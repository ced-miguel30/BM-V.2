"""Punto de entrada — Breakfast Management."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.core.storage.session_store import init_data
from app.core.services.alert_service import sincronizar_alertas
from app.pages import analisis, dashboard, desayuno, settings, stock
from app.ui.components import render_sidebar
from app.ui.styles import inject_global_styles
from app.ui.theme import APP_NAME, APP_VERSION

PAGES = {
    "dashboard": dashboard.render,
    "desayuno": desayuno.render,
    "stock": stock.render,
    "analisis": analisis.render,
    "settings": settings.render,
}


def main() -> None:
    st.set_page_config(
        page_title=f"{APP_NAME} · {APP_VERSION}",
        page_icon="☕",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_global_styles()
    init_data()
    sincronizar_alertas()

    if "bm_abrir_exportacion" not in st.session_state:
        st.session_state["nav_section"] = "Settings"
        st.session_state["settings_subtab"] = "Exportación"
        st.session_state["bm_abrir_exportacion"] = True

    section = render_sidebar()
    PAGES[section]()


if __name__ == "__main__":
    main()
