"""Terminal Inventario — stock operativo sin costes ni administración."""

from __future__ import annotations

import streamlit as st

from app.core.auth.permissions import Permiso
from app.core.auth.session import get_auth_session, session_tiene_permiso
from app.pages import caducidad
from app.pages.desayuno import render_registro_merma
from app.ui.components import page_header, render_sub_tabs


def render() -> None:
    if not session_tiene_permiso(Permiso.ACCEDER_TERMINAL_INVENTARIO) and not session_tiene_permiso(
        Permiso.ACCEDER_INVENTARIO
    ):
        st.error("No autorizado.")
        return

    st.session_state["bm_force_hide_costes"] = True

    session = get_auth_session()
    label = session.actor_label if session else "Inventario"
    page_header(
        "Terminal Inventario",
        f"Operaciones de stock · identidad: {label} (sin precios ni compras)",
    )
    st.info(
        "Modo terminal: merma, caducidad, alertas y ajustes. "
        "No se muestran costes económicos ni configuración."
    )

    sub = render_sub_tabs(
        ["Alertas", "Caducidad", "Merma", "Ajustes"],
        key="terminal_inv_subtab",
    )
    if sub == "Alertas":
        from app.pages.stock import _render_alertas_stock
        _render_alertas_stock()
    elif sub == "Caducidad":
        caducidad.render_caducidad_workbench(mostrar_cabecera=False)
    elif sub == "Merma":
        render_registro_merma()
    else:
        from app.pages.stock import _render_ajustes_inventario
        _render_ajustes_inventario()
