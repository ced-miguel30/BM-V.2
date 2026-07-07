"""Almacenamiento temporal en memoria (session_state de Streamlit)."""

import streamlit as st

from app.core.models import AppData
from app.data.mock_data import crear_datos_mock

SESSION_KEY = "bm_data"


def init_data() -> AppData:
    """Inicializa los datos mock en la sesión si aún no existen."""
    if SESSION_KEY not in st.session_state:
        st.session_state[SESSION_KEY] = crear_datos_mock()
    return st.session_state[SESSION_KEY]


def get_data() -> AppData:
    """Devuelve los datos actuales de la aplicación."""
    return init_data()


def reset_data() -> AppData:
    """Reinicia los datos a los valores mock originales."""
    st.session_state[SESSION_KEY] = crear_datos_mock()
    return st.session_state[SESSION_KEY]
