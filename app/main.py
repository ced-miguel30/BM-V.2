"""Punto de entrada — Breakfast Management."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.core.storage.session_store import init_data
from app.pages import analisis, dashboard, desayuno, settings, stock
from app.ui.components import render_sidebar
from app.ui.styles import inject_global_styles
from app.ui.theme import APP_NAME

PAGES = {
    "dashboard": dashboard.render,
    "desayuno": desayuno.render,
    "stock": stock.render,
    "analisis": analisis.render,
    "settings": settings.render,
}


def main() -> None:
    st.set_page_config(
        page_title=APP_NAME,
        page_icon="☕",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_global_styles()
    init_data()

    section = render_sidebar()
    PAGES[section]()


if __name__ == "__main__":
    main()
