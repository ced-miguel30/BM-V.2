"""Fase 4D — merma vía AppContext.

Ejecutar:

    py -m unittest tests.test_fase4d_merma -v
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
    LoteStock,
    MotivoMerma,
    Producto,
    ResponsableMerma,
    RolUsuario,
    UnidadProducto,
    Usuario,
)
from app.core.services import merma_service
from app.core.services.merma_service import LineaCestaMerma


def _datos() -> AppData:
    return AppData(
        productos=[Producto("p1", "Pan", UnidadProducto.UD)],
        lotes=[
            LoteStock(
                "l1", "p1",
                precio_total=10.0,
                cantidad=10.0,
                cantidad_restante=10.0,
                fecha_compra=date(2026, 7, 1),
            ),
        ],
        responsables_merma=[ResponsableMerma("rm01", "Ana", True)],
        usuarios=[Usuario("u01", "Admin", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


def _ctx(data: AppData):
    return build_app_context(
        uow=InMemoryUnitOfWork(data),
        clock=FixedClock(datetime(2026, 7, 30, 9, 0, 0)),
        actor=Actor(id="u01", nombre="Admin", rol="Admin"),
    )


class TestFase4DMerma(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _datos()
        self.ctx = _ctx(self.data)
        self._session: dict = {}
        self._st = mock.patch("streamlit.session_state", self._session)
        self._st.start()

    def tearDown(self) -> None:
        self._st.stop()

    def test_crear_responsable_via_contexto(self) -> None:
        r = merma_service.crear_responsable_merma("Luis", ctx=self.ctx)
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(len(self.data.responsables_merma), 2)
        self.assertEqual(self.data.actividades[0].accion, "Responsable merma")

    def test_registrar_merma_via_contexto(self) -> None:
        self._session[merma_service.CESTA_MERMA_KEY] = [
            LineaCestaMerma(
                lote_id="l1",
                producto_id="p1",
                nombre="Pan",
                unidad="Ud",
                fecha_compra_txt="01/07/2026",
                cantidad=2.0,
                motivo=MotivoMerma.EXPIRACION.value,
                tipo_servicio_snapshot="general",
                turno_snapshot="manana",
                responsable_id="rm01",
                responsable_nombre="Ana",
            ),
        ]
        r = merma_service.registrar_merma(date(2026, 7, 28), ctx=self.ctx)
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(self.data.lotes[0].cantidad_restante, 8.0)
        self.assertEqual(len(self.data.mermas), 1)
        self.assertEqual(self.data.mermas[0].registrado_por, "Admin")
        self.assertEqual(self.data.actividades[0].accion, "Registro merma")
        self.assertEqual(self._session[merma_service.CESTA_MERMA_KEY], [])

    def test_fecha_futura_bloqueada(self) -> None:
        self._session[merma_service.CESTA_MERMA_KEY] = [
            LineaCestaMerma(
                lote_id="l1",
                producto_id="p1",
                nombre="Pan",
                unidad="Ud",
                fecha_compra_txt="01/07/2026",
                cantidad=1.0,
                motivo=MotivoMerma.EXPIRACION.value,
                tipo_servicio_snapshot="general",
                turno_snapshot="manana",
                responsable_id="rm01",
                responsable_nombre="Ana",
            ),
        ]
        r = merma_service.registrar_merma(date(2026, 8, 5), ctx=self.ctx)
        self.assertFalse(r.ok)
        self.assertIn("futur", r.mensaje.lower())


if __name__ == "__main__":
    unittest.main()
