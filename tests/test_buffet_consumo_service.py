"""Tests de buffet_consumo_service."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BM_TEST_ISOLATION", "1")

from app.core.auth.session import AuthSession, set_test_session

from app.core.application.actor import Actor
from app.core.application.clock import FixedClock
from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import (
    AppData,
    LoteStock,
    Producto,
    ResponsableMerma,
    RolUsuario,
    UnidadProducto,
    Usuario,
)
from app.core.models.buffet import (
    MOTIVO_BUFFET_CONSUMO,
    MOTIVO_BUFFET_MERMA,
    TIPO_LINEA_SIMPLE,
    LineaConfigBuffet,
)
from app.core.services.buffet_consumo_service import (
    LineaBuffetEntrada,
    importar_lineas_buffet,
)
from tests.demo_isolation import EXPORT_SESSION_MODULES, isolated_persist

_TEST_MODULES = EXPORT_SESSION_MODULES + (
    "app.core.services.desayuno_service",
    "app.core.services.merma_service",
    "app.core.services.buffet_consumo_service",
    "app.core.storage.session_store",
)


def _datos() -> AppData:
    return AppData(
        productos=[
            Producto("p1", "Pan", UnidadProducto.UD, servicios_disponibles=["desayuno"]),
            Producto("b06", "Naranja", UnidadProducto.KG, servicios_disponibles=["desayuno"]),
            Producto("b28", "Zumo bote", UnidadProducto.UD, servicios_disponibles=["desayuno"]),
        ],
        lotes=[
            LoteStock("l1", "p1", 10.0, 10.0, 10.0, date(2026, 7, 1)),
            LoteStock("l2", "b06", 5.0, 5.0, 5.0, date(2026, 7, 1)),
            LoteStock("l3", "b28", 4.0, 4.0, 4.0, date(2026, 7, 1)),
        ],
        config_buffet=[
            LineaConfigBuffet(
                "cb1", "Pan", 1, "Pan gallego", "p1", "Ud", 1.0,
                tipo_linea=TIPO_LINEA_SIMPLE,
            ),
            LineaConfigBuffet(
                "cb2", "Jarras", 2, "Jarra zumo naranja", "b06", "Ud", 1.0,
                tipo_linea="jarra_zumo", producto_bote_id="b28",
            ),
        ],
        responsables_merma=[ResponsableMerma("rm01", "Ana", True)],
        usuarios=[Usuario("u01", "Admin", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


class TestBuffetConsumoService(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _datos()
        self._session: dict = {}
        self._st = mock.patch("streamlit.session_state", self._session)
        self._st.start()
        from tests.streamlit_store_harness import cleanup_container, use_patched_streamlit_stores

        use_patched_streamlit_stores()
        self.addCleanup(cleanup_container)
        self._iso = isolated_persist(*_TEST_MODULES, data=self.data)
        self._iso.__enter__()
        self.addCleanup(self._iso.__exit__, None, None, None)
        self._cesta_get = mock.patch(
            "app.core.services.cesta_service.get_data", return_value=self.data,
        )
        self._cesta_get.start()
        self.addCleanup(self._cesta_get.stop)
        set_test_session(
            AuthSession(
                authenticated=True,
                actor_type="usuario",
                actor_id="u01",
                actor_label="Admin",
                role="direccion",
                session_id="test",
                login_at=datetime(2026, 1, 1).isoformat(),
                login="admin",
            )
        )

        self.ctx = build_app_context(
            uow=InMemoryUnitOfWork(self.data),
            clock=FixedClock(datetime(2026, 8, 31, 8, 0, 0)),
            actor=Actor(id="u01", nombre="Admin", rol="Admin"),
        )

    def tearDown(self) -> None:
        self._st.stop()

    def test_import_consumo_registra_desayuno_y_buffet(self) -> None:
        r = importar_lineas_buffet(
            date(2026, 8, 10),
            [
                LineaBuffetEntrada(None, "Pan gallego", "Pan", 2.0, MOTIVO_BUFFET_CONSUMO),
            ],
            ctx=self.ctx,
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(len(self.data.desayunos), 1)
        self.assertEqual(len(self.data.registros_buffet), 1)

    def test_import_merma_crea_merma(self) -> None:
        r = importar_lineas_buffet(
            date(2026, 8, 10),
            [
                LineaBuffetEntrada(None, "Pan gallego", "Pan", 1.0, MOTIVO_BUFFET_MERMA),
            ],
            ctx=self.ctx,
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(len(self.data.mermas), 1)
        self.assertEqual(len(self.data.registros_buffet), 1)

    def test_jarra_naranja_y_bote(self) -> None:
        r = importar_lineas_buffet(
            date(2026, 8, 11),
            [
                LineaBuffetEntrada(
                    None, "Jarra zumo naranja", "Jarras", 1.0, MOTIVO_BUFFET_CONSUMO,
                    naranjas=0.5, zumo_bote=1.0,
                ),
            ],
            ctx=self.ctx,
        )
        self.assertTrue(r.ok, r.mensaje)
        pids = {ln.producto_id for d in self.data.desayunos for ln in d.lineas}
        self.assertIn("b06", pids)
        self.assertIn("b28", pids)

    def test_idempotencia(self) -> None:
        lineas = [LineaBuffetEntrada(None, "Pan gallego", "Pan", 1.0, MOTIVO_BUFFET_CONSUMO)]
        r1 = importar_lineas_buffet(date(2026, 8, 12), lineas, ctx=self.ctx)
        r2 = importar_lineas_buffet(date(2026, 8, 12), lineas, ctx=self.ctx)
        self.assertTrue(r1.ok, r1.mensaje)
        self.assertTrue(r2.skipped, r2.mensaje)


if __name__ == "__main__":
    unittest.main()
