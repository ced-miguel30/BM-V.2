"""Fase 3 — fronteras de aplicación: contexto, UoW, lectura de productos.

Ejecutar:

    py -m unittest tests.test_app_context_fase3 -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application.actor import actor_desde_appdata
from app.core.application.auditoria import registrar_actividad
from app.core.application.clock import FixedClock
from app.core.application.context import build_app_context
from app.core.application.id_generator import next_id
from app.core.application.producto_queries import (
    listar_productos,
    mapa_productos_nombre_id,
    obtener_producto,
)
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import AppData, Producto, RolUsuario, UnidadProducto, Usuario
from app.core.repositories.data_repository import DataRepository


def _datos() -> AppData:
    return AppData(
        productos=[
            Producto("p02", "Leche", UnidadProducto.L, es_bebida=False),
            Producto("p01", "Agua", UnidadProducto.L, es_bebida=True),
            Producto("p03", "Jarabe", UnidadProducto.L, es_bebida=True),
        ],
        usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


class TestAppContextFase3(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _datos()
        self.uow = InMemoryUnitOfWork(self.data)
        self.clock = FixedClock(datetime(2026, 8, 3, 12, 0, 0))
        self.ctx = build_app_context(
            uow=self.uow,
            clock=self.clock,
            actor=actor_desde_appdata(self.data),
        )

    def test_next_id_compatible(self) -> None:
        self.assertEqual(next_id("p", ["p01", "p02"]), "p03")
        self.assertEqual(next_id("l", []), "l01")

    def test_actor_desde_datos(self) -> None:
        self.assertEqual(self.ctx.actor.id, "u01")
        self.assertEqual(self.ctx.actor.nombre, "Ana")

    def test_clock_fijo(self) -> None:
        self.assertEqual(self.ctx.clock.today().isoformat(), "2026-08-03")

    def test_obtener_producto(self) -> None:
        p = obtener_producto(self.ctx, "p01")
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.nombre, "Agua")
        self.assertIsNone(obtener_producto(self.ctx, "nope"))

    def test_listar_filtra_bebida(self) -> None:
        bebidas = listar_productos(self.ctx, es_bebida=True)
        self.assertEqual([p.id for p in bebidas], ["p01", "p03"])  # Agua, Jarabe
        no_bebidas = listar_productos(self.ctx, es_bebida=False)
        self.assertEqual([p.id for p in no_bebidas], ["p02"])
        todos = listar_productos(self.ctx)
        self.assertEqual(len(todos), 3)

    def test_mapa_nombre_id(self) -> None:
        mapa = mapa_productos_nombre_id(self.ctx, es_bebida=None)
        self.assertEqual(mapa["Agua"], "p01")
        self.assertEqual(mapa["Leche"], "p02")
        self.assertEqual(mapa["Jarabe"], "p03")

    def test_equivalencia_con_data_repository(self) -> None:
        repo = DataRepository(self.data)
        for pid in ("p01", "p02"):
            a = obtener_producto(self.ctx, pid)
            b = repo.get_producto(pid)
            self.assertEqual(a.id if a else None, b.id if b else None)
            self.assertEqual(a.nombre if a else None, b.nombre if b else None)

    def test_auditoria_sin_commit_no_rompe(self) -> None:
        act = registrar_actividad(self.ctx, "Prueba", "detalle fase 3", commit=False)
        self.assertTrue(act.id.startswith("act"))
        self.assertEqual(act.usuario, "Ana")
        self.assertEqual(self.data.actividades[0].id, act.id)
        self.assertEqual(act.fecha_hora, self.clock.now())


if __name__ == "__main__":
    unittest.main()
