"""Stock — productos, bebidas y alertas."""

from datetime import date

import pandas as pd
import streamlit as st

from app.core.models import TipoAlerta
from app.core.services.alert_service import (
    alertas_stock_activas,
    crear_alerta_manual,
    remover_alerta,
    sincronizar_alertas,
)
from app.core.services.data_service import get_repository
from app.core.services.formatting import formato_fecha, formato_moneda
from app.core.services.stock_service import (
    UNIDADES,
    crear_bebida,
    crear_producto,
    mapa_bebidas,
    mapa_productos,
    registrar_lote,
)
from app.ui.components import empty_state, page_header, render_sub_tabs, section_divider
from app.ui.search import render_autocomplete


_TIPO_ETIQUETA = {
    TipoAlerta.STOCK_BAJO: "Stock bajo",
    TipoAlerta.STOCK_CERO: "Stock cero",
    TipoAlerta.STOCK_NEGATIVO: "Stock negativo",
    TipoAlerta.EXPIRACION_PROXIMA: "Expiración próxima",
    TipoAlerta.EXPIRADO: "Expirado",
    TipoAlerta.MANUAL: "Manual",
}


def _filtrar_catalogo(repo, es_bebida: bool) -> list:
    return [p for p in repo.data.productos if p.es_bebida == es_bebida]


def _render_inventario(repo, *, es_bebida: bool) -> None:
    titulo = "Inventario de bebidas" if es_bebida else "Inventario"
    col_nombre = "Bebida" if es_bebida else "Producto"
    items = _filtrar_catalogo(repo, es_bebida)

    st.markdown(f"#### {titulo}")
    st.caption(
        "Stock total por bebida. Las compras se registran por lote pero se muestran agregadas aquí."
        if es_bebida
        else "Stock total por producto. Las compras se registran por lote pero se muestran agregadas aquí."
    )

    if items:
        filas = []
        for p in sorted(items, key=lambda x: x.nombre):
            stock = repo.stock_total_producto(p.id)
            filas.append({
                col_nombre: p.nombre,
                "Unidad": p.unidad.value,
                "Stock actual": stock,
                "Stock mínimo": p.stock_minimo if p.stock_minimo is not None else "—",
            })
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
    else:
        msg = "No hay bebidas registradas." if es_bebida else "No hay productos registrados."
        empty_state(msg, icon="🥤" if es_bebida else "📦")


