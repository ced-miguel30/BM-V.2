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
    bebida_service,
    cena_service,
    comida_service,
    consumo_service,
    desayuno_service,
    merma_service,
    stock_service,
)
from app.core.services.alert_service import sincronizar_alertas
from app.core.services.exportacion_semanal_service import procesar_pendientes
from app.pages import analisis, dashboard, recetas, registros, settings, stock
from app.ui.components import render_sidebar
from app.ui.styles import inject_global_styles
from app.ui.theme import APP_NAME, APP_VERSION

PAGES = {
    "dashboard": dashboard.render,
    "registros": registros.render,
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
        bebida_service.configuracion_exportacion(), ahora,
        fecha_mas_antigua=bebida_service.fecha_mas_antigua(),
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
    from app.bootstrap import configure_for_streamlit

    configure_for_streamlit()
    st.set_page_config(
        page_title=f"{APP_NAME} · {APP_VERSION}",
        page_icon="☕",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_global_styles()
    init_data()

    from app.pages.auth_gate import render_auth_gate

    if not render_auth_gate():
        return

    from app.core.auth.permissions import Permiso
    from app.core.auth.session import get_auth_session, session_tiene_permiso

    session = get_auth_session()
    # Recepción: módulo pendiente
    if session and session.role == "recepcion":
        st.warning("Módulo de Recepción pendiente de implementación.")
        st.info(f"Sesión: {session.actor_label}. Acceso limitado.")
        from app.pages.auth_gate import render_logout_sidebar

        with st.sidebar:
            render_logout_sidebar()
        return

    # Terminal inventario (antes que el catch-all restaurante/terminal)
    if session and session.terminal_id == "terminal_inventario":
        if not (
            session_tiene_permiso(Permiso.ACCEDER_TERMINAL_INVENTARIO)
            or session_tiene_permiso(Permiso.ACCEDER_INVENTARIO)
        ):
            st.error("No autorizado.")
            return
        from app.pages import terminal_inventario
        from app.pages.auth_gate import render_logout_sidebar

        st.session_state["bm_force_hide_costes"] = True
        with st.sidebar:
            st.caption("Terminal Inventario")
            render_logout_sidebar()
        terminal_inventario.render()
        return

    # Terminal restaurante: UI dedicada
    if session and (
        session.actor_type == "terminal"
        or session.role == "restaurante"
    ):
        if not session_tiene_permiso(Permiso.ACCEDER_REGISTRO):
            st.error("No autorizado.")
            return
        from app.pages import terminal_restaurante
        from app.pages.auth_gate import render_logout_sidebar

        st.session_state.pop("bm_force_hide_costes", None)
        with st.sidebar:
            st.caption("Terminal Restaurante")
            render_logout_sidebar()
        terminal_restaurante.render()
        return

    sincronizar_alertas()
    _procesar_exportaciones_semanales_pendientes()

    section = render_sidebar()
    # Defensa en profundidad: sección no autorizada → remap
    from app.core.auth.permissions import puede_ver_seccion
    from app.ui.theme import NAV_SECTIONS

    label_by_key = {v: k for k, v in NAV_SECTIONS.items()}
    label = label_by_key.get(section, "Dashboard")
    if session and not puede_ver_seccion(session.role, label):
        st.session_state["nav_section"] = "Registros" if session_tiene_permiso(
            Permiso.ACCEDER_REGISTRO
        ) else "Dashboard"
        st.warning("Destino no autorizado; redirigido a una zona permitida.")
        st.rerun()
        return

    PAGES[section]()


if __name__ == "__main__":
    main()
