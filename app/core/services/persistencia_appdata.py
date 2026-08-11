"""Persistencia transaccional de AppData sobre un JSON (capa A2).

Todas las mutaciones productivas pasan por el coordinador compartido
(``.bm_shared.lock`` + ``meta.revision``). No hay fallback local.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from app.core.models import AppData
from app.core.storage.json_atomic import AtomicWriteResult, TransactionalUpdateResult
from app.core.storage.shared_coordinator import (
    SharedLockTimeout,
    SharedPathUnavailable,
    SharedWriteAborted,
    coordinated_transactional_update,
)
from app.data.serializers import dict_to_appdata

T = TypeVar("T")


def read_appdata_json(path: Path) -> AppData:
    if not path.exists():
        return AppData()
    return dict_to_appdata(json.loads(path.read_text(encoding="utf-8")))


def transactional_update_appdata(
    path: Path | str,
    mutator: Callable[[AppData], AppData | None],
    *,
    validate: Callable[[AppData], None] | None = None,
    lock_timeout: float = 30.0,
    operation: str = "transactional_update",
) -> TransactionalUpdateResult:
    """Lock compartido → leer fresco → deepcopy → mutar → validar → atomic write.

    Devuelve el nuevo AppData en ``result.state``. No muta instancias previas.
    """
    destination = Path(path)

    def _mutator(working: AppData) -> AppData:
        out = mutator(working)
        return working if out is None else out

    try:
        state = coordinated_transactional_update(
            destination,
            _mutator,
            validate=validate,
            operation=operation,
            timeout=lock_timeout,
        )
    except SharedLockTimeout as exc:
        raise TimeoutError(str(exc)) from exc
    except SharedPathUnavailable:
        raise
    except SharedWriteAborted as exc:
        raise RuntimeError(str(exc)) from exc

    write = AtomicWriteResult(
        path=destination.resolve(),
        replaced=True,
        dir_synced=None,
        durability_note="shared_coordinator",
    )
    return TransactionalUpdateResult(
        path=destination.resolve(), state=state, write=write
    )
