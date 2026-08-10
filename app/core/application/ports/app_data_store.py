"""Puerto de acceso a AppData (sin UI)."""

from __future__ import annotations

from typing import Protocol

from app.core.models import AppData


class AppDataStore(Protocol):
    """Fuente única de AppData para la composición activa."""

    def get(self) -> AppData:
        """Devuelve el AppData en memoria de la composición."""

    def persist(self, data: AppData) -> AppData:
        """Persiste y actualiza el espejo en memoria."""

    def reload_from_disk(self) -> AppData:
        """Recarga desde el fichero JSON efectivo."""
