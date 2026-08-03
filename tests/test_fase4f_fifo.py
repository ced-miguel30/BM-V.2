"""Fase 4F — FIFO / inventory_ops vía AppContext.

Caracteriza orden FIFO y equivalencia wrapper ↔ servicio puro.

Ejecutar:

    py -m unittest tests.test_fase4f_fifo -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application.actor import Actor
from app.core.application.clock import FixedClock
from app.core.application.context import build_app_context
from app.core.application.inventory_ops import (
    aplicar_descuento_atomico,
    descontar_lotes,
    planificar_descuento,
    stock_disponible,
)
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import AppData, LoteStock, Producto, UnidadProducto
from app.core.services import inventory_batch_service as ib


def _datos_fifo() -> AppData:
    return AppData(
        productos=[Producto("p1", "Harina", UnidadProducto.KG)],
        lotes=[
            LoteStock(
                "l_nuevo", "p1", 20.0, 10.0, 10.0,
                fecha_compra=date(2026, 7, 20),
            ),
            LoteStock(
                "l_viejo", "p1", 10.0, 10.0, 10.0,
                fecha_compra=date(2026, 7, 1),
            ),
            LoteStock(
                "l_medio", "p1", 15.0, 10.0, 10.0,
                fecha_compra=date(2026, 7, 10),
            ),
        ],
    )


def _ctx(data: AppData):
    return build_app_context(
        uow=InMemoryUnitOfWork(data),
        clock=FixedClock(datetime(2026, 7, 30, 12, 0, 0)),
        actor=Actor(id="u01", nombre="Ana", rol="Admin"),
    )


class TestFase4FFifo(unittest.TestCase):
    def test_orden_fifo_fecha_luego_id(self) -> None:
        data = _datos_fifo()
        orden = [l.id for l in ib.lotes_ordenados_consumo(data, "p1")]
        self.assertEqual(orden, ["l_viejo", "l_medio", "l_nuevo"])

    def test_descontar_consume_lote_mas_antiguo(self) -> None:
        data = _datos_fifo()
        ctx = _ctx(data)
        r = descontar_lotes(ctx, "p1", 5.0)
        self.assertEqual(r.movimientos[0].lote_id, "l_viejo")
        self.assertAlmostEqual(data.lotes[1].cantidad_restante, 5.0, places=4)  # l_viejo
        self.assertAlmostEqual(data.lotes[0].cantidad_restante, 10.0, places=4)  # l_nuevo intacto

    def test_ops_equivalente_a_servicio_puro(self) -> None:
        data_a = _datos_fifo()
        data_b = _datos_fifo()
        ctx = _ctx(data_a)
        self.assertEqual(
            stock_disponible(ctx, "p1"),
            ib.stock_disponible(data_b, "p1"),
        )
        plan_a = planificar_descuento(ctx, {"p1": 3.0}, nombres={"p1": "Harina"})
        plan_b = ib.planificar_descuento(data_b, {"p1": 3.0}, nombres={"p1": "Harina"})
        self.assertEqual(plan_a.ok, plan_b.ok)
        self.assertEqual(plan_a.lineas[0].salida, plan_b.lineas[0].salida)

        ra = aplicar_descuento_atomico(ctx, {"p1": 4.0})
        rb = ib.aplicar_descuento_atomico(data_b, {"p1": 4.0})
        self.assertEqual(ra.costes["p1"], rb.costes["p1"])
        self.assertEqual(
            [m.lote_id for m in ra.movimientos],
            [m.lote_id for m in rb.movimientos],
        )
        self.assertEqual(
            ib.stock_disponible(data_a, "p1"),
            ib.stock_disponible(data_b, "p1"),
        )

    def test_lote_anulado_fuera_de_fifo(self) -> None:
        data = _datos_fifo()
        data.lotes[1].anulado = True  # l_viejo
        orden = [l.id for l in ib.lotes_ordenados_consumo(data, "p1")]
        self.assertEqual(orden, ["l_medio", "l_nuevo"])


if __name__ == "__main__":
    unittest.main()
