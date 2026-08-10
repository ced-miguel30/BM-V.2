"""Puente de sesión Flet → AuthSessionStore / actor (contratos existentes)."""

from __future__ import annotations

from app.core.auth.permissions import Permiso
from app.core.auth.session import (
    AuthSession,
    get_auth_session,
    iniciar_terminal_inventario,
    iniciar_terminal_restaurante,
    logout as auth_logout,
    save_auth_session,
    session_tiene_permiso,
)
from app.core.application.actor import Actor, actor_desde_auth_session
from app.presentation.flet.mappers import map_acceso_denegado
from app.presentation.flet.viewmodels import FeedbackVM, SessionVM


def session_to_vm(session: AuthSession | None, *, mensaje: str = "") -> SessionVM:
    if session is None or not session.authenticated:
        return SessionVM(authenticated=False, mensaje=mensaje)
    return SessionVM(
        authenticated=True,
        actor_label=session.actor_label,
        actor_id=session.actor_id,
        role=session.role,
        terminal_id=session.terminal_id,
        mensaje=mensaje,
    )


def current_session_vm() -> SessionVM:
    return session_to_vm(get_auth_session())


def current_actor() -> Actor | None:
    return actor_desde_auth_session()


def enter_terminal_restaurante() -> tuple[SessionVM, FeedbackVM | None]:
    """Entra como actor terminal restaurante si hay permiso efectivo."""
    session = iniciar_terminal_restaurante()
    save_auth_session(session)
    if not (
        session_tiene_permiso(Permiso.ACCEDER_TERMINAL_RESTAURANTE)
        or session_tiene_permiso(Permiso.ACCEDER_REGISTRO)
    ):
        auth_logout()
        fb = map_acceso_denegado("Falta permiso de acceso al terminal.")
        return session_to_vm(None, mensaje=fb.mensaje), fb
    return session_to_vm(session), None


def enter_terminal_inventario() -> tuple[SessionVM, FeedbackVM | None]:
    """Entra como actor terminal inventario si hay permiso efectivo."""
    session = iniciar_terminal_inventario()
    save_auth_session(session)
    if not (
        session_tiene_permiso(Permiso.ACCEDER_TERMINAL_INVENTARIO)
        or session_tiene_permiso(Permiso.ACCEDER_INVENTARIO)
    ):
        auth_logout()
        fb = map_acceso_denegado("Falta permiso de acceso al Terminal Inventario.")
        return session_to_vm(None, mensaje=fb.mensaje), fb
    return session_to_vm(session), None


def deny_foreign_role(role: str) -> tuple[SessionVM, FeedbackVM]:
    """Simula intento de acceso sin rol adecuado (tests / denegación)."""
    fb = map_acceso_denegado(f"El rol '{role}' no puede operar este terminal.")
    return session_to_vm(None, mensaje=fb.mensaje), fb


def logout_terminal() -> SessionVM:
    auth_logout()
    return session_to_vm(None, mensaje="Sesión cerrada.")


def puede_usar_terminal() -> bool:
    return session_tiene_permiso(Permiso.ACCEDER_TERMINAL_RESTAURANTE) or session_tiene_permiso(
        Permiso.ACCEDER_REGISTRO
    )


def puede_usar_terminal_inventario() -> bool:
    return session_tiene_permiso(Permiso.ACCEDER_TERMINAL_INVENTARIO) or session_tiene_permiso(
        Permiso.ACCEDER_INVENTARIO
    )
