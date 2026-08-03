"""Fase 7A.4 / cierre 7A — dual-write consumo, anulación registro y compra.

Ejecutar:

    py -m unittest tests.test_fase7a4_dual_write_consumo -v
"""

from __future__ import annotations

import copy
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application.actor import Actor
from app.core.application.clock import FixedClock
from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import (
    AppData,
    DireccionMovimiento,
    LineaDetalleOrigen,
    LoteStock,
    Producto,
    RegistroDesayuno,
    RolUsuario,
    TipoMovimiento,
    UnidadProducto,
    Usuario,
)
from app.core.models.enums import OrigenConsumo
from app.core.models.registro_servicio import ConsumoLoteDetalle
from app.core.services import anulacion_compra_service as anul_c
from app.core.services import anulacion_registro_service as anul_r
from app.core.services import desayuno_service
from app.core.services import movimiento_service as mov
from app.core.services.diagnostico_service import generar_diagnostico
from app.core.services.stock_service import registrar_lote
from app.data.serializers import appdata_to_dict, dict_to_appdata
from app.ui.theme import APP_VERSION


def _datos() -> AppData:
    return AppData(
        productos=[Producto("p1", "Harina", UnidadProducto.KG)],
        lotes=[
            LoteStock(
                "l1", "p1",
                precio_total=20.0,
                cantidad=10.0,
                cantidad_restante=10.0,
                fecha_compra=date(2026, 7, 1),
            ),
            LoteStock(
                "l2", "p1",
                precio_total=8.0,
                cantidad=4.0,
                cantidad_restante=4.0,
                fecha_compra=date(2026, 7, 2),
            ),
        ],
        usuarios=[Usuario("u01", "Admin", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


def _ctx(data: AppData):
    return build_app_context(
        uow=InMemoryUnitOfWork(data),
        clock=FixedClock(datetime(2026, 7, 30, 10, 0, 0)),
        actor=Actor(id="u01", nombre="Admin", rol="Admin"),
    )


class TestFase7A4Consumo(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _datos()
        self.ctx = _ctx(self.data)
        self._session: dict = {}
        self._st = mock.patch("streamlit.session_state", self._session)
        self._st.start()
        self._alert = mock.patch(
            "app.core.services.alert_service.sincronizar_alertas"
        )
        self._alert.start()

    def tearDown(self) -> None:
        self._alert.stop()
        self._st.stop()

    def _cesta_producto(self, cantidad: float = 3.0) -> None:
        from app.core.services.cesta_service import LineaCesta

        self._session["bm_cesta_desayuno"] = [
            LineaCesta(
                linea_id="lin_0001",
                producto_id="p1",
                nombre="Harina",
                unidad="Kg",
                cantidad=cantidad,
                es_extra=False,
            )
        ]
        self._session["bm_cesta_recetas"] = []

    def test_01_consumo_por_fragmento(self) -> None:
        self._cesta_producto(12.0)
        r = desayuno_service.registrar_desayuno(
            date(2026, 7, 28), 2, ctx=self.ctx,
        )
        self.assertTrue(r.ok, r.mensaje)
        cons = [m for m in self.data.movimientos if m.tipo == TipoMovimiento.CONSUMO]
        self.assertGreaterEqual(len(cons), 2)
        self.assertEqual(sum(m.cantidad for m in cons), 12.0)
        self.assertTrue(all(m.direccion == DireccionMovimiento.SALIDA for m in cons))
        self.assertEqual(self.data.lotes[0].cantidad_restante, 0.0)
        self.assertEqual(self.data.lotes[1].cantidad_restante, 2.0)

    def test_02_origen_y_coste(self) -> None:
        self._cesta_producto(2.0)
        self.assertTrue(
            desayuno_service.registrar_desayuno(date(2026, 7, 28), 1, ctx=self.ctx).ok
        )
        m = self.data.movimientos[0]
        self.assertEqual(m.origen_tipo, mov.ORIGEN_TIPO_DESAYUNO)
        self.assertEqual(m.origen_id, self.data.desayunos[0].id)
        self.assertTrue(m.origen_linea_id.startswith("det"))
        frag = self.data.desayunos[0].lineas_detalle[0].consumos_lote[0]
        self.assertEqual(m.coste_total_snapshot, frag.coste)

    def test_03_idempotencia_consumo(self) -> None:
        self._cesta_producto(1.0)
        self.assertTrue(
            desayuno_service.registrar_desayuno(date(2026, 7, 28), 1, ctx=self.ctx).ok
        )
        n = len(self.data.movimientos)
        rid = self.data.desayunos[0].id
        mov.escribir_espejos_consumo_registro(
            origen_tipo=mov.ORIGEN_TIPO_DESAYUNO,
            registro_id=rid,
            lineas_detalle=self.data.desayunos[0].lineas_detalle,
            fecha=date(2026, 7, 28),
            ctx=self.ctx,
        )
        self.assertEqual(len(self.data.movimientos), n)

    def test_04_fallo_espejo_revierte_desayuno(self) -> None:
        self._cesta_producto(1.0)
        with patch(
            "app.core.services.movimiento_service.escribir_espejos_consumo_registro",
            side_effect=RuntimeError("forzado"),
        ):
            with self.assertRaises(RuntimeError):
                desayuno_service.registrar_desayuno(
                    date(2026, 7, 28), 1, ctx=self.ctx,
                )
        self.assertEqual(self.data.desayunos, [])
        self.assertEqual(self.data.movimientos, [])
        self.assertEqual(self.data.lotes[0].cantidad_restante, 10.0)

    def test_05_anulacion_crea_reversion_consumo(self) -> None:
        self._cesta_producto(2.0)
        self.assertTrue(
            desayuno_service.registrar_desayuno(date(2026, 7, 28), 1, ctx=self.ctx).ok
        )
        rid = self.data.desayunos[0].id
        origs = [m.id for m in self.data.movimientos if m.tipo == TipoMovimiento.CONSUMO]
        r = anul_r.anular_registro(
            self.data, rid, anul_r.TIPO_DESAYUNO, "error", ctx=self.ctx,
        )
        self.assertTrue(r.ok, r.mensaje)
        revs = [
            m for m in self.data.movimientos
            if m.tipo == TipoMovimiento.REVERSION_CONSUMO
        ]
        self.assertEqual(len(revs), len(origs))
        self.assertTrue(all(m.direccion == DireccionMovimiento.ENTRADA for m in revs))
        self.assertEqual({m.movimiento_revertido_id for m in revs}, set(origs))
        self.assertEqual(self.data.lotes[0].cantidad_restante, 10.0)

    def test_06_anulacion_historica_sin_espejo(self) -> None:
        reg = RegistroDesayuno(
            id="d_hist",
            fecha=date(2026, 6, 1),
            lineas=[],
            coste_total=2.0,
            registrado_por="Ana",
            num_huespedes=1,
            lineas_detalle=[
                LineaDetalleOrigen(
                    origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                    producto_id="p1",
                    cantidad=2.0,
                    coste=4.0,
                    consumos_lote=[
                        ConsumoLoteDetalle("l1", "p1", 2.0, 4.0),
                    ],
                )
            ],
        )
        self.data.desayunos.append(reg)
        self.data.lotes[0].cantidad_restante = 8.0
        r = anul_r.anular_registro(
            self.data, "d_hist", anul_r.TIPO_DESAYUNO, "hist", ctx=self.ctx,
        )
        self.assertTrue(r.ok, r.mensaje)
        revs = [
            m for m in self.data.movimientos
            if m.tipo == TipoMovimiento.REVERSION_CONSUMO
        ]
        self.assertEqual(len(revs), 1)
        self.assertIsNone(revs[0].movimiento_revertido_id)
        self.assertEqual(
            revs[0].origen_tipo, mov.ORIGEN_TIPO_ANULACION_REGISTRO_HISTORICA
        )

    def test_07_anulacion_compra_reversion_entrada(self) -> None:
        with patch("app.core.services.stock_service.get_data", return_value=self.data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            self.assertTrue(
                registrar_lote("p1", 5.0, 2.0, fecha_compra=date(2026, 7, 5)).ok
            )
        lote = self.data.lotes[-1]
        r = anul_c.anular_compra(self.data, lote.id, "error compra", ctx=self.ctx)
        self.assertTrue(r.ok, r.mensaje)
        revs = [
            m for m in self.data.movimientos
            if m.tipo == TipoMovimiento.REVERSION_ENTRADA
        ]
        self.assertEqual(len(revs), 1)
        self.assertEqual(revs[0].cantidad, 2.0)
        self.assertEqual(revs[0].direccion, DireccionMovimiento.SALIDA)
        self.assertIsNotNone(revs[0].movimiento_revertido_id)
        self.assertEqual(lote.cantidad_restante, 0.0)

    def test_08_diagnostico_y_reconciliacion(self) -> None:
        self._cesta_producto(1.0)
        self.assertTrue(
            desayuno_service.registrar_desayuno(date(2026, 7, 28), 1, ctx=self.ctx).ok
        )
        antes = copy.deepcopy(appdata_to_dict(self.data))
        resumen = generar_diagnostico(self.data)
        self.assertGreaterEqual(resumen.num_movimientos_consumo, 1)
        tipos = mov.resumen_tipos_ledger(self.data)
        self.assertGreater(tipos.consumos, 0)
        mov.reconciliacion_informativa(self.data)
        self.assertEqual(antes, appdata_to_dict(self.data))

    def test_09_json_antiguo_y_version(self) -> None:
        data = dict_to_appdata({"meta": {}, "productos": []})
        self.assertEqual(data.movimientos, [])
        self.assertIn("Ledger espejo completo", APP_VERSION)

    def test_10_stock_sigue_en_lotes(self) -> None:
        self._cesta_producto(1.0)
        self.assertTrue(
            desayuno_service.registrar_desayuno(date(2026, 7, 28), 1, ctx=self.ctx).ok
        )
        stock = sum(l.cantidad_restante for l in self.data.lotes if not l.anulado)
        self.assertEqual(stock, 13.0)


if __name__ == "__main__":
    unittest.main()
