"""Fase 7B.5 — ledger como fuente de verdad (modos legacy/shadow/ledger).

Ejecutar:

    py -m unittest tests.test_fase7b5_ledger_sot -v
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

from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
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
from app.core.services import movimiento_service as mov
from app.core.services.inventory_balance import cantidad_disponible_lote
from app.core.services.ledger_config import fijar_modo_saldo, ledger_balance_mode
from app.data.serializers import appdata_to_dict


def _data_cubierta() -> AppData:
    data = AppData(
        productos=[Producto("p01", "Leche", UnidadProducto.L)],
        lotes=[
            LoteStock(
                "lot01",
                "p01",
                20.0,
                10.0,
                10.0,
                fecha_compra=date(2026, 1, 1),
            ),
            LoteStock(
                "lot02",
                "p01",
                10.0,
                5.0,
                5.0,
                fecha_compra=date(2026, 1, 5),
            ),
        ],
        configuracion=ConfiguracionHotel(
            "H",
            "EUR",
            ledger_activation_iso="2026-01-01T00:00:00",
            ledger_balance_mode="shadow",
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
            "lot02",
            TipoMovimiento.ENTRADA_COMPRA,
            DireccionMovimiento.ENTRADA,
            5.0,
            date(2026, 1, 5),
            None,
            "lote",
            "lot02",
            creado_en=datetime(2026, 1, 5, 9, 0, 0),
        ),
    ]
    return data


class TestFase7B5LedgerSoT(unittest.TestCase):
    def test_01_modos(self) -> None:
        data = _data_cubierta()
        for mode in ("legacy", "shadow", "ledger"):
            fijar_modo_saldo(data, mode)
            self.assertEqual(ledger_balance_mode(data), mode)

    def test_02_fifo_igual_en_shadow_y_ledger(self) -> None:
        data_s = _data_cubierta()
        data_l = _data_cubierta()
        fijar_modo_saldo(data_s, "shadow")
        fijar_modo_saldo(data_l, "ledger")
        ids_s = [l.id for l in fifo.lotes_ordenados_consumo(data_s, "p01")]
        ids_l = [l.id for l in fifo.lotes_ordenados_consumo(data_l, "p01")]
        self.assertEqual(ids_s, ids_l)
        self.assertEqual(ids_s, ["lot01", "lot02"])

    def test_03_stock_nuevo_desde_ledger(self) -> None:
        data = _data_cubierta()
        fijar_modo_saldo(data, "ledger")
        # Divergencia artificial en restante: ledger manda
        data.lotes[0].cantidad_restante = 99.0
        self.assertAlmostEqual(
            cantidad_disponible_lote(data, data.lotes[0]), 10.0
        )
        self.assertAlmostEqual(fifo.stock_disponible(data, "p01"), 15.0)

    def test_04_compatibilidad_historica(self) -> None:
        data = AppData(
            productos=[Producto("p01", "X", UnidadProducto.UD)],
            lotes=[
                LoteStock(
                    "old",
                    "p01",
                    5.0,
                    5.0,
                    3.0,
                    fecha_compra=date(2024, 1, 1),
                )
            ],
            configuracion=ConfiguracionHotel(
                "H",
                "EUR",
                ledger_activation_iso="2026-01-01T00:00:00",
                ledger_balance_mode="ledger",
            ),
        )
        # Sin movimientos → cobertura histórica → legacy híbrido
        self.assertAlmostEqual(
            cantidad_disponible_lote(data, data.lotes[0]), 3.0
        )

    def test_05_vuelta_a_shadow(self) -> None:
        data = _data_cubierta()
        fijar_modo_saldo(data, "ledger")
        n_mov = len(data.movimientos)
        fijar_modo_saldo(data, "shadow")
        self.assertEqual(ledger_balance_mode(data), "shadow")
        self.assertEqual(len(data.movimientos), n_mov)

    def test_06_fallo_movimiento_no_cambia_saldo(self) -> None:
        data = _data_cubierta()
        fijar_modo_saldo(data, "ledger")
        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        antes = copy.deepcopy(appdata_to_dict(data))
        r = mov.crear_movimiento(
            producto_id="p01",
            lote_id="lot_inexistente",
            tipo=TipoMovimiento.CONSUMO,
            direccion=DireccionMovimiento.SALIDA,
            cantidad=1.0,
            fecha=date(2026, 2, 1),
            origen_tipo="desayuno",
            origen_id="d99",
            ctx=ctx,
            commit=False,
        )
        self.assertFalse(r.ok)
        self.assertEqual(appdata_to_dict(data)["lotes"], antes["lotes"])
        self.assertEqual(
            len(appdata_to_dict(data)["movimientos"]),
            len(antes["movimientos"]),
        )

    def test_07_descuento_fifo_en_ledger(self) -> None:
        data = _data_cubierta()
        fijar_modo_saldo(data, "ledger")
        res = fifo.descontar_lotes(data, "p01", 12.0)
        self.assertAlmostEqual(res.coste, 20.0 + 4.0, places=2)  # 10*2 + 2*2
        self.assertAlmostEqual(data.lotes[0].cantidad_restante, 0.0)
        self.assertAlmostEqual(data.lotes[1].cantidad_restante, 3.0)


if __name__ == "__main__":
    unittest.main()
