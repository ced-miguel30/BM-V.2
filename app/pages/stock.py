"""Stock — productos, bebidas y alertas."""

from datetime import date, datetime

import pandas as pd
import streamlit as st

from app.core.models import ESTADO_ALERTA_LABEL, EstadoAlerta, TipoAlerta
from app.core.models.enums import SERVICIO_DISPONIBLE_LABEL, TipoServicio
from app.core.services.alert_service import (
    alertas_stock_activas,
    cambiar_estado_alerta,
    crear_alerta_manual,
    sincronizar_alertas,
)
from app.core.services.data_service import get_repository
from app.core.services.exportacion_semanal_service import exportar_semana_actual, limite_semana
from app.core.services.formatting import formato_fecha, formato_moneda
from app.core.services import stock_service
from app.core.services.stock_service import (
    UNIDADES,
    crear_bebida,
    crear_producto,
    editar_producto_catalogo,
    mapa_bebidas,
    mapa_productos,
    registrar_lote,
)
from app.core.services.unidad_service import (
    formato_number_input,
    normalizar_cantidad,
    paso_unidad,
)
from app.ui.components import empty_state, page_header, render_sub_tabs, section_divider
from app.ui.search import render_autocomplete

_ETIQUETAS_SERVICIO = [SERVICIO_DISPONIBLE_LABEL[s] for s in TipoServicio]
_VALOR_SERVICIO = {SERVICIO_DISPONIBLE_LABEL[s]: s.value for s in TipoServicio}
_ETIQUETA_SERVICIO = {s.value: SERVICIO_DISPONIBLE_LABEL[s] for s in TipoServicio}


def _selector_servicios_disponibles(key: str, valores_iniciales: list[str] | None = None) -> list[str]:
    iniciales = valores_iniciales or []
    default = [_ETIQUETA_SERVICIO[v] for v in iniciales if v in _ETIQUETA_SERVICIO]
    seleccion = st.multiselect(
        "Servicios disponibles",
        _ETIQUETAS_SERVICIO,
        default=default,
        key=key,
        help=(
            "En qué registros puede usarse este producto. "
            "Vacío = No configurado (no significa «todos»). "
            "Distinto de la categoría de inventario."
        ),
    )
    return [_VALOR_SERVICIO[e] for e in seleccion]


def _etiqueta_servicios(valores: list[str]) -> str:
    if not valores:
        return "No configurado"
    return ", ".join(_ETIQUETA_SERVICIO.get(v, v) for v in valores)


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


def _lunes_semana_actual() -> date:
    lunes, _ = limite_semana(date.today())
    return lunes


def _boton_exportar_semana(config, key_prefix: str) -> None:
    col_btn, _ = st.columns([1, 2])
    with col_btn:
        if st.button("Exportar semana actual", use_container_width=True, key=f"{key_prefix}_exportar_semana"):
            resultado = exportar_semana_actual(config, datetime.now())
            if resultado.ok:
                st.session_state[f"{key_prefix}_export_dl"] = (
                    resultado.ruta.read_bytes(), resultado.nombre_archivo,
                )
                st.success(resultado.mensaje)
            else:
                st.error(resultado.mensaje)

    dl = st.session_state.get(f"{key_prefix}_export_dl")
    if dl:
        contenido, nombre = dl
        st.download_button(
            "Descargar Excel",
            data=contenido,
            file_name=nombre,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"{key_prefix}_export_dl_btn",
        )


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
                "Categoría inventario": p.categoria_inventario or "No configurado",
                "Servicios disponibles": _etiqueta_servicios(p.servicios_disponibles),
                "Stock actual": stock,
                "Stock mínimo": p.stock_minimo if p.stock_minimo is not None else "—",
            })
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
    else:
        msg = "No hay bebidas registradas." if es_bebida else "No hay productos registrados."
        empty_state(msg, icon="🥤" if es_bebida else "📦")


