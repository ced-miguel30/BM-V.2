"""B5 — autorización Terminal Inventario vs deny_terminal."""

from __future__ import annotations

import unittest
from datetime import date

from app.core.auth.permissions import AuthorizationError, Permiso
from app.core.auth.roles import ROL_ADMINISTRACION, ROL_DIRECCION, ROL_RESTAURANTE
from app.core.auth.session import (
    AuthSession,
    clear_test_session,
    iniciar_terminal_inventario,
    iniciar_terminal_restaurante,
    session_tiene_permiso,
    set_test_session,
)
from app.core.auth.usecase_guard import UseCaseDenied, require_usecase, usecase_deny_message
from app.core.services import ajuste_service, costes_service
from tests.auth_harness import HARNESS_SESSION, restore_harness_session


def _terminal_generico() -> AuthSession:
    """Actor terminal historico/generico sin terminal_id de inventario."""
    return AuthSession(
        authenticated=True,
        actor_type="terminal",
        actor_id="terminal_legacy",
        actor_label="Legacy",
        role=ROL_ADMINISTRACION,
        session_id="legacy-t",
        login_at="2026-01-01T00:00:00",
        terminal_id="terminal_desconocido",
        login=None,
    )


class TestB5DenyTerminalInventario(unittest.TestCase):
    def tearDown(self) -> None:
        restore_harness_session()

    def test_restaurante_sigue_bloqueado_en_ajustes(self) -> None:
        clear_test_session()
        set_test_session(iniciar_terminal_restaurante())
        denied = usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
        self.assertIsNotNone(denied)
        with self.assertRaises(AuthorizationError):
            require_usecase(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)

    def test_inventario_puede_mutar_inventario_operativo(self) -> None:
        clear_test_session()
        set_test_session(iniciar_terminal_inventario())
        session = require_usecase(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
        self.assertEqual(session.terminal_id, "terminal_inventario")
        self.assertIsNone(
            usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
        )

    def test_inventario_no_consulta_costes_ni_gestor(self) -> None:
        clear_test_session()
        set_test_session(iniciar_terminal_inventario())
        self.assertFalse(session_tiene_permiso(Permiso.CONSULTAR_COSTES))
        self.assertFalse(session_tiene_permiso(Permiso.ACCEDER_GESTOR))
        with self.assertRaises(AuthorizationError):
            require_usecase(Permiso.CONSULTAR_COSTES)
        with self.assertRaises(AuthorizationError):
            costes_service.resumen_periodo(date(2026, 7, 1), date(2026, 7, 31), [])

    def test_inventario_puede_compras_y_config_maestros(self) -> None:
        clear_test_session()
        set_test_session(iniciar_terminal_inventario())
        self.assertTrue(session_tiene_permiso(Permiso.ACCEDER_COMPRAS_DOCUMENTOS))
        self.assertTrue(session_tiene_permiso(Permiso.ACCEDER_CONFIGURACION))
        self.assertIsNone(
            usecase_deny_message(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)
        )
        self.assertIsNone(
            usecase_deny_message(Permiso.ACCEDER_CONFIGURACION, deny_terminal=True)
        )
        require_usecase(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)
        require_usecase(Permiso.ACCEDER_CONFIGURACION, deny_terminal=True)

    def test_terminal_generico_no_recibe_permisos_nuevos(self) -> None:
        clear_test_session()
        set_test_session(_terminal_generico())
        # Aunque el rol sea administracion, deny_terminal sigue bloqueando
        # actores terminal que no son terminal_inventario.
        with self.assertRaises(UseCaseDenied):
            require_usecase(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)

    def test_direccion_y_admin_personal_conservan_comportamiento(self) -> None:
        clear_test_session()
        set_test_session(HARNESS_SESSION)
        self.assertEqual(
            require_usecase(Permiso.ACCEDER_INVENTARIO, deny_terminal=True).role,
            ROL_DIRECCION,
        )
        clear_test_session()
        set_test_session(
            AuthSession(
                authenticated=True,
                actor_type="usuario",
                actor_id="adm1",
                actor_label="Admin",
                role=ROL_ADMINISTRACION,
                session_id="a1",
                login_at="2026-01-01T00:00:00",
                login="adm",
            )
        )
        self.assertIsNone(
            usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
        )

    def test_restaurante_personal_sin_inventario(self) -> None:
        clear_test_session()
        set_test_session(
            AuthSession(
                authenticated=True,
                actor_type="usuario",
                actor_id="r1",
                actor_label="Rest",
                role=ROL_RESTAURANTE,
                session_id="r1",
                login_at="2026-01-01T00:00:00",
                login="rest",
            )
        )
        self.assertIsNotNone(
            usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=False)
        )


if __name__ == "__main__":
    unittest.main()
