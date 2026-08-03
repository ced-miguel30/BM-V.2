"""Fase 7B.6 — recuentos de inventario por ubicación.

Ejecutar:

    py -m unittest tests.test_fase7b6_recuentos -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import (
    AppData,
    ConfiguracionHotel,
    LoteStock,
    Producto,
    Ubicacion,
    UnidadProducto,
)
from app.core.models.recuento import EstadoRecuento
from app.core.services import movimiento_service as mov
from app.core.services import recuento_service as rc
from app.core.services.ubicacion_stock_service import saldo_en_ubicacion
from app.data.serializers import appdata_to_dict, dict_to_appdata
from app.ui.theme import APP_VERSION


def _data() -> AppData:
    data = AppData(
        productos=[
            Producto("p01", "Leche", UnidadProducto.L, ubicacion_ids=["ubi01"])
        ],
        lotes=[
            LoteStock(
                "lot01",
                "p01",
                20.0,
                10.0,
                10.0,
                fecha_compra=date(2026, 1, 1),
            )
        ],
        ubicaciones=[Ubicacion("ubi01", "Cámara", True)],
        configuracion=ConfiguracionHotel(
            "H",
            "EUR",
            ledger_activation_iso="2026-01-01T00:00:00",
            ledger_balance_mode="shadow",
        ),
    )
    ctx = build_app_context(uow=InMemoryUnitOfWork(data))
    mov.espejo_entrada_lote(
        producto_id="p01",
        lote_id="lot01",
        cantidad=10.0,
        fecha=date(2026, 1, 1),
        precio_total=20.0,
        ubicacion_destino_id="ubi01",
        ctx=ctx,
        commit=False,
    )
    return data


class TestFase7B6Recuentos(unittest.TestCase):
    def test_01_borrador(self) -> None:
        data = _data()
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        r = rc.crear_borrador(
            ubicacion_id="ubi01",
            lineas=[("lot01", "p01", 9.0)],
            motivo="Conteo mañana",
            ctx=ctx,
            commit=False,
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(r.sesion.estado, EstadoRecuento.BORRADOR)
        self.assertAlmostEqual(r.sesion.lineas[0].diferencia, -1.0)

    def test_02_confirmacion_ajuste_negativo(self) -> None:
        data = _data()
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        r = rc.crear_borrador(
            ubicacion_id="ubi01",
            lineas=[("lot01", "p01", 8.0)],
            ctx=ctx,
            commit=False,
        )
        conf = rc.confirmar_recuento(recuento_id=r.sesion.id, ctx=ctx, commit=False)
        self.assertTrue(conf.ok, conf.mensaje)
        self.assertEqual(conf.sesion.estado, EstadoRecuento.CONFIRMADO)
        self.assertAlmostEqual(data.lotes[0].cantidad_restante, 8.0)
        self.assertAlmostEqual(saldo_en_ubicacion(data, "lot01", "ubi01"), 8.0)
        self.assertTrue(any(
            (m.tipo.value if hasattr(m.tipo, "value") else m.tipo) == "ajuste_salida"
            for m in data.movimientos
        ))

    def test_03_ajuste_positivo(self) -> None:
        data = _data()
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        r = rc.crear_borrador(
            ubicacion_id="ubi01",
            lineas=[("lot01", "p01", 12.0)],
            ctx=ctx,
            commit=False,
        )
        conf = rc.confirmar_recuento(recuento_id=r.sesion.id, ctx=ctx, commit=False)
        self.assertTrue(conf.ok, conf.mensaje)
        self.assertAlmostEqual(data.lotes[0].cantidad_restante, 12.0)

    def test_04_anulacion(self) -> None:
        data = _data()
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        r = rc.crear_borrador(
            ubicacion_id="ubi01",
            lineas=[("lot01", "p01", 7.0)],
            ctx=ctx,
            commit=False,
        )
        rc.confirmar_recuento(recuento_id=r.sesion.id, ctx=ctx, commit=False)
        an = rc.anular_recuento(recuento_id=r.sesion.id, ctx=ctx, commit=False)
        self.assertTrue(an.ok, an.mensaje)
        self.assertAlmostEqual(data.lotes[0].cantidad_restante, 10.0)

    def test_05_rollback_confirmacion(self) -> None:
        data = _data()
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        # Lote inexistente en confirmación forzada: crear borrador ok, luego
        # corromper línea
        r = rc.crear_borrador(
            ubicacion_id="ubi01",
            lineas=[("lot01", "p01", 9.0)],
            ctx=ctx,
            commit=False,
        )
        r.sesion.lineas[0].lote_id = "lot_fantasma"
        n_aj = len(data.ajustes)
        n_mov = len(data.movimientos)
        conf = rc.confirmar_recuento(recuento_id=r.sesion.id, ctx=ctx, commit=False)
        self.assertFalse(conf.ok)
        self.assertEqual(len(data.ajustes), n_aj)
        self.assertEqual(len(data.movimientos), n_mov)
        self.assertEqual(data.lotes[0].cantidad_restante, 10.0)

    def test_06_roundtrip_y_version(self) -> None:
        data = _data()
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        rc.crear_borrador(
            ubicacion_id="ubi01",
            lineas=[("lot01", "p01", 10.0)],
            ctx=ctx,
            commit=False,
        )
        back = dict_to_appdata(appdata_to_dict(data))
        self.assertEqual(len(back.recuentos), 1)
        self.assertIn("Ledger y stock por ubicación", APP_VERSION)

    def test_07_json_antiguo_sin_recuentos(self) -> None:
        data = dict_to_appdata({"productos": []})
        self.assertEqual(data.recuentos, [])


if __name__ == "__main__":
    unittest.main()