def _render_historial_compras(repo, *, es_bebida: bool, key_prefix: str) -> None:
    st.markdown("#### Historial de compras")
    st.caption(
        "Solo se muestran las compras de la semana en curso (con fecha de compra). "
        "Las semanas anteriores quedan archivadas y disponibles en las exportaciones. "
        "Una compra solo se puede anular si el lote está intacto y sin dependencias."
    )
    _boton_exportar_semana(stock_service.configuracion_exportacion(es_bebida=es_bebida), key_prefix)
    section_divider()

    ids_catalogo = {p.id for p in _filtrar_catalogo(repo, es_bebida)}
    lotes_tipo = [l for l in repo.data.lotes if l.producto_id in ids_catalogo]
    lunes = _lunes_semana_actual()
    lotes_semana = [
        l for l in lotes_tipo
        if l.fecha_compra and l.fecha_compra >= lunes
    ]

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

    lotes_filtrados = []
    for lote in sorted(
        lotes_semana,
        key=lambda l: (l.fecha_compra or date.min, l.id),
        reverse=True,
    ):
        nombre = repo.get_nombre_producto(lote.producto_id)
        if filtro != etiqueta_todos and nombre != filtro:
            continue
        lotes_filtrados.append(lote)

    # Listado operativo: excluir anuladas; selector incluye todas con etiqueta.
    lotes_activos = [l for l in lotes_filtrados if not getattr(l, "anulado", False)]
    lotes_anulados = [l for l in lotes_filtrados if getattr(l, "anulado", False)]

    filas = []
    for lote in lotes_activos:
        nombre = repo.get_nombre_producto(lote.producto_id)
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
    elif not lotes_filtrados:
        empty_state("No hay compras en la semana actual para este filtro.", icon="🔍")
    else:
        st.caption("No hay compras activas esta semana (solo anuladas).")

    if lotes_anulados:
        st.caption(
            f"{len(lotes_anulados)} compra(s) anulada(s) esta semana "
            "(visibles en el selector de detalle)."
        )

    if lotes_filtrados:
        from app.core.services.anulacion_compra_service import (
            anular_compra,
            lote_esta_anulado,
            puede_anular_compra,
            previsualizar_anulacion_compra,
        )
        from app.core.storage.session_store import get_data

        opciones = {}
        for lote in lotes_filtrados:
            nombre = repo.get_nombre_producto(lote.producto_id)
            marca = " [Anulado]" if getattr(lote, "anulado", False) else ""
            clave = (
                f"{lote.id}{marca} — {nombre} — "
                f"{formato_fecha(lote.fecha_compra)}"
            )
            opciones[clave] = lote

        sel = st.selectbox(
            "Ver detalle / anular compra",
            ["—"] + list(opciones.keys()),
            key=f"{key_prefix}_compra_detalle_sel",
        )
        if sel != "—":
            lote = opciones[sel]
            data = get_data()
            preview = previsualizar_anulacion_compra(data, lote)
            if lote_esta_anulado(lote):
                st.warning("Estado: **Anulado**")
                st.caption(
                    f"Fecha: {formato_fecha(lote.fecha_anulacion) if lote.fecha_anulacion else '—'} "
                    f"{lote.hora_anulacion.strftime('%H:%M') if lote.hora_anulacion else ''} "
                    f"· Por: {lote.anulado_por or '—'} "
                    f"· Motivo: {lote.motivo_anulacion or '—'} "
                    f"· Ref: {lote.referencia_anulacion or '—'}"
                )
            else:
                st.caption("Estado: Activo")

            st.dataframe(
                {
                    "Campo": [
                        "Producto", "Lote", "Cantidad compra", "Restante",
                        "Precio total", "Proveedor",
                    ],
                    "Valor": [
                        preview.nombre,
                        preview.lote_id,
                        f"{preview.cantidad_compra:g} {preview.unidad}",
                        f"{preview.cantidad_restante:g} {preview.unidad}",
                        formato_moneda(preview.precio_total, repo.get_simbolo_moneda()),
                        lote.marca_proveedor or "—",
                    ],
                },
                use_container_width=True,
                hide_index=True,
            )
            st.caption(preview.efecto)

            st.markdown("##### Anulación de compra")
            puede = puede_anular_compra(data, lote)
            if not puede.ok:
                for motivo in puede.motivos_bloqueo:
                    st.error(motivo)
            else:
                motivo_a = st.text_input(
                    "Motivo de anulación (obligatorio)",
                    key=f"{key_prefix}_compra_anul_motivo_{lote.id}",
                )
                ref_a = st.text_input(
                    "Referencia (opcional)",
                    key=f"{key_prefix}_compra_anul_ref_{lote.id}",
                )
                conf = st.checkbox(
                    "Confirmo anular esta compra intacta (restante → 0; histórico conservado)",
                    key=f"{key_prefix}_compra_anul_ok_{lote.id}",
                )
                if st.button(
                    "Anular compra",
                    type="primary",
                    disabled=not conf or not (motivo_a or "").strip(),
                    key=f"{key_prefix}_compra_anul_btn_{lote.id}",
                ):
                    resultado = anular_compra(data, lote.id, motivo_a, ref_a)
                    if resultado.ok:
                        st.success(resultado.mensaje)
                        st.rerun()
                    else:
                        st.error(resultado.mensaje)


