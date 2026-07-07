"""Desayuno — registro de consumo y merma."""

import streamlit as st

from app.ui.components import empty_state, page_header, render_sub_tabs, section_divider


def _render_registro_desayuno() -> None:
    st.markdown("#### Registro rápido de desayuno")
    st.caption("Seleccione productos y añádalos a la cesta para registrar el consumo del día.")

    col_buscar, col_cesta = st.columns([2, 1])

    with col_buscar:
        st.text_input(
            "Buscar producto",
            placeholder="Escriba el nombre del producto...",
            disabled=True,
            key="desayuno_buscar",
        )
        st.date_input("Fecha", disabled=True, key="desayuno_fecha")
        empty_state(
            "Busque un producto para añadirlo a la cesta. "
            "La funcionalidad estará disponible en Fase 6.",
            icon="🔍",
        )

    with col_cesta:
        st.markdown(
            """
            <div class="bm-basket-panel">
                <div class="bm-basket-title">Cesta del desayuno</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        empty_state("La cesta está vacía", icon="🧺")
        st.button("Registrar desayuno", type="primary", disabled=True, use_container_width=True, key="btn_registrar_desayuno")

    section_divider()
    st.markdown("#### Historial del día")
    empty_state("No hay registros de desayuno para hoy.", icon="📅")


def _render_registro_merma() -> None:
    st.markdown("#### Registro de merma")
    st.caption("Registre productos perdidos por merma, expiración u otros motivos.")

    col_buscar, col_cesta = st.columns([2, 1])

    with col_buscar:
        st.text_input(
            "Buscar producto",
            placeholder="Escriba el nombre del producto...",
            disabled=True,
            key="merma_buscar",
        )
        st.date_input("Fecha", disabled=True, key="merma_fecha")
        st.selectbox(
            "Motivo",
            ["Merma", "Expiración", "Producto malo", "Producto abierto", "Otro"],
            disabled=True,
            key="merma_motivo",
        )
        st.text_area("Comentario (opcional)", disabled=True, key="merma_comentario")
        empty_state(
            "Busque un producto para registrar merma. "
            "La funcionalidad estará disponible en Fase 7.",
            icon="🔍",
        )

    with col_cesta:
        st.markdown(
            """
            <div class="bm-basket-panel">
                <div class="bm-basket-title">Cesta de merma</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        empty_state("La cesta está vacía", icon="🧺")
        st.button("Registrar merma", type="primary", disabled=True, use_container_width=True, key="btn_registrar_merma")

    section_divider()
    st.markdown("#### Historial de merma")
    empty_state("No hay registros de merma para mostrar.", icon="📋")


_SUBTABS = {
    "Registro desayuno": _render_registro_desayuno,
    "Registro merma": _render_registro_merma,
}


def render() -> None:
    page_header("Desayuno", "Registro diario de consumo y merma")

    selected = render_sub_tabs(list(_SUBTABS.keys()), key="desayuno_subtab")
    _SUBTABS[selected]()
