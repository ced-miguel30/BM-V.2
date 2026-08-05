"""Autorización en frontera de casos de uso (F18).

Solo para entry points públicos. No usar en helpers FIFO/cálculo/serializers.
La autorización deriva exclusivamente de AuthSession válida (F16).
"""

from __future__ import annotations

from app.core.auth.permissions import AuthorizationError, Permiso
from app.core.auth.session import AuthSession, require_permiso


class UseCaseDenied(AuthorizationError):
    """Rechazo de caso de uso público."""


def require_usecase(
    permiso: Permiso | str,
    *,
    deny_terminal: bool = False,
) -> AuthSession:
    """Exige AuthSession autenticada con el permiso indicado.

    ``deny_terminal`` bloquea actor_type=terminal aunque el rol tenga el permiso
    (compras, ajustes, anulaciones administrativas, etc.).
    """
    session = require_permiso(permiso)
    if deny_terminal and session.actor_type == "terminal":
        raise UseCaseDenied("Terminal Restaurante no autorizado para esta operación.")
    return session


def usecase_deny_message(
    permiso: Permiso | str,
    *,
    deny_terminal: bool = False,
) -> str | None:
    """None si autorizado; mensaje de error si no (para ResultadoOperacion)."""
    try:
        require_usecase(permiso, deny_terminal=deny_terminal)
        return None
    except AuthorizationError as exc:
        return getattr(exc, "mensaje", None) or str(exc) or "No autorizado."
