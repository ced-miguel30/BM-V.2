"""Punto de entrada — Breakfast Management."""

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.core.storage.session_store import init_data
from app.core.services import (
    actividad_service,
    cena_service,
    comida_service,
    consumo_service,
    desayuno_service,
    merma_service,
    stock_service,
)
from app.core.services.alert_service import sincronizar_alertas
from app.core.services.exportacion_semanal_service import procesar_pendientes
from app.pages import analisis, cena, comida, dashboard, desayuno, recetas, settings, stock
from app.ui.components import render_sidebar
from app.ui.styles import inject_global_styles
from app.ui.theme import APP_NAME, APP_VERSION

PAGES = {
    "dashboard": dashboard.render,
    "desayuno": desayuno.render,
    "comida": comida.render,
    "cena": cena.render,
    "recetas": recetas.render,
    "stock": stock.render,
    "analisis": analisis.render,
    "settings": settings.render,
}


def _procesar_exportaciones_semanales_pendientes() -> None:
    """Exporta automáticamente a Excel cualquier semana ya cerrada (lunes a
    domingo) que todavía no se haya exportado. Idempotente: se puede llamar en
    cada arranque sin generar archivos ni actividades duplicadas."""
    ahora = datetime.now()
    procesar_pendientes(
        desayuno_service.configuracion_exportacion(), ahora,
        fecha_mas_antigua=desayuno_service.fecha_mas_antigua(),
    )
    procesar_pendientes(
        comida_service.configuracion_exportacion(), ahora,
        fecha_mas_antigua=comida_service.fecha_mas_antigua(),
    )
    procesar_pendientes(
        cena_service.configuracion_exportacion(), ahora,
        fecha_mas_antigua=cena_service.fecha_mas_antigua(),
    )
    procesar_pendientes(
        merma_service.configuracion_exportacion(), ahora,
        fecha_mas_antigua=merma_service.fecha_mas_antigua(),
    )
    procesar_pendientes(
        stock_service.configuracion_exportacion(es_bebida=False), ahora,
        fecha_mas_antigua=stock_service.fecha_mas_antigua(es_bebida=False),
    )
    procesar_pendientes(
        stock_service.configuracion_exportacion(es_bebida=True), ahora,
        fecha_mas_antigua=stock_service.fecha_mas_antigua(es_bebida=True),
    )
    procesar_pendientes(
        consumo_service.configuracion_exportacion(), ahora,
        fecha_mas_antigua=consumo_service.fecha_mas_antigua(),
    )
    procesar_pendientes(
        actividad_service.configuracion_exportacion(), ahora,
        fecha_mas_antigua=actividad_service.fecha_mas_antigua(),
    )


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

    _procesar_exportaciones_semanales_pendientes()

    section = render_sidebar()
    PAGES[section]()


if __name__ == "__main__":
    main()
