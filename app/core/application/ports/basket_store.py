"""Puerto de almacén de borradores de cesta (sin UI)."""

from __future__ import annotations

from typing import Any, Protocol


class BasketStore(Protocol):
    """Almacén temporal de listas y contadores de cesta."""

    def get_list(self, key: str) -> list[Any]:
        """Obtiene una lista; crea vacía si no existe."""

    def set_list(self, key: str, value: list[Any]) -> None:
        """Sustituye la lista completa."""

    def get_counter(self, key: str) -> int:
        """Contador entero (default 0)."""

    def set_counter(self, key: str, value: int) -> None:
        """Actualiza el contador."""
