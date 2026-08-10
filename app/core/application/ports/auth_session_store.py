"""Puerto de sesión de autenticación (sin UI)."""

from __future__ import annotations

from typing import Any, Protocol


class AuthSessionStore(Protocol):
    """Persistencia temporal de la AuthSession activa."""

    def get_raw(self) -> dict[str, Any] | None:
        """Dict serializado de sesión o None."""

    def set_raw(self, raw: dict[str, Any] | None) -> None:
        """Guarda o borra la sesión."""

    def clear_keys(self, keys: tuple[str, ...]) -> None:
        """Elimina claves auxiliares de UI al logout (si existen)."""
