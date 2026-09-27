"""Valoración: FIFO mientras haya stock; sobreconsumo al último precio."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BM_TEST_ISOLATION", "1")

from app.core.models import AppData, LoteStock, Producto, UnidadProducto
from app.core.services.inventory_batch_service import (
    descontar_lotes,
    valorizar_cantidad_fifo,
)


def _data_dos_lotes() -> AppData:
    """Lote viejo 10 ud @ 1 €; lote nuevo 5 ud @ 3 €."""
    return AppData(
        productos=[
            Producto("p1", "Huevo", UnidadProducto.UD, codigo="H"),
        ],
        lotes=[
            LoteStock("l1", "p1", 10.0, 10.0, 10.0, date(2026, 8, 1)),
            LoteStock("l2", "p1", 15.0, 5.0, 5.0, date(2026, 9, 1)),
        ],
    )


class TestValoracionUltimoPrecio(unittest.TestCase):
    def test_fifo_mientras_haya_stock(self) -> None:
        data = _data_dos_lotes()
        # 12 ud: 10@1 + 2@3 = 16
        val = valorizar_cantidad_fifo(data, "p1", 12.0)
        self.assertFalse(val.incompleto)
        self.assertAlmostEqual(val.coste, 16.0, places=2)

    def test_sobreconsumo_usa_ultimo_lote_con_precio(self) -> None:
        data = _data_dos_lotes()
        # 20 ud: 10@1 + 5@3 + 5@3 (vigente l2) = 10+15+15 = 40
        val = valorizar_cantidad_fifo(data, "p1", 20.0)
        self.assertFalse(val.incompleto)
        self.assertAlmostEqual(val.coste, 40.0, places=2)

    def test_stock_agotado_solo_ultimo_precio(self) -> None:
        data = _data_dos_lotes()
        for l in data.lotes:
            l.cantidad_restante = 0.0
        val = valorizar_cantidad_fifo(data, "p1", 4.0)
        self.assertFalse(val.incompleto)
        self.assertAlmostEqual(val.coste, 12.0, places=2)  # 4 * 3

    def test_descontar_negativo_valora_overdraw(self) -> None:
        data = _data_dos_lotes()
        res = descontar_lotes(data, "p1", 20.0, permitir_negativo=True)
        self.assertAlmostEqual(res.coste, 40.0, places=2)
        self.assertGreater(len(res.movimientos), 1)
        self.assertAlmostEqual(sum(m.coste for m in res.movimientos), 40.0, places=2)
        # Overdraw no a 0 €
        self.assertTrue(all(m.coste > 0 or m.cantidad <= 0 for m in res.movimientos))

    def test_nuevo_precio_pasa_a_ser_vigente(self) -> None:
        data = _data_dos_lotes()
        for l in data.lotes:
            l.cantidad_restante = 0.0
        data.lotes.append(
            LoteStock("l3", "p1", 20.0, 4.0, 0.0, date(2026, 9, 10)),  # 5 €/ud, sin stock
        )
        # Sin stock: vigente = l3 @ 5 €
        val = valorizar_cantidad_fifo(data, "p1", 2.0)
        self.assertAlmostEqual(val.coste, 10.0, places=2)

    def test_sin_ningun_precio_incompleto(self) -> None:
        data = AppData(
            productos=[Producto("p1", "X", UnidadProducto.UD, codigo="X")],
            lotes=[
                LoteStock("l0", "p1", 0.0, 10.0, 0.0, date(2026, 8, 1)),
            ],
        )
        val = valorizar_cantidad_fifo(data, "p1", 3.0)
        self.assertTrue(val.incompleto)
        self.assertAlmostEqual(val.coste, 0.0, places=2)


if __name__ == "__main__":
    unittest.main()
