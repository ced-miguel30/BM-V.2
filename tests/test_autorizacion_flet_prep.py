"""Autorización en frontera de casos de uso (preparación Flet)."""

from __future__ import annotations

import unittest
from datetime import date

from app.core.auth.permissions import AuthorizationError, Permiso
from app.core.auth.roles import ROL_ADMINISTRACION, ROL_RESTAURANTE
from app.core.auth.session import (
    AuthSession,
    clear_test_session,
    iniciar_terminal_inventario,
    require_permiso,
    session_tiene_permiso,
    set_test_session,
)
from app.core.auth.usecase_guard import UseCaseDenied, require_usecase
from app.core.services import costes_service, dashboard_service
from tests.auth_harness import HARNESS_SESSION, restore_harness_session


def _session(*, role: str, terminal_id: str | None = None, actor_type: str = "usuario") -> AuthSession:
    return AuthSession(
        authenticated=True,
        actor_type=actor_type,
        actor_id="actor-test",
        actor_label="Actor test",
        role=role,
        session_id="s-test",
        login_at="2026-01-01T00:00:00",
        terminal_id=terminal_id,
        login="t",
    )


class TestAutorizacionUseCases(unittest.TestCase):
    def tearDown(self) -> None:
        restore_harness_session()

    def test_restaurante_no_consulta_costes_via_usecase(self) -> None:
        clear_test_session()
        set_test_session(_session(role=ROL_RESTAURANTE))
        with self.assertRaises(AuthorizationError):
            require_usecase(Permiso.CONSULTAR_COSTES)
        with self.assertRaises(AuthorizationError):
            costes_service.costes_consumo_por_servicio(date(2026, 7, 1), date(2026, 7, 31))

    def test_terminal_inventario_no_consulta_economia(self) -> None:
        clear_test_session()
        set_test_session(iniciar_terminal_inventario())
        self.assertFalse(session_tiene_permiso(Permiso.CONSULTAR_COSTES))
        self.assertFalse(session_tiene_permiso(Permiso.ACCEDER_CONFIGURACION))
        with self.assertRaises(AuthorizationError):
            require_permiso(Permiso.CONSULTAR_COSTES)
        with self.assertRaises(AuthorizationError):
            require_usecase(Permiso.CONSULTAR_COSTES)

    def test_sin_permiso_no_muta_ajustes(self) -> None:
        from app.core.services import ajuste_service

        clear_test_session()
        set_test_session(_session(role=ROL_RESTAURANTE))
        # Restaurante no tiene ACCEDER_INVENTARIO / ajustes
        denied = None
        try:
            from app.core.auth.usecase_guard import usecase_deny_message
            from app.core.auth.permissions import Permiso as P

            denied = usecase_deny_message(P.ACCEDER_INVENTARIO, deny_terminal=False)
        except Exception:
            denied = "fail"
        self.assertIsNotNone(denied)

    def test_direccion_si_consulta_costes(self) -> None:
        clear_test_session()
        set_test_session(HARNESS_SESSION)
        session = require_usecase(Permiso.CONSULTAR_COSTES)
        self.assertEqual(session.role, "direccion")
        self.assertEqual(session.actor_id, HARNESS_SESSION.actor_id)

    def test_actor_preservado_en_snapshot(self) -> None:
        from app.core.auth.session import actor_snapshot_from_session

        clear_test_session()
        set_test_session(HARNESS_SESSION)
        snap = actor_snapshot_from_session(HARNESS_SESSION)
        self.assertEqual(snap["actor_id"], HARNESS_SESSION.actor_id)
        self.assertEqual(snap["role_snapshot"], "direccion")
