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
    """UoW sobre el AppDataStore del composition root.

    El nombre histórico se conserva; ya no implica Streamlit por sí mismo.
    """

    def get_data(self) -> AppData:
        from app.bootstrap import get_container

        return get_container().app_data_store.get()

    def commit(self, data: AppData | None = None) -> AppData:
        from app.bootstrap import get_container

        store = get_container().app_data_store
        payload = data if data is not None else store.get()
        return store.persist(payload)
