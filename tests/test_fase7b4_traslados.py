"""Fase 7B.4 — traslados atómicos entre ubicaciones.

Ejecutar:

    py -m unittest tests.test_fase7b4_traslados -v
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
    DireccionMovimiento,
    LoteStock,
    Producto,
    TipoMovimiento,
    Ubicacion,
    UnidadProducto,
)
from app.core.services import movimiento_service as mov
from app.core.services import traslado_service as tr
from app.core.services.ubicacion_stock_service import saldo_en_ubicacion


def _data() -> AppData:
    data = AppData(
        productos=[
            Producto(
                "p01",
                "Leche",
                UnidadProducto.L,
                ubicacion_ids=["ubi01", "ubi02"],
            )
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
        ubicaciones=[
            Ubicacion("ubi01", "Cámara", True),
            Ubicacion("ubi02", "Barra", True),
        ],
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


class TestFase7B4Traslados(unittest.TestCase):
    def test_01_traslado_valido(self) -> None:
        data = _data()
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        r = tr.confirmar_traslado(
            lote_id="lot01",
            ubicacion_origen_id="ubi01",
            ubicacion_destino_id="ubi02",
            cantidad=4.0,
            ctx=ctx,
            commit=False,
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertAlmostEqual(saldo_en_ubicacion(data, "lot01", "ubi01"), 6.0)
        self.assertAlmostEqual(saldo_en_ubicacion(data, "lot01", "ubi02"), 4.0)
        self.assertAlmostEqual(data.lotes[0].cantidad_restante, 10.0)

    def test_02_origen_igual_destino(self) -> None:
        data = _data()
        p = tr.previsualizar_traslado(
            data,
            lote_id="lot01",
            ubicacion_origen_id="ubi01",
            ubicacion_destino_id="ubi01",
            cantidad=1.0,
        )
        self.assertFalse(p.ok)

    def test_03_saldo_insuficiente(self) -> None:
        data = _data()
        p = tr.previsualizar_traslado(
            data,
            lote_id="lot01",
            ubicacion_origen_id="ubi01",
            ubicacion_destino_id="ubi02",
            cantidad=99.0,
        )
        self.assertFalse(p.ok)

    def test_04_stock_y_coste_estables(self) -> None:
        data = _data()
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        coste_antes = data.lotes[0].precio_total
        stock_antes = data.lotes[0].cantidad_restante
        tr.confirmar_traslado(
            lote_id="lot01",
            ubicacion_origen_id="ubi01",
            ubicacion_destino_id="ubi02",
            cantidad=3.0,
            ctx=ctx,
            commit=False,
        )
        self.assertEqual(data.lotes[0].precio_total, coste_antes)
        self.assertEqual(data.lotes[0].cantidad_restante, stock_antes)
        self.assertEqual(data.lotes[0].cantidad, 10.0)

    def test_05_reversion(self) -> None:
        data = _data()
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        r = tr.confirmar_traslado(
            lote_id="lot01",
            ubicacion_origen_id="ubi01",
            ubicacion_destino_id="ubi02",
            cantidad=5.0,
            ctx=ctx,
            commit=False,
        )
        self.assertTrue(r.ok)
        an = tr.anular_traslado(traslado_id=r.traslado_id, ctx=ctx, commit=False)
        self.assertTrue(an.ok, an.mensaje)
        self.assertAlmostEqual(saldo_en_ubicacion(data, "lot01", "ubi01"), 10.0)
        self.assertAlmostEqual(saldo_en_ubicacion(data, "lot01", "ubi02"), 0.0)

    def test_06_idempotencia_anulacion(self) -> None:
        data = _data()
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        r = tr.confirmar_traslado(
            lote_id="lot01",
            ubicacion_origen_id="ubi01",
            ubicacion_destino_id="ubi02",
            cantidad=2.0,
            ctx=ctx,
            commit=False,
        )
        tr.anular_traslado(traslado_id=r.traslado_id, ctx=ctx, commit=False)
        an2 = tr.anular_traslado(traslado_id=r.traslado_id, ctx=ctx, commit=False)
        self.assertFalse(an2.ok)

    def test_07_rollback_no_persiste_movimiento(self) -> None:
        data = _data()
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        n = len(data.movimientos)
        # forzar fallo: destino inexistente
        r = tr.confirmar_traslado(
            lote_id="lot01",
            ubicacion_origen_id="ubi01",
            ubicacion_destino_id="ubi999",
            cantidad=1.0,
            ctx=ctx,
            commit=False,
        )
        self.assertFalse(r.ok)
        self.assertEqual(len(data.movimientos), n)

    def test_08_ledger_total_coherente(self) -> None:
        data = _data()
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        tr.confirmar_traslado(
            lote_id="lot01",
            ubicacion_origen_id="ubi01",
            ubicacion_destino_id="ubi02",
            cantidad=4.0,
            ctx=ctx,
            commit=False,
        )
        teorico = mov.saldo_teorico_ledger_por_lote(data, "lot01")
        self.assertAlmostEqual(teorico, 10.0)
        self.assertTrue(
            any(
                (m.tipo.value if hasattr(m.tipo, "value") else m.tipo)
                == TipoMovimiento.TRASLADO.value
                for m in data.movimientos
            )
        )


if __name__ == "__main__":
    unittest.main()
