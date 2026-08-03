"""Unidad de trabajo sobre AppData (JSON / memoria)."""

from __future__ import annotations

from typing import Protocol

from app.core.models import AppData


class UnitOfWork(Protocol):
    def get_data(self) -> AppData: ...

    def commit(self, data: AppData | None = None) -> AppData: ...


class InMemoryUnitOfWork:
    """UoW para tests: no toca disco ni Streamlit."""

    def __init__(self, data: AppData) -> None:
        self._data = data

    def get_data(self) -> AppData:
        return self._data

    def commit(self, data: AppData | None = None) -> AppData:
        if data is not None:
            self._data = data
        return self._data


class JsonSessionUnitOfWork:
    """Adaptador temporal: delega en session_store (sin eliminarlo)."""

    def get_data(self) -> AppData:
        from app.core.storage.session_store import get_data

        return get_data()

    def commit(self, data: AppData | None = None) -> AppData:
        from app.core.storage.session_store import get_data, persist_data

        payload = data if data is not None else get_data()
        return persist_data(payload)