def _render_catalogo_solo(*, es_bebida: bool) -> None:
    """Alta y configuración de catálogo (sin compras ni inventario)."""
    from app.core.services import catalogo_service as cat

    repo = get_repository()
    key_prefix = "bebida" if es_bebida else "producto"
    etiqueta = "bebida" if es_bebida else "producto"
    crear_fn = crear_bebida if es_bebida else crear_producto
    mapa_fn = mapa_bebidas if es_bebida else lambda d: mapa_productos(d, es_bebida=False)

    st.caption(
        "La categoría estructurada y los departamentos organizan el inventario. "
        "La categoría histórica / libre se conserva por compatibilidad. "
        "Servicios disponibles definen en qué registros puede usarse (vacío ≠ todos)."
    )

    with st.expander(f"Crear {etiqueta}", expanded=True):
        st.markdown(f"##### Nueva {etiqueta}")
        cats = cat.opciones_categoria_asignacion(repo.data)
        cat_labels = {"— Sin categoría —": None}
        cat_labels.update({c.nombre: c.id for c in cats})
        cat_sel = st.selectbox(
            "Categoría estructurada (opcional)",
            list(cat_labels.keys()),
            key=f"crear_cat_id_{key_prefix}",
        )
        cat_id = cat_labels[cat_sel]
        subs = cat.opciones_subcategoria_asignacion(repo.data, cat_id)
        sub_labels = {"— Sin subcategoría —": None}
        sub_labels.update({s.nombre: s.id for s in subs})
        sub_sel = st.selectbox(
            "Subcategoría (opcional)",
            list(sub_labels.keys()),
            key=f"crear_sub_id_{key_prefix}",
            disabled=cat_id is None,
        )
        sub_id = sub_labels[sub_sel] if cat_id else None
        deps = cat.opciones_departamento_asignacion(repo.data)
        dep_sel = st.multiselect(
            "Departamentos (opcional)",
            options=[d.id for d in deps],
            format_func=lambda i: next(d.nombre for d in deps if d.id == i),
            key=f"crear_deps_{key_prefix}",
            help="Ámbitos donde el producto puede usarse. No es ubicación ni stock.",
        )
        ubis = cat.opciones_ubicacion_asignacion(repo.data)
        ubi_sel = st.multiselect(
            "Ubicaciones permitidas",
            options=[u.id for u in ubis],
            format_func=lambda i: next(u.nombre for u in ubis if u.id == i),
            key=f"crear_ubis_{key_prefix}",
        )
        st.caption(
            "Lugares donde este producto puede almacenarse. "
            "No representa la cantidad disponible en cada ubicación."
        )
        from app.core.models.enums import TIPO_ARTICULO_AYUDA, TIPO_ARTICULO_LABEL, TipoArticulo

        tipo_labels = {TIPO_ARTICULO_LABEL[t]: t.value for t in TipoArticulo}
        tipo_sel = st.selectbox(
            "Tipo de artículo",
            list(tipo_labels.keys()),
            key=f"crear_tipo_{key_prefix}",
        )
        st.caption(
            f"**Consumible** — {TIPO_ARTICULO_AYUDA[TipoArticulo.CONSUMIBLE]}\n\n"
            f"**Reutilizable** — {TIPO_ARTICULO_AYUDA[TipoArticulo.REUTILIZABLE]}"
        )

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
                    step=paso_unidad(unidad),
                    format=formato_number_input(unidad),
                    help="Deje 0 si no desea definir stock mínimo.",
                )
                stock_min = normalizar_cantidad(stock_min, unidad)
                categoria_inv = st.text_input(
                    "Categoría histórica / libre",
                    placeholder="Ej: Verduras, Lácteos…",
                    key=f"crear_cat_inv_{key_prefix}",
                )
                st.caption(
                    "Campo anterior conservado por compatibilidad. "
                    "No sustituye la categoría estructurada."
                )
                servicios = _selector_servicios_disponibles(f"crear_servicios_{key_prefix}")
            enviado = st.form_submit_button(f"Crear {etiqueta}", type="primary")
            if enviado:
                resultado = crear_fn(
                    nombre,
                    unidad,
                    stock_min if stock_min > 0 else None,
                    servicios_disponibles=servicios,
                    categoria_inventario=categoria_inv,
                    categoria_id=cat_id,
                    subcategoria_id=sub_id,
                    departamento_ids=dep_sel,
                    ubicacion_ids=ubi_sel,
                    tipo_articulo=tipo_labels[tipo_sel],
                )
                if resultado.ok:
                    sincronizar_alertas()
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)

    with st.expander(f"Configurar {etiqueta} existente", expanded=True):
        catalogo_map = mapa_fn(repo.data)
        if not catalogo_map:
            st.warning(f"No hay {etiqueta}s para configurar.")
        else:
            nombres = list(catalogo_map.keys())
            sel_nombre = st.selectbox(
                f"Seleccionar {etiqueta}",
                nombres,
                key=f"cfg_sel_{key_prefix}",
            )
            producto = repo.get_producto(catalogo_map[sel_nombre])
            if producto:
                et_cat = cat.etiqueta_categoria(repo.data, producto.categoria_id)
                et_sub = cat.etiqueta_subcategoria(repo.data, producto.subcategoria_id)
                et_deps = ", ".join(
                    cat.etiqueta_departamento(repo.data, d)
                    for d in producto.departamento_ids
                ) or "No configurado"
                et_ubis = ", ".join(
                    cat.etiqueta_ubicacion(repo.data, u)
                    for u in getattr(producto, "ubicacion_ids", []) or []
                ) or "No configurado"
                et_tipo = cat.etiqueta_tipo_articulo(
                    getattr(producto, "tipo_articulo", None),
                )
                st.caption(
                    f"Actual — histórica: "
                    f"**{producto.categoria_inventario or 'No configurado'}** · "
                    f"estructurada: **{et_cat}** / **{et_sub}** · "
                    f"deptos: **{et_deps}** · "
                    f"ubicaciones: **{et_ubis}** · "
                    f"tipo: **{et_tipo}** · "
                    f"servicios: **{_etiqueta_servicios(producto.servicios_disponibles)}**"
                )
                cats_e = cat.opciones_categoria_asignacion(
                    repo.data, conservar_id=producto.categoria_id,
                )
                cat_labels_e = {"— Sin categoría —": None}
                cat_labels_e.update({c.nombre: c.id for c in cats_e})
                # Índice por id actual
                cat_keys = list(cat_labels_e.keys())
                cat_default = 0
                for i, k in enumerate(cat_keys):
                    if cat_labels_e[k] == producto.categoria_id:
                        cat_default = i
                        break
                cat_sel_e = st.selectbox(
                    "Categoría estructurada (opcional)",
                    cat_keys,
                    index=cat_default,
                    key=f"cfg_cat_id_{key_prefix}_{producto.id}",
                )
                cat_id_e = cat_labels_e[cat_sel_e]
                subs_e = cat.opciones_subcategoria_asignacion(
                    repo.data,
                    cat_id_e,
                    conservar_id=producto.subcategoria_id
                    if (producto.categoria_id == cat_id_e) else None,
                )
                sub_labels_e = {"— Sin subcategoría —": None}
                sub_labels_e.update({s.nombre: s.id for s in subs_e})
                sub_keys = list(sub_labels_e.keys())
                sub_default = 0
                for i, k in enumerate(sub_keys):
                    if sub_labels_e[k] == producto.subcategoria_id and cat_id_e == producto.categoria_id:
                        sub_default = i
                        break
                sub_sel_e = st.selectbox(
                    "Subcategoría (opcional)",
                    sub_keys,
                    index=min(sub_default, len(sub_keys) - 1),
                    key=f"cfg_sub_id_{key_prefix}_{producto.id}",
                    disabled=cat_id_e is None,
                )
                sub_id_e = sub_labels_e[sub_sel_e] if cat_id_e else None
                deps_e = cat.opciones_departamento_asignacion(
                    repo.data, conservar_ids=list(producto.departamento_ids),
                )
                dep_sel_e = st.multiselect(
                    "Departamentos (opcional)",
                    options=[d.id for d in deps_e],
                    default=[
                        d for d in producto.departamento_ids
                        if any(x.id == d for x in deps_e)
                    ],
                    format_func=lambda i: next(
                        (d.nombre for d in deps_e if d.id == i),
                        "Referencia no encontrada",
                    ),
                    key=f"cfg_deps_{key_prefix}_{producto.id}",
                )
                ubis_e = cat.opciones_ubicacion_asignacion(
                    repo.data,
                    conservar_ids=list(getattr(producto, "ubicacion_ids", []) or []),
                )
                ubi_map_e = {u.id: u for u in ubis_e}

                def _fmt_ubi(i: str) -> str:
                    u = ubi_map_e.get(i)
                    if u is None:
                        return "Referencia no encontrada"
                    if not u.activo:
                        return f"{u.nombre} (inactivo)"
                    return u.nombre

                ubi_sel_e = st.multiselect(
                    "Ubicaciones permitidas",
                    options=[u.id for u in ubis_e],
                    default=[
                        u for u in (getattr(producto, "ubicacion_ids", []) or [])
                        if any(x.id == u for x in ubis_e)
                    ],
                    format_func=_fmt_ubi,
                    key=f"cfg_ubis_{key_prefix}_{producto.id}",
                )
                st.caption(
                    "Lugares donde este producto puede almacenarse. "
                    "No representa la cantidad disponible en cada ubicación."
                )
                from app.core.models.enums import (
                    TIPO_ARTICULO_AYUDA,
                    TIPO_ARTICULO_LABEL,
                    TipoArticulo,
                )

                tipo_opts: dict[str, str | None] = {"Sin clasificar": None}
                tipo_opts.update({TIPO_ARTICULO_LABEL[t]: t.value for t in TipoArticulo})
                actual_tipo = getattr(producto, "tipo_articulo", None)
                if actual_tipo is not None and not cat.es_tipo_articulo_conocido(actual_tipo):
                    tipo_opts[f"Valor desconocido ({actual_tipo})"] = str(actual_tipo)
                tipo_keys = list(tipo_opts.keys())
                tipo_default = 0
                for i, k in enumerate(tipo_keys):
                    val = tipo_opts[k]
                    if val is None and actual_tipo is None:
                        tipo_default = i
                        break
                    if val is not None and actual_tipo is not None:
                        actual_v = (
                            actual_tipo.value
                            if hasattr(actual_tipo, "value")
                            else str(actual_tipo)
                        )
                        if val == actual_v:
                            tipo_default = i
                            break
                tipo_sel_e = st.selectbox(
                    "Tipo de artículo",
                    tipo_keys,
                    index=tipo_default,
                    key=f"cfg_tipo_{key_prefix}_{producto.id}",
                )
                st.caption(
                    f"**Consumible** — {TIPO_ARTICULO_AYUDA[TipoArticulo.CONSUMIBLE]}  \n"
                    f"**Reutilizable** — {TIPO_ARTICULO_AYUDA[TipoArticulo.REUTILIZABLE]}  \n"
                    "Los históricos sin clasificar pueden permanecer así temporalmente; "
                    "no se clasifican automáticamente."
                )
                cat_edit = st.text_input(
                    "Categoría histórica / libre",
                    value=producto.categoria_inventario or "",
                    key=f"cfg_cat_{key_prefix}_{producto.id}",
                )
                st.caption(
                    "Campo anterior conservado por compatibilidad. "
                    "No sustituye la categoría estructurada."
                )
                serv_edit = _selector_servicios_disponibles(
                    f"cfg_serv_{key_prefix}_{producto.id}",
                    producto.servicios_disponibles,
                )
                if st.button(
                    "Guardar catálogo",
                    type="primary",
                    key=f"cfg_guardar_{key_prefix}",
                ):
                    resultado = editar_producto_catalogo(
                        producto.id,
                        servicios_disponibles=serv_edit,
                        categoria_inventario=cat_edit,
                        categoria_id=cat_id_e,
                        subcategoria_id=sub_id_e,
                        departamento_ids=dep_sel_e,
                        ubicacion_ids=ubi_sel_e,
                        tipo_articulo=tipo_opts[tipo_sel_e],
                    )
                    if resultado.ok:
                        st.success(resultado.mensaje)
                        st.rerun()
                    else:
                        st.error(resultado.mensaje)


