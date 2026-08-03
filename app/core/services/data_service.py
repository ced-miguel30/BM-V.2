"""Acceso al repositorio de datos y contexto de aplicación (Fase 3)."""

from app.core.application.context import AppContext, build_app_context
from app.core.repositories.data_repository import DataRepository
from app.core.storage.session_store import get_data


def get_repository() -> DataRepository:
    """Devuelve el repositorio conectado a los datos de sesión."""
    return DataRepository(get_data())


def get_app_context() -> AppContext:
    """Contexto de operación (UoW JSON/sesión + actor + reloj).

    No cambia el comportamiento visible. Piloto para desacople (Fase 3–4).
    `session_store` sigue siendo la fuente detrás del UoW.
    """
    return build_app_context()
