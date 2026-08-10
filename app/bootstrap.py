"""Composition root reutilizable (Streamlit, tests, futura Flet).

Una sola fuente de AppData por proceso. Sin globals mutables de dominio:
solo el contenedor de composición activo.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.application.adapters.memory_stores import (
    FileBackedAppDataStore,
    MemoryAuthSessionStore,
    MemoryBasketStore,
    MemoryIdempotencyStore,
    MemoryAppDataStore,
)
from app.core.application.clock import Clock, SystemClock
from app.core.application.ports.app_data_store import AppDataStore
from app.core.application.ports.auth_session_store import AuthSessionStore
from app.core.application.ports.basket_store import BasketStore
from app.core.application.ports.idempotency_store import IdempotencyStore
from app.core.models import AppData


@dataclass
class AppContainer:
    """Dependencias de borde de la aplicación."""

    app_data_store: AppDataStore
    basket_store: BasketStore
    auth_session_store: AuthSessionStore
    idempotency_store: IdempotencyStore
    clock: Clock


_container: AppContainer | None = None


def get_container() -> AppContainer:
    """Contenedor activo. Lazy-init file-backed sin Streamlit (tests/scripts)."""
    global _container
    if _container is None:
        _container = build_default_container()
    return _container


def set_container(container: AppContainer | None) -> None:
    """Sustituye o limpia el contenedor (tests)."""
    global _container
    _container = container


def build_default_container(*, clock: Clock | None = None) -> AppContainer:
    """Composición por defecto: JSON file-backed, stores en memoria."""
    return AppContainer(
        app_data_store=FileBackedAppDataStore(),
        basket_store=MemoryBasketStore(),
        auth_session_store=MemoryAuthSessionStore(),
        idempotency_store=MemoryIdempotencyStore(),
        clock=clock or SystemClock(),
    )


def configure_for_streamlit(*, clock: Clock | None = None) -> AppContainer:
    """Composición Streamlit: adaptadores de session_state."""
    from app.presentation.streamlit.adapters import (
        StreamlitAppDataStore,
        StreamlitAuthSessionStore,
        StreamlitBasketStore,
        StreamlitIdempotencyStore,
    )

    container = AppContainer(
        app_data_store=StreamlitAppDataStore(),
        basket_store=StreamlitBasketStore(),
        auth_session_store=StreamlitAuthSessionStore(),
        idempotency_store=StreamlitIdempotencyStore(),
        clock=clock or SystemClock(),
    )
    set_container(container)
    return container


def configure_for_tests(
    data: AppData | None = None,
    *,
    persist_to_disk: bool = False,
    clock: Clock | None = None,
) -> AppContainer:
    """Composición de tests: memoria (o file-backed si persist_to_disk)."""
    if persist_to_disk:
        store: AppDataStore = FileBackedAppDataStore(data)
        if data is not None:
            store.persist(data)
    else:
        from app.data.mock_data import crear_datos_mock

        store = MemoryAppDataStore(data if data is not None else crear_datos_mock())
    container = AppContainer(
        app_data_store=store,
        basket_store=MemoryBasketStore(),
        auth_session_store=MemoryAuthSessionStore(),
        idempotency_store=MemoryIdempotencyStore(),
        clock=clock or SystemClock(),
    )
    set_container(container)
    return container


def reset_container() -> None:
    """Elimina el contenedor activo (siguiente get_container lazy-init)."""
    set_container(None)
