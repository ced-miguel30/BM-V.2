"""Stock — productos y alertas."""

import streamlit as st

from app.core.models import TipoAlerta
from app.core.services.data_service import get_repository
from app.core.services.formatting import formato_fecha, formato_moneda
from app.ui.components import empty_state, page_header, render_sub_tabs, section_divider


def _render_registro_producto() -> None:
    repo = get_repository()

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
        opciones = ["— Seleccione un producto —"] + [p.nombre for p in repo.data.productos]
        col1, col2 = st.columns(2)
        with col1:
            st.selectbox("Producto", opciones, disabled=True, key="lote_producto")
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

    if repo.data.productos:
        filas = []
        for p in repo.data.productos:
            stock = repo.stock_total_producto(p.id)
            filas.append({
                "Producto": p.nombre,
                "Unidad": p.unidad.value,
                "Stock actual": stock,
                "Stock mínimo": p.stock_minimo if p.stock_minimo is not None else "—",
            })
        st.dataframe(filas, use_container_width=True, hide_index=True)
    else:
        empty_state("No hay productos registrados.", icon="📦")

    section_divider()
    st.markdown("#### Lotes registrados")

    if repo.data.lotes:
        filas = []
        for lote in repo.data.lotes:
            filas.append({
                "Producto": repo.get_nombre_producto(lote.producto_id),
                "Cantidad": lote.cantidad,
                "Restante": lote.cantidad_restante,
                "Precio total": formato_moneda(lote.precio_total, repo.get_simbolo_moneda()),
                "Compra": formato_fecha(lote.fecha_compra),
                "Expiración": formato_fecha(lote.fecha_expiracion),
                "Proveedor": lote.marca_proveedor or "—",
            })
        st.dataframe(filas, use_container_width=True, hide_index=True)
    else:
        empty_state("No hay lotes registrados.", icon="🏷️")


def _render_alertas_stock() -> None:
    repo = get_repository()

    st.markdown("#### Estado de alertas")
    st.caption("Productos con stock bajo, sin stock, próximos a expirar y alertas manuales.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Stock bajo")
        stock_bajo = repo.productos_stock_bajo()
        if stock_bajo:
            for producto, stock in stock_bajo:
                st.markdown(f"- **{producto.nombre}** — {stock} {producto.unidad.value}")
        else:
            empty_state("Sin productos con stock bajo.", icon="⚠️")

    with col2:
        st.markdown("##### Stock cero")
        agotados = repo.productos_stock_cero()
        if agotados:
            for producto in agotados:
                st.markdown(f"- **{producto.nombre}**")
        else:
            empty_state("Sin productos agotados.", icon="🚫")

    section_divider()

    col3, col4 = st.columns(2)
    with col3:
        st.markdown("##### Próximos a expirar")
        proximos = repo.lotes_proximos_expirar()
        if proximos:
            for item in proximos:
                st.markdown(
                    f"- **{item['producto']}** — expira en {item['dias']} días "
                    f"({formato_fecha(item['lote'].fecha_expiracion)})"
                )
        else:
            empty_state("Sin productos próximos a expirar.", icon="⏰")

    with col4:
        st.markdown("##### Alertas manuales")
        manuales = repo.alertas_por_tipo(TipoAlerta.MANUAL)
        if manuales:
            for alerta in manuales:
                st.markdown(f"- **{alerta.titulo}** — {alerta.mensaje}")
        else:
            empty_state("Sin alertas manuales creadas.", icon="✋")

    section_divider()
    st.markdown("#### Generar alerta manual")
    opciones = ["— Seleccione un producto —"] + [p.nombre for p in repo.data.productos]
    with st.form("form_alerta_manual", clear_on_submit=False):
        st.selectbox("Producto", opciones, disabled=True, key="alerta_producto")
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
