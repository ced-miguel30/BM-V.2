"""Fase 7B.2 — saldo ledger en modo sombra.

Ejecutar:

    py -m unittest tests.test_fase7b2_shadow_balance -v
"""

from __future__ import annotations

import copy
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import (
    AppData,
    ConfiguracionHotel,
    DireccionMovimiento,
    LoteStock,
    MovimientoInventario,
    Producto,
    TipoMovimiento,
    UnidadProducto,
)
from app.core.services import inventory_batch_service as fifo
from app.core.services.ledger_balance_service import (
    comparar_lote_vs_restante,
    comparar_producto_vs_restante,
    diagnostico_modo_sombra,
    saldo_ledger_por_lote,
    saldo_ledger_por_producto,
)
from app.core.services.ledger_config import fijar_modo_saldo
from app.data.serializers import appdata_to_dict


def _data_completa() -> AppData:
    data = AppData(
        productos=[Producto("p01", "Leche", UnidadProducto.L)],
        lotes=[
            LoteStock(
                "lot01",
                "p01",
                20.0,
                10.0,
                6.0,
                fecha_compra=date(2026, 1, 1),
            )
        ],
        configuracion=ConfiguracionHotel(
            "H",
            "EUR",
            ledger_activation_iso="2026-01-01T00:00:00",
            ledger_balance_mode="shadow",
            ledger_qty_tolerance=1e-4,
        ),
    )
    data.movimientos = [
        MovimientoInventario(
            "m1",
            "p01",
            "lot01",
            TipoMovimiento.ENTRADA_COMPRA,
            DireccionMovimiento.ENTRADA,
            10.0,
            date(2026, 1, 1),
            None,
            "lote",
            "lot01",
            creado_en=datetime(2026, 1, 1, 9, 0, 0),
        ),
        MovimientoInventario(
            "m2",
            "p01",
            "lot01",
            TipoMovimiento.CONSUMO,
            DireccionMovimiento.SALIDA,
            4.0,
            date(2026, 1, 2),
            None,
            "desayuno",
            "d01",
            creado_en=datetime(2026, 1, 2, 9, 0, 0),
        ),
    ]
    return data


class TestFase7B2ShadowBalance(unittest.TestCase):
    def test_01_saldo_por_lote(self) -> None:
        data = _data_completa()
        self.assertAlmostEqual(saldo_ledger_por_lote(data, "lot01"), 6.0)

    def test_02_saldo_por_producto(self) -> None:
        data = _data_completa()
        self.assertAlmostEqual(saldo_ledger_por_producto(data, "p01"), 6.0)

    def test_03_comparacion_sin_diff(self) -> None:
        data = _data_completa()
        c = comparar_lote_vs_restante(data, data.lotes[0])
        self.assertTrue(c.dentro_tolerancia)
        self.assertAlmostEqual(c.diferencia, 0.0, places=4)

    def test_04_tolerancia(self) -> None:
        data = _data_completa()
        data.lotes[0].cantidad_restante = 6.0 + 5e-5  # dentro de 1e-4
        c = comparar_lote_vs_restante(data, data.lotes[0])
        self.assertTrue(c.dentro_tolerancia)
        data.lotes[0].cantidad_restante = 6.0 + 0.01
        c2 = comparar_lote_vs_restante(data, data.lotes[0])
        self.assertFalse(c2.dentro_tolerancia)

    def test_05_shadow_no_cambia_fifo_operativo(self) -> None:
        data = _data_completa()
        fijar_modo_saldo(data, "shadow")
        antes = copy.deepcopy(appdata_to_dict(data))
        diag = diagnostico_modo_sombra(data)
        self.assertEqual(diag.modo, "shadow")
        self.assertTrue(diag.ok_post_activacion)
        # FIFO sigue leyendo cantidad_restante
        self.assertAlmostEqual(fifo.stock_disponible(data, "p01"), 6.0)
        self.assertEqual(appdata_to_dict(data), antes)

    def test_06_producto_comparacion(self) -> None:
        data = _data_completa()
        p = comparar_producto_vs_restante(data, "p01")
        self.assertTrue(p.dentro_tolerancia)
        self.assertEqual(len(p.lotes), 1)

    def test_07_legacy_mode_label(self) -> None:
        data = _data_completa()
        fijar_modo_saldo(data, "legacy")
        self.assertEqual(diagnostico_modo_sombra(data).modo, "legacy")


if __name__ == "__main__":
    unittest.main()
