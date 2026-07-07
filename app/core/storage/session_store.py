"""Almacenamiento: sesión + archivo JSON en data/demo/."""

import streamlit as st

from app.core.models import AppData
from app.core.storage.demo_files import DEMO_FILE, load_demo_files, save_demo_files

SESSION_KEY = "bm_data"


def init_data() -> AppData:
    if SESSION_KEY not in st.session_state:
        st.session_state[SESSION_KEY] = load_demo_files()
    return st.session_state[SESSION_KEY]


def get_data() -> AppData:
    return init_data()


def persist_data(data: AppData) -> AppData:
    """Guarda en disco y actualiza la sesión."""
    save_demo_files(data)
    st.session_state[SESSION_KEY] = data
    return data


def reset_data() -> AppData:
    from app.data.mock_data import crear_datos_mock

    data = crear_datos_mock()
    return persist_data(data)


def reload_from_disk() -> AppData:
    st.session_state[SESSION_KEY] = load_demo_files()
    return st.session_state[SESSION_KEY]


def get_demo_path() -> str:
    return str(DEMO_FILE)
