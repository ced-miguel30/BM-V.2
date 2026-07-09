"""Punto de entrada — Breakfast Management."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.core.storage.session_store import init_data
from app.core.services.alert_service import sincronizar_alertas
from app.core.services.historial_compras_service import archivar_historial_semanal, debe_archivar_semanal
from app.pages import analisis, dashboard, desayuno, recetas, settings, stock
from app.ui.components import render_sidebar
from app.ui.styles import inject_global_styles
from app.ui.theme import APP_NAME, APP_VERSION

PAGES = {
    "dashboard": dashboard.render,
    "desayuno": desayuno.render,
    "recetas": recetas.render,
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

    if debe_archivar_semanal():
        archivar_historial_semanal()

    section = render_sidebar()
    PAGES[section]()


if __name__ == "__main__":
    main()
