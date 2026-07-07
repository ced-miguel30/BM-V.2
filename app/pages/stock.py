"""Stock — productos y alertas."""

from datetime import date

import pandas as pd
import streamlit as st

from app.core.models import TipoAlerta
from app.core.services.alert_service import (
    alertas_stock_activas,
    crear_alerta_manual,
    resolver_alerta,
    sincronizar_alertas,
)
from app.core.services.data_service import get_repository
from app.core.services.formatting import formato_fecha, formato_moneda
from app.core.services.stock_service import UNIDADES, crear_producto, mapa_productos, registrar_lote
from app.ui.components import empty_state, page_header, render_sub_tabs, section_divider

_TIPO_ETIQUETA = {
    TipoAlerta.STOCK_BAJO: "Stock bajo",
    TipoAlerta.STOCK_CERO: "Stock cero",
    TipoAlerta.EXPIRACION_PROXIMA: "Expiración próxima",
    TipoAlerta.EXPIRADO: "Expirado",
    TipoAlerta.MANUAL: "Manual",
}


def _render_inventario(repo) -> None:
    st.markdown("#### Inventario")
    st.caption("Stock total por producto. Las compras se registran por lote pero se muestran agregadas aquí.")

    if repo.data.productos:
        filas = []
        for p in sorted(repo.data.productos, key=lambda x: x.nombre):
            stock = repo.stock_total_producto(p.id)
            filas.append({
                "Producto": p.nombre,
                "Unidad": p.unidad.value,
                "Stock actual": stock,
                "Stock mínimo": p.stock_minimo if p.stock_minimo is not None else "—",
            })
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
    else:
        empty_state("No hay productos registrados.", icon="📦")


def _render_historial_compras(repo) -> None:
    st.markdown("#### Historial de compras")
    st.caption("Detalle por lote. Use esta vista para ver cada compra, no el inventario diario.")

    if not repo.data.lotes:
        empty_state("No hay compras registradas.", icon="🏷️")
        return

    productos = sorted(repo.data.productos, key=lambda x: x.nombre)
    opciones = ["Todos los productos"] + [p.nombre for p in productos]
    filtro = st.selectbox("Filtrar por producto", opciones, key="historial_filtro_producto")

    filas = []
    for lote in sorted(
        repo.data.lotes,
        key=lambda l: (l.producto_id, l.fecha_compra or date.min),
        reverse=True,
    ):
        nombre = repo.get_nombre_producto(lote.producto_id)
        if filtro != "Todos los productos" and nombre != filtro:
            continue
        filas.append({
            "Producto": nombre,
            "Lote": lote.id,
            "Compra": formato_fecha(lote.fecha_compra),
            "Expiración": formato_fecha(lote.fecha_expiracion),
            "Cantidad": lote.cantidad,
            "Restante": lote.cantidad_restante,
            "Precio total": formato_moneda(lote.precio_total, repo.get_simbolo_moneda()),
            "Proveedor": lote.marca_proveedor or "—",
        })

    if filas:
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
    else:
        empty_state("No hay compras para este producto.", icon="🔍")


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
                    sincronizar_alertas()
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
                        sincronizar_alertas()
                        st.success(resultado.mensaje)
                        st.rerun()
                    else:
                        st.error(resultado.mensaje)

    section_divider()
    _render_inventario(repo)
    section_divider()
    _render_historial_compras(repo)


def _render_alertas_stock() -> None:
    sincronizar_alertas()
    repo = get_repository()
    alertas = alertas_stock_activas(repo.data)

    st.markdown("#### Alertas activas")
    st.caption("Alertas generadas automáticamente desde el stock y las que cree manualmente.")

    if alertas:
        for alerta in alertas:
            etiqueta = _TIPO_ETIQUETA.get(alerta.tipo, alerta.tipo.value)
            col_info, col_btn = st.columns([5, 1])
            with col_info:
                st.markdown(
                    f"**{alerta.titulo}** `{etiqueta}`  \n"
                    f"{alerta.mensaje}  \n"
                    f"*{formato_fecha(alerta.fecha)}*"
                )
            with col_btn:
                if st.button("Resolver", key=f"resolver_alerta_{alerta.id}", use_container_width=True):
                    resultado = resolver_alerta(alerta.id)
                    if resultado.ok:
                        sincronizar_alertas()
                        st.rerun()
                    else:
                        st.error(resultado.mensaje)
    else:
        empty_state("No hay alertas de stock activas.", icon="✅")

    section_divider()
    st.markdown("#### Resumen rápido")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Stock bajo")
        stock_bajo = repo.productos_stock_bajo()
        if stock_bajo:
            for producto, stock in stock_bajo:
                st.markdown(f"- **{producto.nombre}** — {stock:g} {producto.unidad.value}")
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
    st.markdown("#### Crear alerta manual")
    productos_map = mapa_productos(repo.data)
    opciones_producto = ["(Ninguno)"] + list(productos_map.keys())

    with st.form("form_alerta_manual", clear_on_submit=True):
        titulo = st.text_input("Título", placeholder="Ej: Revisar pedido de jamón")
        mensaje = st.text_area("Mensaje", placeholder="Detalle de la alerta...")
        producto_sel = st.selectbox("Producto relacionado (opcional)", opciones_producto)
        enviado = st.form_submit_button("Crear alerta", type="primary")
        if enviado:
            producto_id = productos_map.get(producto_sel) if producto_sel != "(Ninguno)" else None
            resultado = crear_alerta_manual(titulo, mensaje, producto_id)
            if resultado.ok:
                sincronizar_alertas()
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)


_SUBTABS = {
    "Registro producto": _render_registro_producto,
    "Alertas stock": _render_alertas_stock,
}


def render() -> None:
    page_header("Stock", "Inventario por producto, compras por lote y alertas")

    selected = render_sub_tabs(list(_SUBTABS.keys()), key="stock_subtab")
    _SUBTABS[selected]()
