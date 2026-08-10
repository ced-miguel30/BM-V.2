"""Adaptadores en memoria / fichero — sin Streamlit."""

from __future__ import annotations

from typing import Any

from app.core.models import AppData
from app.core.storage.demo_files import load_demo_files, save_demo_files


class FileBackedAppDataStore:
    """Espejo en memoria + JSON vía demo_files. Independiente de UI."""

    def __init__(self, data: AppData | None = None) -> None:
        self._data = data

    def get(self) -> AppData:
        if self._data is None:
            self._data = load_demo_files()
        return self._data

    def persist(self, data: AppData) -> AppData:
        save_demo_files(data)
        self._data = data
        return data

    def reload_from_disk(self) -> AppData:
        self._data = load_demo_files()
        return self._data


class MemoryAppDataStore:
    """Solo memoria (tests). No escribe a disco salvo que se sustituya."""

    def __init__(self, data: AppData) -> None:
        self._data = data

    def get(self) -> AppData:
        return self._data

    def persist(self, data: AppData) -> AppData:
        self._data = data
        return data

    def reload_from_disk(self) -> AppData:
        return self._data


class MemoryBasketStore:
    def __init__(self) -> None:
        self._lists: dict[str, list[Any]] = {}
        self._counters: dict[str, int] = {}

    def get_list(self, key: str) -> list[Any]:
        if key not in self._lists:
            self._lists[key] = []
        return self._lists[key]

    def set_list(self, key: str, value: list[Any]) -> None:
        self._lists[key] = value

    def get_counter(self, key: str) -> int:
        return int(self._counters.get(key, 0))

    def set_counter(self, key: str, value: int) -> None:
        self._counters[key] = int(value)


class MemoryAuthSessionStore:
    def __init__(self) -> None:
        self._raw: dict[str, Any] | None = None
        self._extra: dict[str, Any] = {}

    def get_raw(self) -> dict[str, Any] | None:
        return self._raw

    def set_raw(self, raw: dict[str, Any] | None) -> None:
        self._raw = raw

    def clear_keys(self, keys: tuple[str, ...]) -> None:
        for k in keys:
            self._extra.pop(k, None)


class MemoryIdempotencyStore:
    def __init__(self) -> None:
        self._tokens: dict[str, str] = {}

    def get(self, scope: str) -> str | None:
        return self._tokens.get(scope)

    def set(self, scope: str, token: str) -> None:
        self._tokens[scope] = token