def _render_registrar_lote(*, es_bebida: bool) -> None:
    """Formulario de nuevo lote/compra para el catálogo indicado."""
    repo = get_repository()
    key_prefix = "bebida" if es_bebida else "producto"
    etiqueta = "bebida" if es_bebida else "producto"
    etiqueta_cap = "Bebida" if es_bebida else "Producto"
    mapa_fn = mapa_bebidas if es_bebida else lambda d: mapa_productos(d, es_bebida=False)

    st.markdown("#### Registrar compra / lote")
    catalogo_map = mapa_fn(repo.data)
    if not catalogo_map:
        st.warning(f"Primero debe crear al menos una {etiqueta} en la pestaña Productos.")
        return

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
            unidad_lote = "Ud"
            if producto_sel:
                prod_obj = repo.get_producto(producto_sel["id"])
                if prod_obj:
                    unidad_lote = prod_obj.unidad.value
            cantidad = st.number_input(
                "Cantidad",
                min_value=0.0,
                value=0.0,
                step=paso_unidad(unidad_lote),
                format=formato_number_input(unidad_lote),
            )
            cantidad = normalizar_cantidad(cantidad, unidad_lote)
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


def _render_tab_productos() -> None:
    st.markdown("#### Catálogo")
    tipo = render_sub_tabs(["Producto", "Bebida"], key="stock_prod_tipo")
    _render_catalogo_solo(es_bebida=(tipo == "Bebida"))


