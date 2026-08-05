"""Sesión Auth de harness para tests de dominio (F18).

Producción nunca importa este módulo. Los tests F18 que prueban rechazo
llaman ``clear_test_session()`` y deben restaurar el harness al terminar.
"""

from __future__ import annotations

from app.core.auth.session import AuthSession, set_test_session

HARNESS_SESSION = AuthSession(
    authenticated=True,
    actor_type="usuario",
    actor_id="test_harness_dir",
    actor_label="Test Dirección",
    role="direccion",
    session_id="test-harness-session",
    login_at="2026-01-01T00:00:00",
    login="test_harness_dir",
)


def restore_harness_session() -> None:
    set_test_session(HARNESS_SESSION)
