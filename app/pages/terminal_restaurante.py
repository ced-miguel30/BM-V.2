"""Terminal Restaurante — registros operativos sin costes ni administración."""

from __future__ import annotations

import streamlit as st

from app.core.auth.permissions import Permiso
from app.core.auth.session import get_auth_session, session_tiene_permiso
from app.pages import bebidas, cena, comida, desayuno
from app.ui.components import page_header, render_sub_tabs

_SUBTABS = {
    "Desayuno": lambda: desayuno.render_registro_desayuno(),
    "Comida": lambda: comida.render(mostrar_cabecera=False),
    "Cena": lambda: cena.render(mostrar_cabecera=False),
    "Bebidas": lambda: bebidas.render(mostrar_cabecera=False),
    "Merma": lambda: desayuno.render_registro_merma(),
}


def render() -> None:
    if not session_tiene_permiso(Permiso.ACCEDER_TERMINAL_RESTAURANTE) and not session_tiene_permiso(
        Permiso.ACCEDER_REGISTRO
    ):
        st.error("No autorizado.")
        return

    session = get_auth_session()
    label = session.actor_label if session else "Restaurante"
    page_header(
        "Terminal Restaurante",
        f"Registro operativo · identidad: {label} (sin precios ni configuración)",
    )
    st.info("No se muestran costes, compras ni administración en este modo.")
    selected = render_sub_tabs(list(_SUBTABS.keys()), key="terminal_rest_subtab")
    _SUBTABS[selected]()