def _render_historial_compras(repo, *, es_bebida: bool, key_prefix: str) -> None:
    st.markdown("#### Historial de compras")
    st.caption("Detalle por lote. Use esta vista para ver cada compra, no el inventario diario.")

    ids_catalogo = {p.id for p in _filtrar_catalogo(repo, es_bebida)}
    lotes_tipo = [l for l in repo.data.lotes if l.producto_id in ids_catalogo]

    if not lotes_tipo:
        empty_state("No hay compras registradas.", icon="🏷️")
        return

    productos = sorted(_filtrar_catalogo(repo, es_bebida), key=lambda x: x.nombre)
    etiqueta_todos = "Todas las bebidas" if es_bebida else "Todos los productos"
    opciones_filtro = [{"id": "__all__", "label": etiqueta_todos}] + [
        {"id": p.id, "label": p.nombre} for p in productos
    ]
    filtro_sel = render_autocomplete(
        opciones_filtro,
        f"{key_prefix}_historial_filtro",
        f"Filtrar por {'bebida' if es_bebida else 'producto'}",
        f"Buscar {'bebida' if es_bebida else 'producto'}...",
        etiqueta_selectbox="Bebida" if es_bebida else "Producto",
    )
    filtro = filtro_sel["label"] if filtro_sel else etiqueta_todos

    filas = []
    for lote in sorted(
        lotes_tipo,
        key=lambda l: (l.producto_id, l.fecha_compra or date.min),
        reverse=True,
    ):
        nombre = repo.get_nombre_producto(lote.producto_id)
        if filtro != etiqueta_todos and nombre != filtro:
            continue
        filas.append({
            "Bebida" if es_bebida else "Producto": nombre,
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
        empty_state("No hay compras para este filtro.", icon="🔍")

    section_divider()
    st.markdown("##### Exportar historial")

    from app.core.services.historial_compras_service import (
        HISTORIAL_DIR,
        exportar_historial_hasta,
        ultimo_archivo_semanal,
    )

    ultimo = ultimo_archivo_semanal()
    if ultimo:
        st.caption(f"Último archivo semanal automático (productos y bebidas): lunes {formato_fecha(ultimo)}")
    else:
        st.caption("Aún no se ha generado el archivo semanal automático.")

    col_ord, col_fecha = st.columns(2)
    with col_ord:
        orden = st.selectbox(
            "Orden de exportación",
            options=["fecha", "nombre"],
            format_func=lambda x: "Fecha de compra (reciente primero)" if x == "fecha" else "Nombre (A→Z)",
            key=f"{key_prefix}_historial_orden_export",
        )
    with col_fecha:
        fecha_hasta = st.date_input(
            "Exportar hasta",
            value=date.today(),
            key=f"{key_prefix}_historial_fecha_hasta",
        )

    if st.button(
        "Exportar historial",
        type="primary",
        use_container_width=True,
        key=f"{key_prefix}_historial_btn_export",
    ):
        contenido, nombre = exportar_historial_hasta(fecha_hasta, orden, es_bebida=es_bebida)
        st.session_state[f"{key_prefix}_historial_export"] = (contenido, nombre)
        st.success(f"Exportado: {nombre}")

    if f"{key_prefix}_historial_export" in st.session_state:
        data, fname = st.session_state[f"{key_prefix}_historial_export"]
        st.download_button(
            "Descargar Excel",
            data=data,
            file_name=fname,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"{key_prefix}_historial_dl_export",
        )

    st.caption(f"Carpeta local: `{HISTORIAL_DIR}`")


def _render_registro_catalogo(*, es_bebida: bool) -> None:
    repo = get_repository()
    key_prefix = "bebida" if es_bebida else "producto"
    etiqueta = "bebida" if es_bebida else "producto"
    etiqueta_cap = "Bebida" if es_bebida else "Producto"
    crear_fn = crear_bebida if es_bebida else crear_producto
    mapa_fn = mapa_bebidas if es_bebida else lambda d: mapa_productos(d, es_bebida=False)

    with st.expander(f"Crear {etiqueta}", expanded=True):
        st.markdown(f"##### Nueva {etiqueta}")
        with st.form(f"form_crear_{key_prefix}", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                nombre = st.text_input(
                    f"Nombre de la {etiqueta}",
                    placeholder="Ej: Zumo de naranja" if es_bebida else "Ej: Croissant",
                )
                unidad = st.selectbox("Unidad", UNIDADES)
            with col2:
                stock_min = st.number_input(
                    "Stock mínimo (opcional)",
                    min_value=0.0,
                    value=0.0,
                    step=1.0,
                    help="Deje 0 si no desea definir stock mínimo.",
                )
            enviado = st.form_submit_button(f"Crear {etiqueta}", type="primary")
            if enviado:
                resultado = crear_fn(nombre, unidad, stock_min if stock_min > 0 else None)
                if resultado.ok:
                    sincronizar_alertas()
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)

    with st.expander("Registrar lote / compra"):
        st.markdown("##### Nuevo lote")
        catalogo_map = mapa_fn(repo.data)
        if not catalogo_map:
            st.warning(f"Primero debe crear al menos una {etiqueta}.")
        else:
            nombres = list(catalogo_map.keys())
            opciones_prod = [{"id": catalogo_map[n], "label": n} for n in nombres]
            producto_sel = render_autocomplete(
                opciones_prod,
                f"stock_lote_{key_prefix}",
                etiqueta_cap,
                f"Buscar {etiqueta} registrada...",
                etiqueta_selectbox=etiqueta_cap,
            )
            with st.form(f"form_registrar_lote_{key_prefix}", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    if producto_sel:
                        st.caption(f"{etiqueta_cap}: **{producto_sel['label']}**")
                    else:
                        st.warning(f"Seleccione una {etiqueta} arriba antes de registrar el lote.")
                    usar_compra = st.checkbox("Usar fecha de compra", value=False)
                    fecha_compra_val = st.date_input(
                        "Fecha de compra",
                        key=f"lote_fecha_compra_{key_prefix}",
                    )
                    usar_exp = st.checkbox("Usar fecha de expiración", value=False)
                    fecha_exp_val = st.date_input(
                        "Fecha de expiración",
                        key=f"lote_fecha_exp_{key_prefix}",
                    )
                with col2:
                    precio = st.number_input(
                        "Precio total",
                        min_value=0.0,
                        value=0.0,
                        step=0.01,
                        format="%.2f",
                    )
                    cantidad = st.number_input(
                        "Cantidad",
                        min_value=0.0,
                        value=0.0,
                        step=0.1,
                        format="%.2f",
                    )
                    proveedor = st.text_input("Marca / proveedor (opcional)")
                    alerta_dias = st.number_input(
                        "Alerta de expiración en X días (opcional)",
                        min_value=0,
                        value=0,
                        step=1,
                    )
                enviado = st.form_submit_button("Registrar lote", type="primary")
                if enviado:
                    if not producto_sel:
                        st.error(f"Seleccione una {etiqueta} antes de registrar el lote.")
                    else:
                        resultado = registrar_lote(
                            producto_id=producto_sel["id"],
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
    _render_inventario(repo, es_bebida=es_bebida)
    section_divider()
    _render_historial_compras(repo, es_bebida=es_bebida, key_prefix=key_prefix)


def _render_registro_producto() -> None:
    _render_registro_catalogo(es_bebida=False)


def _render_registro_bebidas() -> None:
    _render_registro_catalogo(es_bebida=True)


def _etiqueta_item(repo, producto_id: str | None) -> str:
    if not producto_id:
        return ""
    producto = repo.get_producto(producto_id)
    if not producto:
        return ""
    tipo = "Bebida" if producto.es_bebida else "Producto"
    return f"{producto.nombre} ({tipo})"


def _render_alertas_stock() -> None:
    sincronizar_alertas()
    repo = get_repository()
    alertas = alertas_stock_activas(repo.data)

    st.markdown("#### Alertas activas")
    st.caption(
        "Alertas automáticas de productos y bebidas, más las que cree manualmente."
    )

    if alertas:
        for alerta in alertas:
            etiqueta = _TIPO_ETIQUETA.get(alerta.tipo, alerta.tipo.value)
            item = _etiqueta_item(repo, alerta.producto_id)
            item_txt = f"  \n*{item}*" if item else ""
            col_info, col_btn = st.columns([5, 1])
            with col_info:
                st.markdown(
                    f"**{alerta.titulo}** `{etiqueta}`  \n"
                    f"{alerta.mensaje}{item_txt}  \n"
                    f"*{formato_fecha(alerta.fecha)}*"
                )
            with col_btn:
                if st.button("Remover", key=f"remover_alerta_{alerta.id}", use_container_width=True):
                    resultado = remover_alerta(alerta.id)
                    if resultado.ok:
                        sincronizar_alertas()
                        st.rerun()
                    else:
                        st.error(resultado.mensaje)
    else:
        empty_state("No hay alertas de stock activas.", icon="✅")

    section_divider()
    st.markdown("#### Resumen rápido")
    st.caption("Incluye productos y bebidas.")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("##### Stock bajo")
        stock_bajo = repo.productos_stock_bajo()
        if stock_bajo:
            for producto, stock in stock_bajo:
                tipo = "Bebida" if producto.es_bebida else "Producto"
                st.markdown(f"- **{producto.nombre}** ({tipo}) — {stock:g} {producto.unidad.value}")
        else:
            empty_state("Sin ítems con stock bajo.", icon="⚠️")

    with col2:
        st.markdown("##### Stock cero")
        agotados = repo.productos_stock_cero()
        if agotados:
            for producto in agotados:
                tipo = "Bebida" if producto.es_bebida else "Producto"
                st.markdown(f"- **{producto.nombre}** ({tipo})")
        else:
            empty_state("Sin ítems agotados.", icon="🚫")

    with col3:
        st.markdown("##### Stock negativo")
        negativos = repo.productos_stock_negativo()
        if negativos:
            for producto, stock in negativos:
                tipo = "Bebida" if producto.es_bebida else "Producto"
                st.markdown(f"- **{producto.nombre}** ({tipo}) — {stock:g} {producto.unidad.value}")
        else:
            empty_state("Sin ítems en negativo.", icon="✅")

    section_divider()
    st.markdown("#### Crear alerta manual")
    productos_map = mapa_productos(repo.data, es_bebida=False)
    bebidas_map = mapa_bebidas(repo.data)
    opciones_producto = [{"id": "__none__", "label": "(Ninguno)"}] + [
        {"id": pid, "label": f"{nombre} (Producto)"} for nombre, pid in productos_map.items()
    ] + [
        {"id": bid, "label": f"{nombre} (Bebida)"} for nombre, bid in bebidas_map.items()
    ]
    producto_alerta = render_autocomplete(
        opciones_producto,
        "alerta_producto",
        "Producto o bebida relacionada (opcional)",
        "Buscar producto o bebida...",
        etiqueta_selectbox="Ítem",
    )

    with st.form("form_alerta_manual", clear_on_submit=True):
        titulo = st.text_input("Título", placeholder="Ej: Revisar pedido de jamón")
        mensaje = st.text_area("Mensaje", placeholder="Detalle de la alerta...")
        enviado = st.form_submit_button("Crear alerta", type="primary")
        if enviado:
            producto_id = None
            if producto_alerta and producto_alerta["id"] != "__none__":
                producto_id = producto_alerta["id"]
            resultado = crear_alerta_manual(titulo, mensaje, producto_id)
            if resultado.ok:
                sincronizar_alertas()
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)


_SUBTABS = {
    "Registro producto": _render_registro_producto,
    "Registro bebidas": _render_registro_bebidas,
    "Alertas stock": _render_alertas_stock,
}


def render() -> None:
    page_header("Stock", "Inventario de productos y bebidas, compras por lote y alertas")

    selected = render_sub_tabs(list(_SUBTABS.keys()), key="stock_subtab")
    _SUBTABS[selected]()
