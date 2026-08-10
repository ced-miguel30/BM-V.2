"""Puerto de tokens de idempotencia de confirmación (sin UI)."""

from __future__ import annotations

from typing import Protocol


class IdempotencyStore(Protocol):
    """Tokens anti doble-confirmación por ámbito (p. ej. prefijo de registro)."""

    def get(self, scope: str) -> str | None:
        """Token actual o None."""

    def set(self, scope: str, token: str) -> None:
        """Fija el token del ámbito."""
