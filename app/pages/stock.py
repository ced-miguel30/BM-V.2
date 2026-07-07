"""Stock — productos y alertas."""

import streamlit as st

from app.ui.components import empty_state, page_header, render_sub_tabs, section_divider


def _render_registro_producto() -> None:
    with st.expander("Crear producto", expanded=True):
        st.markdown("##### Nuevo producto")
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("Nombre del producto", disabled=True, key="prod_nombre")
            st.selectbox(
                "Unidad",
                ["Ud", "L", "gr", "Kg", "Otro"],
                disabled=True,
                key="prod_unidad",
            )
        with col2:
            st.number_input(
                "Stock mínimo (opcional)",
                min_value=0.0,
                value=0.0,
                disabled=True,
                key="prod_stock_min",
            )
        st.button("Crear producto", disabled=True, key="btn_crear_producto")

    with st.expander("Registrar lote / compra"):
        st.markdown("##### Nuevo lote")
        col1, col2 = st.columns(2)
        with col1:
            st.selectbox(
                "Producto",
                ["— Seleccione un producto —"],
                disabled=True,
                key="lote_producto",
            )
            st.date_input("Fecha de compra (opcional)", disabled=True, key="lote_compra")
            st.date_input("Fecha de expiración (opcional)", disabled=True, key="lote_exp")
        with col2:
            st.number_input("Precio total", min_value=0.0, value=0.0, disabled=True, key="lote_precio")
            st.number_input("Cantidad", min_value=0.0, value=0.0, disabled=True, key="lote_cantidad")
            st.text_input("Marca / proveedor (opcional)", disabled=True, key="lote_proveedor")
            st.number_input(
                "Alerta de expiración en X días (opcional)",
                min_value=0,
                value=0,
                disabled=True,
                key="lote_alerta_dias",
            )
        st.button("Registrar lote", disabled=True, key="btn_registrar_lote")

    section_divider()
    st.markdown("#### Productos registrados")
    empty_state(
        "No hay productos registrados. Podrá crearlos en Fase 4.",
        icon="📦",
    )

    section_divider()
    st.markdown("#### Lotes registrados")
    empty_state(
        "No hay lotes registrados.",
        icon="🏷️",
    )


def _render_alertas_stock() -> None:
    st.markdown("#### Estado de alertas")
    st.caption("Productos con stock bajo, sin stock, próximos a expirar y alertas manuales.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Stock bajo")
        empty_state("Sin productos con stock bajo.", icon="⚠️")
    with col2:
        st.markdown("##### Stock cero")
        empty_state("Sin productos agotados.", icon="🚫")

    section_divider()

    col3, col4 = st.columns(2)
    with col3:
        st.markdown("##### Próximos a expirar")
        empty_state("Sin productos próximos a expirar.", icon="⏰")
    with col4:
        st.markdown("##### Alertas manuales")
        empty_state("Sin alertas manuales creadas.", icon="✋")

    section_divider()
    st.markdown("#### Generar alerta manual")
    with st.form("form_alerta_manual", clear_on_submit=False):
        st.selectbox(
            "Producto",
            ["— Seleccione un producto —"],
            disabled=True,
            key="alerta_producto",
        )
        st.text_input("Motivo", disabled=True, key="alerta_motivo")
        st.number_input("Días hasta alerta", min_value=0, value=0, disabled=True, key="alerta_dias")
        st.text_area("Comentario (opcional)", disabled=True, key="alerta_comentario")
        st.form_submit_button("Generar alerta", disabled=True)

    st.caption("La creación de alertas estará disponible en Fase 5.")


_SUBTABS = {
    "Registro producto": _render_registro_producto,
    "Alertas stock": _render_alertas_stock,
}


def render() -> None:
    page_header("Stock", "Gestión de productos, lotes y alertas de inventario")

    selected = render_sub_tabs(list(_SUBTABS.keys()), key="stock_subtab")
    _SUBTABS[selected]()
