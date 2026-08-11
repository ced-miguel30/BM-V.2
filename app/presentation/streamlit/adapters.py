"""Adaptadores que persisten estado temporal en st.session_state."""

from __future__ import annotations

from typing import Any

from app.core.models import AppData
from app.core.storage.demo_files import load_demo_files
from app.core.storage.shared_coordinator import (
    SharedRevisionConflict,
    coordinated_save,
)

APP_DATA_SESSION_KEY = "bm_data"
AUTH_SESSION_KEY = "bm_auth_session"


class StreamlitAppDataStore:
    """AppData espejado en session_state + disco JSON (coordinado)."""

    def get(self) -> AppData:
        import streamlit as st

        if APP_DATA_SESSION_KEY not in st.session_state:
            st.session_state[APP_DATA_SESSION_KEY] = load_demo_files()
        return st.session_state[APP_DATA_SESSION_KEY]

    def persist(self, data: AppData) -> AppData:
        import streamlit as st

        expected = getattr(data, "revision", None)
        try:
            saved = coordinated_save(
                data,
                operation="persist_streamlit",
                expected_revision=expected if expected is not None else None,
            )
        except SharedRevisionConflict:
            self.reload_from_disk()
            raise SharedRevisionConflict(
                "Conflicto de revisión: otro cliente actualizó los datos. "
                "Se recargó desde disco; reintente."
            ) from None
        st.session_state[APP_DATA_SESSION_KEY] = saved
        return saved

    def reload_from_disk(self) -> AppData:
        import streamlit as st

        st.session_state[APP_DATA_SESSION_KEY] = load_demo_files()
        return st.session_state[APP_DATA_SESSION_KEY]


class StreamlitBasketStore:
    def get_list(self, key: str) -> list[Any]:
        import streamlit as st

        if key not in st.session_state:
            st.session_state[key] = []
        return st.session_state[key]

    def set_list(self, key: str, value: list[Any]) -> None:
        import streamlit as st

        st.session_state[key] = value

    def get_counter(self, key: str) -> int:
        import streamlit as st

        return int(st.session_state.get(key, 0))

    def set_counter(self, key: str, value: int) -> None:
        import streamlit as st

        st.session_state[key] = int(value)


class StreamlitAuthSessionStore:
    def get_raw(self) -> dict[str, Any] | None:
        import streamlit as st

        raw = st.session_state.get(AUTH_SESSION_KEY)
        return raw if isinstance(raw, dict) else None

    def set_raw(self, raw: dict[str, Any] | None) -> None:
        import streamlit as st

        if raw is None:
            st.session_state.pop(AUTH_SESSION_KEY, None)
        else:
            st.session_state[AUTH_SESSION_KEY] = raw

    def clear_keys(self, keys: tuple[str, ...]) -> None:
        import streamlit as st

        for k in keys:
            st.session_state.pop(k, None)


class StreamlitIdempotencyStore:
    def _key(self, scope: str) -> str:
        return f"{scope}_clave_idempotencia"

    def get(self, scope: str) -> str | None:
        import streamlit as st

        val = st.session_state.get(self._key(scope))
        return str(val) if val else None

    def set(self, scope: str, token: str) -> None:
        import streamlit as st

        st.session_state[self._key(scope)] = token
