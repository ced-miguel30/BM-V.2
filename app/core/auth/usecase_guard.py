"""Autorización en frontera de casos de uso (F18).

Solo para entry points públicos. No usar en helpers FIFO/cálculo/serializers.
La autorización deriva exclusivamente de AuthSession válida (F16).
"""

from __future__ import annotations

from app.core.auth.permissions import AuthorizationError, Permiso
from app.core.auth.session import (
    TERMINAL_INVENTARIO_ID,
    AuthSession,
    require_permiso,
)


class UseCaseDenied(AuthorizationError):
    """Rechazo de caso de uso público."""


# Mutaciones con deny_terminal=True que el Terminal Inventario sí puede ejecutar
# (ajuste/alertas y demas entrypoints de inventario operativo). Restaurante y
# terminales genericos/historicos siguen bloqueados. Economica/config/compras
# siguen denegadas por session_tiene_permiso / matriz de terminal_id.
_PERMISOS_PERMITIDOS_TERMINAL_INVENTARIO_CON_DENY = frozenset({
    Permiso.ACCEDER_INVENTARIO,
    Permiso.ACCEDER_TERMINAL_INVENTARIO,
})


def _deny_terminal_blocks(session: AuthSession, permiso: Permiso | str) -> bool:
    """True si deny_terminal debe rechazar esta sesion para el permiso."""
    if session.actor_type != "terminal":
        return False
    p = Permiso(permiso) if not isinstance(permiso, Permiso) else permiso
    if (
        session.terminal_id == TERMINAL_INVENTARIO_ID
        and p in _PERMISOS_PERMITIDOS_TERMINAL_INVENTARIO_CON_DENY
    ):
        return False
    return True


def require_usecase(
    permiso: Permiso | str,
    *,
    deny_terminal: bool = False,
) -> AuthSession:
    """Exige AuthSession autenticada con el permiso indicado.

    ``deny_terminal`` bloquea actores terminal salvo Terminal Inventario cuando
    el permiso es de inventario operativo (ACCEDER_INVENTARIO /
    ACCEDER_TERMINAL_INVENTARIO). Compras, config, gestor y costes siguen
    denegados por la matriz de ``terminal_id``.
    """
    session = require_permiso(permiso)
    if deny_terminal and _deny_terminal_blocks(session, permiso):
        raise UseCaseDenied("Terminal no autorizado para esta operación.")
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
