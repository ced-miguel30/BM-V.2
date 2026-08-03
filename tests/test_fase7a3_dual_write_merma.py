"""Fase 7A.3 — dual-write espejo: merma y anulación de merma.

Ejecutar:

    py -m unittest tests.test_fase7a3_dual_write_merma -v
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
from app.core.application import espacios as esp
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import (
    AppData,
    Categoria,
    Departamento,
    DireccionMovimiento,
    LineaMerma,
    LoteStock,
    MotivoAjuste,
    MotivoMerma,
    Producto,
    RegistroMerma,
    ResponsableMerma,
    RolUsuario,
    Subcategoria,
    TipoArticulo,
    TipoMovimiento,
    Ubicacion,
    UnidadProducto,
    Usuario,
)
from app.core.services import ajuste_service
from app.core.services import anulacion_merma_service as anul
from app.core.services import merma_service
from app.core.services import movimiento_service as mov
from app.core.services.diagnostico_service import generar_diagnostico
from app.core.services.inventory_batch_service import descontar_lotes
from app.core.services.merma_service import LineaCestaMerma
from app.core.services.stock_service import registrar_lote
from app.data.serializers import appdata_to_dict, dict_to_appdata
from app.ui.theme import APP_VERSION


def _datos() -> AppData:
    return AppData(
        productos=[
            Producto(
                "p1",
                "Pan",
                UnidadProducto.UD,
                categoria_id="cat01",
                subcategoria_id="sub01",
                departamento_ids=["dep01"],
                ubicacion_ids=["ubi01"],
                tipo_articulo=TipoArticulo.CONSUMIBLE,
                categoria_inventario="Panadería",
            )
        ],
        lotes=[
            LoteStock(
                "l1",
                "p1",
                precio_total=20.0,
                cantidad=10.0,
                cantidad_restante=10.0,
                fecha_compra=date(2026, 7, 1),
            ),
        ],
        responsables_merma=[ResponsableMerma("rm01", "Ana", True)],
        departamentos=[Departamento("dep01", "Cocina", True)],
        categorias=[Categoria("cat01", "Panadería", True)],
        subcategorias=[Subcategoria("sub01", "Barras", "cat01", True)],
        ubicaciones=[Ubicacion("ubi01", "Cámara", True)],
        usuarios=[Usuario("u01", "Admin", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


def _ctx(data: AppData):
    return build_app_context(
        uow=InMemoryUnitOfWork(data),
        clock=FixedClock(datetime(2026, 7, 30, 9, 0, 0)),
        actor=Actor(id="u01", nombre="Admin", rol="Admin"),
    )


def _linea_cesta(
    *,
    lote_id: str = "l1",
    producto_id: str = "p1",
    cantidad: float = 2.0,
    motivo: str | None = None,
    servicio: str = "general",
    turno: str = "manana",
) -> LineaCestaMerma:
    return LineaCestaMerma(
        lote_id=lote_id,
        producto_id=producto_id,
        nombre="Pan",
        unidad="Ud",
        fecha_compra_txt="01/07/2026",
        cantidad=cantidad,
        motivo=motivo or MotivoMerma.EXPIRACION.value,
        tipo_servicio_snapshot=servicio,
        turno_snapshot=turno,
        responsable_id="rm01",
        responsable_nombre="Ana",
    )


class TestFase7A3DualWriteMerma(unittest.TestCase):
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

    def _registrar(self, *lineas: LineaCestaMerma) -> merma_service.ResultadoOperacion:
        self._session[merma_service.CESTA_MERMA_KEY] = list(lineas)
        return merma_service.registrar_merma(date(2026, 7, 28), ctx=self.ctx)

    def test_01_una_linea_crea_movimiento(self) -> None:
        r = self._registrar(_linea_cesta(cantidad=2.0))
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(len(self.data.movimientos), 1)
        self.assertEqual(self.data.lotes[0].cantidad_restante, 8.0)

    def test_02_varias_lineas_movimientos_separados(self) -> None:
        r = self._registrar(
            _linea_cesta(cantidad=1.0, servicio="desayuno"),
            _linea_cesta(cantidad=1.5, servicio="comida", turno="tarde"),
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(len(self.data.mermas[0].lineas), 2)
        self.assertEqual(len(self.data.movimientos), 2)

    def test_03_producto_coincide(self) -> None:
        self._registrar(_linea_cesta())
        self.assertEqual(self.data.movimientos[0].producto_id, "p1")

    def test_04_lote_coincide(self) -> None:
        self._registrar(_linea_cesta())
        self.assertEqual(self.data.movimientos[0].lote_id, "l1")

    def test_05_cantidad_coincide(self) -> None:
        self._registrar(_linea_cesta(cantidad=2.5))
        self.assertEqual(self.data.movimientos[0].cantidad, 2.5)
        self.assertEqual(self.data.mermas[0].lineas[0].cantidad, 2.5)

    def test_06_tipo_merma(self) -> None:
        self._registrar(_linea_cesta())
        self.assertEqual(self.data.movimientos[0].tipo, TipoMovimiento.MERMA)

    def test_07_direccion_salida(self) -> None:
        self._registrar(_linea_cesta())
        self.assertEqual(
            self.data.movimientos[0].direccion, DireccionMovimiento.SALIDA
        )

    def test_08_coste_snapshot(self) -> None:
        self._registrar(_linea_cesta(cantidad=2.0))
        m = self.data.movimientos[0]
        ln = self.data.mermas[0].lineas[0]
        self.assertEqual(m.coste_total_snapshot, ln.coste)
        self.assertAlmostEqual(
            m.coste_unitario_snapshot or 0, ln.coste / ln.cantidad
        )

    def test_09_origen_estable(self) -> None:
        self._registrar(_linea_cesta())
        m = self.data.movimientos[0]
        self.assertEqual(m.origen_tipo, mov.ORIGEN_TIPO_MERMA)
        self.assertEqual(m.origen_id, self.data.mermas[0].id)
        self.assertEqual(m.origen_linea_id, "ln00")

    def test_10_reintento_no_duplica(self) -> None:
        self._registrar(_linea_cesta(cantidad=1.0))
        reg = self.data.mermas[0]
        ln = reg.lineas[0]
        r2 = mov.espejo_merma_linea(
            producto_id=ln.producto_id,
            lote_id=ln.lote_id or "l1",
            cantidad=ln.cantidad,
            fecha=reg.fecha,
            merma_id=reg.id,
            indice_linea=0,
            coste_total=ln.coste,
            ctx=self.ctx,
            commit=False,
        )
        self.assertTrue(r2.duplicado)
        self.assertEqual(len(mov.buscar_por_origen(self.data, "merma", reg.id)), 1)

    def test_11_12_13_14_fallo_espejo_revierte_todo(self) -> None:
        self._session[merma_service.CESTA_MERMA_KEY] = [_linea_cesta(cantidad=3.0)]
        with patch(
            "app.core.services.movimiento_service.espejo_merma_linea",
            return_value=mov.ResultadoMovimiento(ok=False, mensaje="forzado"),
        ):
            with self.assertRaises(RuntimeError):
                merma_service.registrar_merma(date(2026, 7, 28), ctx=self.ctx)
        self.assertEqual(self.data.lotes[0].cantidad_restante, 10.0)
        self.assertEqual(self.data.mermas, [])
        self.assertEqual(self.data.movimientos, [])
        self.assertEqual(self.data.actividades, [])

    def test_15_16_17_18_anulacion_crea_reversion(self) -> None:
        self._registrar(_linea_cesta(cantidad=2.0))
        orig = self.data.movimientos[0]
        r = anul.anular_merma(self.data, self.data.mermas[0].id, "error", ctx=self.ctx)
        self.assertTrue(r.ok, r.mensaje)
        revs = [
            m
            for m in self.data.movimientos
            if m.tipo == TipoMovimiento.REVERSION_MERMA
        ]
        self.assertEqual(len(revs), 1)
        rev = revs[0]
        self.assertEqual(rev.direccion, DireccionMovimiento.ENTRADA)
        self.assertEqual(rev.movimiento_revertido_id, orig.id)
        self.assertEqual(rev.producto_id, "p1")
        self.assertEqual(rev.lote_id, "l1")
        self.assertEqual(rev.cantidad, 2.0)
        self.assertEqual(self.data.lotes[0].cantidad_restante, 10.0)

    def test_19_doble_anulacion_no_duplica(self) -> None:
        self._registrar(_linea_cesta(cantidad=1.0))
        mid = self.data.mermas[0].id
        self.assertTrue(anul.anular_merma(self.data, mid, "uno", ctx=self.ctx).ok)
        n_rev = sum(
            1
            for m in self.data.movimientos
            if m.tipo == TipoMovimiento.REVERSION_MERMA
        )
        r2 = anul.anular_merma(self.data, mid, "dos", ctx=self.ctx)
        self.assertFalse(r2.ok)
        n_rev2 = sum(
            1
            for m in self.data.movimientos
            if m.tipo == TipoMovimiento.REVERSION_MERMA
        )
        self.assertEqual(n_rev, n_rev2)
        self.assertEqual(n_rev, 1)

    def test_20_21_fallo_reverso_restaura(self) -> None:
        self._registrar(_linea_cesta(cantidad=2.0))
        restante = self.data.lotes[0].cantidad_restante
        mid = self.data.mermas[0].id
        with patch(
            "app.core.services.movimiento_service.espejo_reversion_merma_linea",
            return_value=mov.ResultadoMovimiento(ok=False, mensaje="forzado"),
        ):
            r = anul.anular_merma(self.data, mid, "x", ctx=self.ctx)
        self.assertFalse(r.ok)
        self.assertFalse(self.data.mermas[0].anulado)
        self.assertEqual(self.data.lotes[0].cantidad_restante, restante)
        self.assertFalse(
            any(m.tipo == TipoMovimiento.REVERSION_MERMA for m in self.data.movimientos)
        )

    def test_22_historica_sin_backfill(self) -> None:
        hist = RegistroMerma(
            id="m_hist",
            fecha=date(2026, 6, 1),
            coste_total=2.0,
            lineas=[
                LineaMerma("p1", 1.0, 2.0, MotivoMerma.MERMA, lote_id="l1"),
            ],
        )
        self.data.mermas.append(hist)
        self.data.lotes[0].cantidad_restante = 9.0
        self.assertEqual(self.data.movimientos, [])
        # No se generan movimientos al diagnosticar
        generar_diagnostico(self.data)
        self.assertEqual(self.data.movimientos, [])

    def test_23_anulacion_historica_cobertura_parcial(self) -> None:
        hist = RegistroMerma(
            id="m_hist2",
            fecha=date(2026, 6, 2),
            coste_total=3.0,
            lineas=[
                LineaMerma("p1", 1.5, 3.0, MotivoMerma.MERMA, lote_id="l1"),
            ],
        )
        self.data.mermas.append(hist)
        self.data.lotes[0].cantidad_restante = 8.5
        r = anul.anular_merma(self.data, "m_hist2", "histórico", ctx=self.ctx)
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(self.data.lotes[0].cantidad_restante, 10.0)
        revs = [
            m
            for m in self.data.movimientos
            if m.tipo == TipoMovimiento.REVERSION_MERMA
        ]
        self.assertEqual(len(revs), 1)
        self.assertIsNone(revs[0].movimiento_revertido_id)
        self.assertEqual(
            revs[0].origen_tipo, mov.ORIGEN_TIPO_ANULACION_MERMA_HISTORICA
        )
        resumen = generar_diagnostico(self.data)
        self.assertTrue(
            any(
                "cobertura histórica parcial" in i or "sin movimiento espejo original" in i
                for i in resumen.incidencias_movimientos
            )
        )

    def test_24_diagnostico_merma_sin_movimiento(self) -> None:
        self._registrar(_linea_cesta(cantidad=1.0))
        self.data.movimientos.clear()
        resumen = generar_diagnostico(self.data)
        self.assertTrue(
            any("sin movimiento" in i for i in resumen.incidencias_movimientos)
        )

    def test_25_diagnostico_movimiento_sin_merma(self) -> None:
        self._registrar(_linea_cesta(cantidad=1.0))
        self.data.mermas.clear()
        resumen = generar_diagnostico(self.data)
        self.assertTrue(
            any("origen inexistente" in i for i in resumen.incidencias_movimientos)
        )

    def test_26_diagnostico_cantidad_distinta(self) -> None:
        self._registrar(_linea_cesta(cantidad=2.0))
        self.data.movimientos[0].cantidad = 9.0
        resumen = generar_diagnostico(self.data)
        self.assertTrue(
            any("cantidad distinta" in i for i in resumen.incidencias_movimientos)
        )

    def test_27_diagnostico_doble_reverso(self) -> None:
        self._registrar(_linea_cesta(cantidad=1.0))
        mid = self.data.mermas[0].id
        self.assertTrue(anul.anular_merma(self.data, mid, "uno", ctx=self.ctx).ok)
        orig = mov.buscar_movimiento_merma_linea(self.data, mid, 0)
        assert orig is not None
        # Forzar segundo reverso saltando la guarda (append directo)
        from app.core.models import MovimientoInventario

        self.data.movimientos.append(
            MovimientoInventario(
                id="mov99",
                producto_id="p1",
                lote_id="l1",
                tipo=TipoMovimiento.REVERSION_MERMA,
                direccion=DireccionMovimiento.ENTRADA,
                cantidad=1.0,
                fecha=date.today(),
                hora=None,
                origen_tipo=mov.ORIGEN_TIPO_ANULACION_MERMA,
                origen_id=mid,
                origen_linea_id="ln00",
                movimiento_revertido_id=orig.id,
                idempotency_key="forzado-doble",
            )
        )
        resumen = generar_diagnostico(self.data)
        self.assertTrue(
            any(
                "más de una vez" in i or "Doble reverso" in i
                for i in resumen.incidencias_movimientos
            )
        )

    def test_28_diagnostico_no_modifica(self) -> None:
        self._registrar(_linea_cesta(cantidad=1.0))
        antes = copy.deepcopy(appdata_to_dict(self.data))
        generar_diagnostico(self.data)
        self.assertEqual(antes, appdata_to_dict(self.data))

    def test_29_reconciliacion_no_modifica_stock(self) -> None:
        self._registrar(_linea_cesta(cantidad=1.0))
        restante = self.data.lotes[0].cantidad_restante
        mov.reconciliacion_informativa(self.data)
        mov.cobertura_merma_informativa(self.data)
        self.assertEqual(self.data.lotes[0].cantidad_restante, restante)

    def test_30_stock_desde_cantidad_restante(self) -> None:
        self._registrar(_linea_cesta(cantidad=3.0))
        # Crear movimiento aislado no debería usarse como stock
        mov.crear_movimiento(
            producto_id="p1",
            lote_id="l1",
            tipo=TipoMovimiento.AJUSTE_SALIDA,
            direccion=DireccionMovimiento.SALIDA,
            cantidad=50.0,
            fecha=date.today(),
            origen_tipo="test",
            origen_id="iso",
            ctx=self.ctx,
            commit=False,
        )
        stock = sum(l.cantidad_restante for l in self.data.lotes)
        self.assertEqual(stock, 7.0)

    def test_31_fifo_intacto(self) -> None:
        self.data.lotes.append(
            LoteStock(
                "l2",
                "p1",
                precio_total=6.0,
                cantidad=3.0,
                cantidad_restante=3.0,
                fecha_compra=date(2026, 7, 2),
            )
        )
        self._registrar(_linea_cesta(cantidad=1.0))
        copia = copy.deepcopy(self.data)
        copia.movimientos = []
        a = descontar_lotes(copia, "p1", 2.0)
        b = descontar_lotes(self.data, "p1", 2.0)
        self.assertEqual(
            [(m.lote_id, m.cantidad) for m in a.movimientos],
            [(m.lote_id, m.cantidad) for m in b.movimientos],
        )
        self.assertEqual(b.movimientos[0].lote_id, "l1")

    def test_32_entrada_7a2_sigue(self) -> None:
        with patch("app.core.services.stock_service.get_data", return_value=self.data), \
             patch("app.core.services.stock_service.persist_data", side_effect=lambda d: d):
            r = registrar_lote("p1", 8.0, 2.0, fecha_compra=date(2026, 7, 10))
        self.assertTrue(r.ok)
        self.assertTrue(
            any(m.tipo == TipoMovimiento.ENTRADA_COMPRA for m in self.data.movimientos)
        )

    def test_33_ajuste_7a2_sigue(self) -> None:
        r = ajuste_service.aplicar_ajuste(
            date(2026, 7, 22),
            "l1",
            9.0,
            MotivoAjuste.RECONTEO_FISICO.value,
            ctx=self.ctx,
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertTrue(
            any(m.tipo == TipoMovimiento.AJUSTE_SALIDA for m in self.data.movimientos)
        )

    def test_34_campos_6a_6b_6c(self) -> None:
        self._registrar(_linea_cesta(cantidad=1.0))
        back = dict_to_appdata(appdata_to_dict(self.data))
        p = back.productos[0]
        self.assertEqual(p.categoria_id, "cat01")
        self.assertEqual(p.ubicacion_ids, ["ubi01"])
        self.assertEqual(p.tipo_articulo, TipoArticulo.CONSUMIBLE)

    def test_35_espacios_f5(self) -> None:
        self.assertEqual(esp.ESPACIO_DEFAULT, esp.ESPACIO_GESTOR)
        self.assertIn(esp.ESPACIO_REGISTRO, esp.ESPACIOS_ORDEN)
        self.assertIn("Ledger", APP_VERSION)

    def test_36_json_antiguo(self) -> None:
        payload = {
            "meta": {},
            "productos": [{"id": "p1", "nombre": "Pan", "unidad": "Ud"}],
            "mermas": [],
        }
        data = dict_to_appdata(payload)
        self.assertEqual(data.movimientos, [])
        self.assertEqual(data.mermas, [])


if __name__ == "__main__":
    unittest.main()