def _render_tab_compras() -> None:
    tipo = render_sub_tabs(["Producto", "Bebida"], key="stock_compra_tipo")
    es_bebida = tipo == "Bebida"
    key_prefix = "bebida" if es_bebida else "producto"
    _render_registrar_lote(es_bebida=es_bebida)
    section_divider()
    _render_historial_compras(get_repository(), es_bebida=es_bebida, key_prefix=key_prefix)


def _render_tab_inventario() -> None:
    repo = get_repository()
    st.markdown("#### Stock actual")
    tipo = render_sub_tabs(["Producto", "Bebida"], key="stock_inv_tipo")
    _render_inventario(repo, es_bebida=(tipo == "Bebida"))
    section_divider()
    _render_ajustes_inventario()
    section_divider()
    _render_recuentos_inventario()
    section_divider()
    _render_alertas_stock()


def _render_recuentos_inventario() -> None:
    from app.core.services import recuento_service as rc
    from app.core.services.ubicacion_stock_service import saldo_en_ubicacion

    repo = get_repository()
    data = repo.data
    st.markdown("#### Recuentos por ubicación")
    st.caption(
        "Conteo físico: la diferencia confirmada genera ajuste (entrada/salida) "
        "trazable en el ledger. No sobrescribe el saldo a mano."
    )
    ubis = [u for u in data.ubicaciones if getattr(u, "activo", True)]
    lotes = [
        l for l in data.lotes
        if not getattr(l, "anulado", False) and float(l.cantidad_restante) >= 0
    ]
    if not ubis or not lotes:
        empty_state("Se necesitan ubicaciones y lotes para recuentos.", icon="📋")
        return
    mapa_ubi = {f"{u.nombre} ({u.id})": u.id for u in ubis}
    ubi_lbl = st.selectbox("Ubicación", list(mapa_ubi.keys()), key="rc_ubi")
    ubi_id = mapa_ubi[ubi_lbl]
    mapa_lote = {
        f"{l.id} · esperado {saldo_en_ubicacion(data, l.id, ubi_id):g}": l
        for l in lotes
    }
    lote_lbl = st.selectbox("Lote", list(mapa_lote.keys()), key="rc_lote")
    lote = mapa_lote[lote_lbl]
    contada = st.number_input(
        "Cantidad contada",
        min_value=0.0,
        value=float(saldo_en_ubicacion(data, lote.id, ubi_id)),
        key="rc_contada",
    )
    motivo = st.text_input("Motivo", key="rc_motivo")
    if st.button("Crear borrador de recuento", key="rc_draft"):
        res = rc.crear_borrador(
            ubicacion_id=ubi_id,
            lineas=[(lote.id, lote.producto_id, contada)],
            motivo=motivo or None,
        )
        if res.ok:
            st.success(res.mensaje)
            st.session_state["rc_last_id"] = res.sesion.id if res.sesion else None
            st.rerun()
        else:
            st.error(res.mensaje)

    pendientes = rc.listar_recuentos_pendientes(data)
    if pendientes:
        st.markdown("##### Borradores pendientes")
        for s in pendientes:
            st.write(
                f"`{s.id}` · {s.ubicacion_id} · "
                + "; ".join(rc.preview_confirmacion(s))
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Confirmar", key=f"rc_ok_{s.id}"):
                    conf = rc.confirmar_recuento(recuento_id=s.id)
                    if conf.ok:
                        st.success(conf.mensaje)
                        st.rerun()
                    else:
                        st.error(conf.mensaje)
            with c2:
                if st.button("Anular borrador", key=f"rc_no_{s.id}"):
                    an = rc.anular_recuento(recuento_id=s.id)
                    if an.ok:
                        st.success(an.mensaje)
                        st.rerun()
                    else:
                        st.error(an.mensaje)


def _render_tab_traslados() -> None:
    from app.core.services import traslado_service as tr
    from app.core.services.ubicacion_stock_service import saldo_en_ubicacion

    repo = get_repository()
    data = repo.data
    st.markdown("#### Traslados entre ubicaciones")
    st.caption(
        "Mueve cantidad de un lote entre ubicaciones sin cambiar el stock total "
        "del hotel ni el FIFO global."
    )

    lotes = [
        l for l in data.lotes
        if not getattr(l, "anulado", False) and float(l.cantidad_restante) > 0
    ]
    ubis = [u for u in data.ubicaciones if getattr(u, "activo", True)]
    if not lotes or len(ubis) < 2:
        empty_state(
            "Se necesitan lotes con stock y al menos 2 ubicaciones activas.",
            icon="📦",
        )
    else:
        mapa_lotes = {
            f"{l.id} · {next((p.nombre for p in data.productos if p.id == l.producto_id), l.producto_id)} "
            f"(restante {l.cantidad_restante:g})": l
            for l in lotes
        }
        mapa_ubi = {f"{u.nombre} ({u.id})": u.id for u in ubis}
        etiqueta_lote = st.selectbox("Lote", list(mapa_lotes.keys()), key="tr_lote")
        lote = mapa_lotes[etiqueta_lote]
        c1, c2, c3 = st.columns(3)
        with c1:
            origen_lbl = st.selectbox("Origen", list(mapa_ubi.keys()), key="tr_origen")
        with c2:
            dest_lbl = st.selectbox("Destino", list(mapa_ubi.keys()), key="tr_destino")
        with c3:
            qty = st.number_input("Cantidad", min_value=0.0, step=0.1, key="tr_qty")
        origen_id = mapa_ubi[origen_lbl]
        dest_id = mapa_ubi[dest_lbl]
        disp = saldo_en_ubicacion(data, lote.id, origen_id)
        st.caption(f"Disponible en origen: {disp:g}")
        forzar = st.checkbox(
            "Confirmar destino aunque no esté en ubicaciones permitidas del producto",
            key="tr_forzar_destino",
        )
        preview = tr.previsualizar_traslado(
            data,
            lote_id=lote.id,
            ubicacion_origen_id=origen_id,
            ubicacion_destino_id=dest_id,
            cantidad=qty,
            permitir_destino_no_catalogado=forzar,
        )
        if preview.ok:
            st.info(
                f"Preview OK — hotel stock invariante {preview.stock_hotel_antes:g}. "
                f"{preview.mensaje}"
            )
            if preview.advertencia_destino:
                st.warning(preview.advertencia_destino)
        else:
            st.warning(preview.mensaje)

        if st.button("Confirmar traslado", type="primary", key="tr_confirm"):
            res = tr.confirmar_traslado(
                lote_id=lote.id,
                ubicacion_origen_id=origen_id,
                ubicacion_destino_id=dest_id,
                cantidad=qty,
                permitir_destino_no_catalogado=forzar,
            )
            if res.ok:
                st.success(res.mensaje)
                st.rerun()
            else:
                st.error(res.mensaje)

    section_divider()
    st.markdown("#### Historial de traslados")
    hist = tr.listar_traslados(data)
    if not hist:
        st.caption("Sin traslados registrados.")
    else:
        for m in reversed(hist[-30:]):
            st.write(
                f"`{m.origen_id}` · lote `{m.lote_id}` · "
                f"{m.cantidad:g} · {m.ubicacion_origen_id} → {m.ubicacion_destino_id} "
                f"· {m.fecha}"
            )
            if st.button(
                f"Anular {m.origen_id}",
                key=f"tr_anular_{m.id}",
            ):
                an = tr.anular_traslado(traslado_id=m.origen_id)
                if an.ok:
                    st.success(an.mensaje)
                    st.rerun()
                else:
                    st.error(an.mensaje)


_SUBTABS = {
    "Productos": _render_tab_productos,
    "Compras": _render_tab_compras,
    "Inventario": _render_tab_inventario,
    "Traslados": _render_tab_traslados,
}


def render() -> None:
    page_header("Stock", "Inventario de productos y bebidas, compras por lote y alertas")

    selected = render_sub_tabs(list(_SUBTABS.keys()), key="stock_subtab")
    _SUBTABS[selected]()


def _etiqueta_item(repo, producto_id: str | None) -> str:
    if not producto_id:
        return ""
    producto = repo.get_producto(producto_id)
    if not producto:
        return ""
    tipo = "Bebida" if producto.es_bebida else "Producto"
    return f"{producto.nombre} ({tipo})"


def _ir_stock_accion(subtab: str, *, compra_tipo: str | None = None) -> None:
    st.session_state["stock_subtab"] = subtab
    if compra_tipo:
        st.session_state["stock_compra_tipo"] = compra_tipo
    st.rerun()


def _render_alertas_stock() -> None:
    sincronizar_alertas()
    repo = get_repository()
    alertas = alertas_stock_activas(repo.data)

    st.markdown("#### Alertas activas")
    st.caption(
        "Pendiente / Revisada siguen visibles mientras la causa exista. "
        "Resuelta e Ignorada ocultan la alerta (si la causa persiste, no reaparece hasta que desaparezca)."
    )

    if alertas:
        for alerta in alertas:
            etiqueta = _TIPO_ETIQUETA.get(alerta.tipo, alerta.tipo.value)
            try:
                estado = EstadoAlerta(getattr(alerta, "estado", None) or "pendiente")
            except ValueError:
                estado = EstadoAlerta.PENDIENTE
            estado_txt = ESTADO_ALERTA_LABEL[estado]
            item = _etiqueta_item(repo, alerta.producto_id)
            item_txt = f"  \n*{item}*" if item else ""
            lote_id = getattr(alerta, "lote_id", None)
            lote_txt = f"  \nLote: `{lote_id}`" if lote_id else ""

            st.markdown(
                f"**{alerta.titulo}** `{etiqueta}` · **{estado_txt}**  \n"
                f"{alerta.mensaje}{item_txt}{lote_txt}  \n"
                f"*{formato_fecha(alerta.fecha)}*"
            )

            acciones = st.columns(5)
            with acciones[0]:
                if estado != EstadoAlerta.REVISADA and st.button(
                    "Revisada", key=f"alerta_rev_{alerta.id}", use_container_width=True,
                ):
                    r = cambiar_estado_alerta(alerta.id, EstadoAlerta.REVISADA.value)
                    if r.ok:
                        sincronizar_alertas()
                        st.rerun()
                    st.error(r.mensaje)
            with acciones[1]:
                if st.button("Resuelta", key=f"alerta_res_{alerta.id}", use_container_width=True):
                    r = cambiar_estado_alerta(alerta.id, EstadoAlerta.RESUELTA.value)
                    if r.ok:
                        sincronizar_alertas()
                        st.rerun()
                    st.error(r.mensaje)
            with acciones[2]:
                if st.button("Ignorada", key=f"alerta_ign_{alerta.id}", use_container_width=True):
                    r = cambiar_estado_alerta(alerta.id, EstadoAlerta.IGNORADA.value)
                    if r.ok:
                        sincronizar_alertas()
                        st.rerun()
                    st.error(r.mensaje)
            with acciones[3]:
                if alerta.producto_id and st.button(
                    "Ir a compra", key=f"alerta_compra_{alerta.id}", use_container_width=True,
                ):
                    producto = repo.get_producto(alerta.producto_id)
                    tipo = "Bebida" if producto and producto.es_bebida else "Producto"
                    _ir_stock_accion("Compras", compra_tipo=tipo)
            with acciones[4]:
                if alerta.producto_id and st.button(
                    "Ver producto", key=f"alerta_prod_{alerta.id}", use_container_width=True,
                ):
                    producto = repo.get_producto(alerta.producto_id)
                    tipo = "Bebida" if producto and producto.es_bebida else "Producto"
                    st.session_state["stock_prod_tipo"] = tipo
                    _ir_stock_accion("Productos")
            section_divider()
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


def _render_ajustes_inventario() -> None:
    """Ajuste de cantidad restante por lote con trazabilidad (Fase 10)."""
    from app.core.services import ajuste_service
    from app.core.services.unidad_service import formato_number_input, paso_unidad

    repo = get_repository()
    st.markdown("#### Ajustes de inventario")
    st.caption(
        "Corrige el stock teórico del lote frente al recuento real. "
        "Solo cambia la cantidad restante; la compra histórica (precio, cantidad "
        "original, fechas) no se modifica. Toda corrección queda registrada."
    )

    lotes = ajuste_service.lotes_ajustables()
    if not lotes:
        empty_state("No hay lotes para ajustar. Registre una compra primero.", icon="🏷️")
    else:
        mapa = {l["label"]: l for l in lotes}
        etiqueta = st.selectbox(
            "Lote",
            list(mapa.keys()),
            key="ajuste_sel_lote",
        )
        lote_sel = mapa[etiqueta]
        unidad = lote_sel["unidad"]
        st.caption(
            f"Actual restante: {lote_sel['restante']:g} {unidad}. "
            "Indique la cantidad real tras el recuento."
        )
        col_a, col_b = st.columns(2)
        with col_a:
            cantidad_nueva = st.number_input(
                "Cantidad restante nueva",
                min_value=0.0,
                value=float(lote_sel["restante"]),
                step=paso_unidad(unidad),
                format=formato_number_input(unidad),
                key="ajuste_cantidad_nueva",
            )
            motivo = st.selectbox(
                "Motivo",
                ajuste_service.MOTIVOS_AJUSTE,
                key="ajuste_motivo",
            )
        with col_b:
            fecha = st.date_input(
                "Fecha del ajuste",
                value=date.today(),
                max_value=date.today(),
                key="ajuste_fecha",
            )
            comentario = st.text_input(
                "Comentario (opcional)",
                key="ajuste_comentario",
                placeholder="Ej: recuento de cámara fría",
            )

        preview, err = ajuste_service.previsualizar_ajuste(
            lote_sel["id"],
            cantidad_nueva,
            motivo,
            comentario,
        )
        if err:
            st.info(err)
        elif preview is not None:
            st.markdown("##### Vista previa (antes de confirmar)")
            st.dataframe(
                {
                    "Producto": [preview.nombre],
                    "Lote": [preview.lote_id],
                    "Actual": [f"{preview.cantidad_antes:g} {preview.unidad}"],
                    "Nueva": [f"{preview.cantidad_despues:g} {preview.unidad}"],
                    "Δ": [f"{preview.delta:+g} {preview.unidad}"],
                    "Motivo": [preview.motivo],
                    "Compra intacta": [
                        f"{preview.cantidad_compra:g} · "
                        f"{formato_moneda(preview.precio_total, repo.get_simbolo_moneda())} · "
                        f"{preview.fecha_compra_txt}"
                    ],
                },
                use_container_width=True,
                hide_index=True,
            )
            if st.button(
                "Confirmar ajuste",
                type="primary",
                use_container_width=True,
                key="ajuste_btn_confirmar",
            ):
                resultado = ajuste_service.aplicar_ajuste(
                    fecha,
                    lote_sel["id"],
                    cantidad_nueva,
                    motivo,
                    comentario,
                )
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)

    section_divider()
    st.markdown("#### Historial de ajustes")
    st.caption("Registros de la semana en curso. Las correcciones quedan archivadas en los datos.")
    lunes = _lunes_semana_actual()
    ajustes_semana = [
        a for a in ajuste_service.historial_ordenado()
        if a.fecha >= lunes
    ]
    if not ajustes_semana:
        empty_state("No hay ajustes en la semana actual.", icon="📋")
        return

    filas = []
    for reg in ajustes_semana:
        for ln in reg.lineas:
            nombre = ln.producto_nombre_snapshot or repo.get_nombre_producto(ln.producto_id)
            unidad = ln.unidad_snapshot or ""
            filas.append({
                "Fecha": formato_fecha(reg.fecha),
                "Hora": reg.hora.strftime("%H:%M") if reg.hora else "—",
                "Producto": nombre,
                "Lote": ln.lote_id,
                "Antes": f"{ln.cantidad_antes:g} {unidad}".strip(),
                "Después": f"{ln.cantidad_despues:g} {unidad}".strip(),
                "Δ": f"{ln.delta:+g} {unidad}".strip(),
                "Motivo": ln.motivo.value if hasattr(ln.motivo, "value") else str(ln.motivo),
                "Usuario": reg.registrado_por or "—",
                "Comentario": ln.comentario or "—",
            })
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
