"""Aislamiento de tests respecto a data/demo/datos_hotel.json (Fase A1).

Arquitectura:
- El aislamiento **principal** lo aporta cada test (TemporaryDirectory,
  ``isolated_persist``, ``InMemoryUnitOfWork``, patch local).
- La red de seguridad es ``BM_TEST_ISOLATION=1`` en ``save_json`` /
  ``delete_demo_files`` (ruta canónica resuelta). No neutraliza persistencia:
  solo rechaza escrituras al demo real.
- Este módulo **no** instala monkeypatches globales al importarse.
"""

from __future__ import annotations

import os
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Iterator

from app.core.models import AppData

_PROTECTED_DEMO = (
    Path(__file__).resolve().parent.parent / "data" / "demo" / "datos_hotel.json"
).resolve()

EXPORT_SESSION_MODULES = (
    "app.core.services.exportacion_semanal_service",
)

_ENV_FLAG = "BM_TEST_ISOLATION"


def protected_demo_path() -> Path:
    return _PROTECTED_DEMO


def enable_test_isolation_env() -> str | None:
    """Activa BM_TEST_ISOLATION. Devuelve el valor previo (o None)."""
    previous = os.environ.get(_ENV_FLAG)
    os.environ[_ENV_FLAG] = "1"
    return previous


def restore_test_isolation_env(previous: str | None) -> None:
    """Restaura BM_TEST_ISOLATION al valor previo."""
    if previous is None:
        os.environ.pop(_ENV_FLAG, None)
    else:
        os.environ[_ENV_FLAG] = previous


@contextmanager
def isolation_env_active() -> Iterator[None]:
    """Context manager: BM_TEST_ISOLATION=1 solo durante el bloque."""
    previous = enable_test_isolation_env()
    try:
        yield
    finally:
        restore_test_isolation_env(previous)


@contextmanager
def isolated_persist(
    *module_paths: str,
    data: AppData | None = None,
) -> Iterator[AppData]:
    """Parchea get_data/persist_data en módulos de servicio (aislamiento local).

    Los patches se restauran al salir del ``with`` (ExitStack).
    """
    from unittest.mock import patch

    store = data if data is not None else AppData()

    def _persist(payload: AppData | None = None) -> AppData:
        return payload if payload is not None else store

    with ExitStack() as stack:
        for mod in module_paths:
            stack.enter_context(patch(f"{mod}.get_data", return_value=store))
            stack.enter_context(patch(f"{mod}.persist_data", side_effect=_persist))
        yield store
