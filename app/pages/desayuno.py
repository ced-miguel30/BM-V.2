"""Desayuno — registro de consumo y merma."""

import streamlit as st

from app.core.services.data_service import get_repository
from app.core.services.formatting import formato_fecha
from app.ui.components import empty_state, page_header, render_sub_tabs, section_divider


def _lineas_desayuno_texto(repo, desayuno) -> str:
    partes = []
    for linea in desayuno.lineas:
        nombre = repo.get_nombre_producto(linea.producto_id)
        partes.append(f"{nombre} ({linea.cantidad})")
    return ", ".join(partes)


def _lineas_merma_texto(repo, merma) -> str:
    partes = []
    for linea in merma.lineas:
        nombre = repo.get_nombre_producto(linea.producto_id)
        partes.append(f"{nombre} ({linea.cantidad}) — {linea.motivo.value}")
    return ", ".join(partes)


def _render_registro_desayuno() -> None:
    repo = get_repository()

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
        productos_disp = [p.nombre for p in repo.data.productos if repo.stock_total_producto(p.id) > 0]
        if productos_disp:
            st.caption(f"Productos disponibles: {', '.join(productos_disp[:5])}{'...' if len(productos_disp) > 5 else ''}")
        else:
            empty_state("No hay productos con stock disponible.", icon="🔍")

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
    st.markdown("#### Historial de desayunos")

    desayunos = repo.desayunos_ordenados()
    if desayunos:
        st.dataframe(
            {
                "Fecha": [formato_fecha(d.fecha) for d in desayunos],
                "Productos": [_lineas_desayuno_texto(repo, d) for d in desayunos],
                "Coste": [repo.formato_precio(d.coste_total) for d in desayunos],
                "Registrado por": [d.registrado_por for d in desayunos],
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        empty_state("No hay registros de desayuno.", icon="📅")


def _render_registro_merma() -> None:
    repo = get_repository()

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

    mermas = repo.mermas_ordenadas()
    if mermas:
        st.dataframe(
            {
                "Fecha": [formato_fecha(m.fecha) for m in mermas],
                "Productos": [_lineas_merma_texto(repo, m) for m in mermas],
                "Coste": [repo.formato_precio(m.coste_total) for m in mermas],
                "Registrado por": [m.registrado_por for m in mermas],
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        empty_state("No hay registros de merma.", icon="📋")


_SUBTABS = {
    "Registro desayuno": _render_registro_desayuno,
    "Registro merma": _render_registro_merma,
}


def render() -> None:
    page_header("Desayuno", "Registro diario de consumo y merma")

    selected = render_sub_tabs(list(_SUBTABS.keys()), key="desayuno_subtab")
    _SUBTABS[selected]()
