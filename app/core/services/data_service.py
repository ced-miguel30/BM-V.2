"""Acceso al repositorio de datos."""

from app.core.repositories.data_repository import DataRepository
from app.core.storage.session_store import get_data


def get_repository() -> DataRepository:
    """Devuelve el repositorio conectado a los datos de sesión."""
    return DataRepository(get_data())
