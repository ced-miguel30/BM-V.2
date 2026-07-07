"""Stock — productos y alertas."""

import pandas as pd
import streamlit as st

from app.core.models import TipoAlerta
from app.core.services.data_service import get_repository
from app.core.services.formatting import formato_fecha, formato_moneda
from app.core.services.stock_service import UNIDADES, crear_producto, mapa_productos, registrar_lote
from app.ui.components import empty_state, page_header, render_sub_tabs, section_divider


def _render_registro_producto() -> None:
    repo = get_repository()

    with st.expander("Crear producto", expanded=True):
        st.markdown("##### Nuevo producto")
        with st.form("form_crear_producto", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                nombre = st.text_input("Nombre del producto", placeholder="Ej: Croissant")
                unidad = st.selectbox("Unidad", UNIDADES)
            with col2:
                stock_min = st.number_input(
                    "Stock mínimo (opcional)",
                    min_value=0.0,
                    value=0.0,
                    step=1.0,
                    help="Deje 0 si no desea definir stock mínimo.",
                )
            enviado = st.form_submit_button("Crear producto", type="primary")
            if enviado:
                resultado = crear_producto(nombre, unidad, stock_min if stock_min > 0 else None)
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)

    with st.expander("Registrar lote / compra"):
        st.markdown("##### Nuevo lote")
        productos_map = mapa_productos(repo.data)
        if not productos_map:
            st.warning("Primero debe crear al menos un producto.")
        else:
            nombres = list(productos_map.keys())
            with st.form("form_registrar_lote", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    producto_nombre = st.selectbox("Producto", nombres)
                    usar_compra = st.checkbox("Usar fecha de compra", value=False)
                    fecha_compra_val = st.date_input("Fecha de compra", key="lote_fecha_compra")
                    usar_exp = st.checkbox("Usar fecha de expiración", value=False)
                    fecha_exp_val = st.date_input("Fecha de expiración", key="lote_fecha_exp")
                with col2:
                    precio = st.number_input("Precio total", min_value=0.0, value=0.0, step=0.01, format="%.2f")
                    cantidad = st.number_input("Cantidad", min_value=0.0, value=0.0, step=0.1, format="%.2f")
                    proveedor = st.text_input("Marca / proveedor (opcional)")
                    alerta_dias = st.number_input(
                        "Alerta de expiración en X días (opcional)",
                        min_value=0,
                        value=0,
                        step=1,
                    )
                enviado = st.form_submit_button("Registrar lote", type="primary")
                if enviado:
                    resultado = registrar_lote(
                        producto_id=productos_map[producto_nombre],
                        precio_total=precio,
                        cantidad=cantidad,
                        fecha_compra=fecha_compra_val if usar_compra else None,
                        fecha_expiracion=fecha_exp_val if usar_exp else None,
                        marca_proveedor=proveedor,
                        alerta_expiracion_dias=alerta_dias if alerta_dias > 0 else None,
                    )
                    if resultado.ok:
                        st.success(resultado.mensaje)
                        st.rerun()
                    else:
                        st.error(resultado.mensaje)

    section_divider()
    st.markdown("#### Productos registrados")

    if repo.data.productos:
        filas = []
        for p in sorted(repo.data.productos, key=lambda x: x.nombre):
            stock = repo.stock_total_producto(p.id)
            filas.append({
                "ID": p.id,
                "Producto": p.nombre,
                "Unidad": p.unidad.value,
                "Stock actual": stock,
                "Stock mínimo": p.stock_minimo if p.stock_minimo is not None else "—",
            })
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
    else:
        empty_state("No hay productos registrados.", icon="📦")

    section_divider()
    st.markdown("#### Lotes registrados")

    if repo.data.lotes:
        filas = []
        for lote in repo.data.lotes:
            filas.append({
                "ID": lote.id,
                "Producto": repo.get_nombre_producto(lote.producto_id),
                "Cantidad": lote.cantidad,
                "Restante": lote.cantidad_restante,
                "Precio total": formato_moneda(lote.precio_total, repo.get_simbolo_moneda()),
                "Compra": formato_fecha(lote.fecha_compra),
                "Expiración": formato_fecha(lote.fecha_expiracion),
                "Proveedor": lote.marca_proveedor or "—",
            })
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
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
    st.caption("Disponible en Fase 5.")


_SUBTABS = {
    "Registro producto": _render_registro_producto,
    "Alertas stock": _render_alertas_stock,
}


def render() -> None:
    page_header("Stock", "Gestión de productos, lotes y alertas de inventario")

    selected = render_sub_tabs(list(_SUBTABS.keys()), key="stock_subtab")
    _SUBTABS[selected]()
