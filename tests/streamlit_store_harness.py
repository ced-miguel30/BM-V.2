"""Helpers de composition para tests (stores sin/con Streamlit)."""

from __future__ import annotations

from app.bootstrap import (
    build_default_container,
    configure_for_streamlit,
    reset_container,
    set_container,
)


def fresh_memory_container() -> None:
    """Contenedor limpio en memoria (cestas vacías) para tests vía API."""
    set_container(build_default_container())


def use_patched_streamlit_stores() -> None:
    """Instala composition Streamlit (lee el session_state ya parcheado)."""
    configure_for_streamlit()


def cleanup_container() -> None:
    reset_container()
