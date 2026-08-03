"""Fase 4E — registro desayuno / servicio vía AppContext.

Ejecutar:

    py -m unittest tests.test_fase4e_registro -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.application.actor import Actor
from app.core.application.clock import FixedClock
from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import (
    AppData,
    CategoriaReceta,
    LoteStock,
    Producto,
    RolUsuario,
    UnidadProducto,
    Usuario,
)
from app.core.services import desayuno_service
from app.core.services.cesta_service import LineaCesta
from app.core.services.servicio_registro_service import ServicioRegistro


def _datos() -> AppData:
    return AppData(
        productos=[
            Producto(
                "p1", "Pan", UnidadProducto.UD,
                servicios_disponibles=["desayuno", "comida"],
            ),
        ],
        lotes=[
            LoteStock(
                "l1", "p1",
                precio_total=10.0,
                cantidad=20.0,
                cantidad_restante=20.0,
                fecha_compra=date(2026, 7, 1),
            ),
        ],
        usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


def _ctx(data: AppData):
    return build_app_context(
        uow=InMemoryUnitOfWork(data),
        clock=FixedClock(datetime(2026, 7, 30, 8, 0, 0)),
        actor=Actor(id="u01", nombre="Ana", rol="Admin"),
    )


class TestFase4ERegistro(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _datos()
        self.ctx = _ctx(self.data)
        self._session: dict = {}
        self._st = mock.patch("streamlit.session_state", self._session)
        self._st.start()

    def tearDown(self) -> None:
        self._st.stop()

    def test_registrar_desayuno_via_contexto(self) -> None:
        self._session[desayuno_service.CESTA_SESSION_KEY] = [
            LineaCesta(linea_id="c1", producto_id="p1", nombre="Pan", unidad="Ud", cantidad=2.0),
        ]
        self._session[desayuno_service.CESTA_RECETAS_KEY] = []
        r = desayuno_service.registrar_desayuno(
            date(2026, 7, 28), 10, ctx=self.ctx,
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(self.data.lotes[0].cantidad_restante, 18.0)
        self.assertEqual(len(self.data.desayunos), 1)
        self.assertEqual(self.data.desayunos[0].registrado_por, "Ana")
        self.assertEqual(self.data.actividades[0].accion, "Registro desayuno")
        self.assertTrue(self.data.desayunos[0].lineas_detalle)

    def test_registrar_comida_via_contexto(self) -> None:
        motor = ServicioRegistro(
            "comida",
            "fase4e_comida",
            [CategoriaReceta.COMIDA],
        )
        self.assertTrue(motor.anadir_a_cesta("p1", 3.0, ctx=self.ctx).ok)
        r = motor.registrar(date(2026, 7, 28), ctx=self.ctx)
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(self.data.lotes[0].cantidad_restante, 17.0)
        self.assertEqual(len(self.data.registros_servicio), 1)
        self.assertEqual(self.data.registros_servicio[0].tipo_servicio, "comida")
        self.assertEqual(self.data.registros_servicio[0].registrado_por, "Ana")

    def test_fecha_futura_desayuno_bloqueada(self) -> None:
        self._session[desayuno_service.CESTA_SESSION_KEY] = [
            LineaCesta(linea_id="c1", producto_id="p1", nombre="Pan", unidad="Ud", cantidad=1.0),
        ]
        self._session[desayuno_service.CESTA_RECETAS_KEY] = []
        r = desayuno_service.registrar_desayuno(date(2026, 8, 5), 5, ctx=self.ctx)
        self.assertFalse(r.ok)
        self.assertIn("futur", r.mensaje.lower())


if __name__ == "__main__":
    unittest.main()
