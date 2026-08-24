"""Autorización en frontera de casos de uso (F18).

Solo para entry points públicos. No usar en helpers FIFO/cálculo/serializers.
La autorización deriva exclusivamente de AuthSession válida (F16).
"""

from __future__ import annotations

from collections.abc import Collection

from app.core.auth.permissions import AuthorizationError, Permiso
from app.core.auth.session import (
    TERMINAL_INVENTARIO_ID,
    AuthSession,
    require_permiso,
)


class UseCaseDenied(AuthorizationError):
    """Rechazo de caso de uso público."""


# Mutaciones con deny_terminal=True que el Terminal Inventario sí puede ejecutar.
# Incluye economato (compras/documentos + maestros vía ACCEDER_CONFIGURACION).
# Restaurante y terminales genéricos/históricos siguen bloqueados.
_PERMISOS_PERMITIDOS_TERMINAL_INVENTARIO_CON_DENY = frozenset({
    Permiso.ACCEDER_INVENTARIO,
    Permiso.ACCEDER_TERMINAL_INVENTARIO,
    Permiso.ACCEDER_COMPRAS_DOCUMENTOS,
    Permiso.ACCEDER_CONFIGURACION,
})


def _deny_terminal_blocks(
    session: AuthSession,
    permiso: Permiso | str,
    *,
    allowed_terminals: Collection[str] | None = None,
) -> bool:
    """True si deny_terminal debe rechazar esta sesion para el permiso."""
    if session.actor_type != "terminal":
        return False
    p = Permiso(permiso) if not isinstance(permiso, Permiso) else permiso
    if (
        session.terminal_id == TERMINAL_INVENTARIO_ID
        and p in _PERMISOS_PERMITIDOS_TERMINAL_INVENTARIO_CON_DENY
    ):
        return False
    # Excepción explícita por llamada (p. ej. anulación Restaurante).
    # No altera el comportamiento por defecto cuando allowed_terminals es None/vacío.
    if allowed_terminals and session.terminal_id in allowed_terminals:
        return False
    return True


def require_usecase(
    permiso: Permiso | str,
    *,
    deny_terminal: bool = False,
    allowed_terminals: Collection[str] | None = None,
) -> AuthSession:
    """Exige AuthSession autenticada con el permiso indicado.

    ``deny_terminal`` bloquea actores terminal salvo:

    - Terminal Inventario cuando el permiso está en la allowlist de economato
      (inventario operativo, compras/documentos, configuración de maestros); o
    - un ``terminal_id`` listado explícitamente en ``allowed_terminals``
      para **esta** llamada (el permiso sigue siendo obligatorio).

    Sin ``allowed_terminals``, el comportamiento es idéntico al histórico
    salvo la allowlist de Terminal Inventario. Gestor y costes siguen
    denegados por la matriz de ``terminal_id`` / permisos de rol.
    """
    session = require_permiso(permiso)
    if deny_terminal and _deny_terminal_blocks(
        session, permiso, allowed_terminals=allowed_terminals
    ):
        raise UseCaseDenied("Terminal no autorizado para esta operación.")
    return session


def usecase_deny_message(
    permiso: Permiso | str,
    *,
    deny_terminal: bool = False,
    allowed_terminals: Collection[str] | None = None,
) -> str | None:
    """None si autorizado; mensaje de error si no (para ResultadoOperacion)."""
    try:
        require_usecase(
            permiso,
            deny_terminal=deny_terminal,
            allowed_terminals=allowed_terminals,
        )
    except AuthorizationError as exc:
        return getattr(exc, "mensaje", None) or str(exc) or "No autorizado."
    return None
