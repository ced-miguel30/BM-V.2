"""Persistencia transaccional de AppData sobre un JSON (capa A2)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from app.core.models import AppData
from app.core.storage.json_atomic import TransactionalUpdateResult, transactional_update
from app.data.serializers import appdata_to_dict, dict_to_appdata

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
) -> TransactionalUpdateResult:
    """Lock → leer fresco → deepcopy → mutar → validar → atomic write.

    Devuelve el nuevo AppData en ``result.state``. No muta instancias previas.
    """
    destination = Path(path)

    def _mutator(working: AppData) -> AppData:
        out = mutator(working)
        return working if out is None else out

    return transactional_update(
        destination,
        mutator=_mutator,
        reader=read_appdata_json,
        validate=validate,
        to_dict=appdata_to_dict,
        lock_timeout=lock_timeout,
        default_factory=AppData,
    )
