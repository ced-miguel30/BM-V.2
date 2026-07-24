"""Desayuno — registro de consumo y merma."""

from datetime import date, datetime, time

import streamlit as st

from app.core.models import TipoServicio
from app.core.services import desayuno_service
from app.core.services.data_service import get_repository
from app.core.services.desayuno_service import (
    ajustar_cantidad_suelto,
    ajustar_linea_grupo,
    ajustar_porciones_grupo,
    anadir_a_cesta,
    anadir_mod_pendiente_receta,
    anadir_receta_a_cesta,
    coste_total_cesta,
    etiqueta_linea_receta,
    etiqueta_linea_suelta,
    cantidad_texto_linea_receta,
    get_cesta,
    get_cesta_recetas,
    get_mods_pendientes,
    limpiar_cesta,
    modificar_porciones_grupo,
    paso_linea_grupo,
    paso_linea_suelta,
    productos_catalogo,
    quitar_grupo_receta,
    quitar_linea_grupo,
    quitar_linea_suelta,
    quitar_mod_pendiente,
    registrar_desayuno,
)
from app.core.services.unidad_service import (
    formato_number_input,
    normalizar_cantidad,
    paso_unidad,
)
from app.core.services.exportacion_semanal_service import limite_semana
from app.core.services.formatting import formato_fecha
from app.core.services.receta_service import listar_recetas
from app.ui.cesta_render import (
    boton_exportar_semana as _boton_exportar_semana,
    clave_orden as _clave_orden,
    fila_cesta as _fila_cesta,
    ok_o_error as _ok_o_error,
    quitar_y_rerun as _quitar_y_rerun,
)
from app.ui.components import (
    aviso_servicios_pendientes,
    empty_state,
    page_header,
    render_sub_tabs,
    section_divider,
)
from app.ui.search import render_autocomplete, render_buscador_producto

STOCK_PENDIENTE_KEY = "bm_stock_pendiente_registro"



def _lineas_merma_texto(repo, merma) -> str:
    partes = []
    for linea in merma.lineas:
        nombre = repo.get_nombre_producto(linea.producto_id)
        partes.append(f"{nombre} ({linea.cantidad}) — {linea.motivo.value}")
    return ", ".join(partes)


def _lunes_semana_actual() -> date:
    lunes, _ = limite_semana(date.today())
    return lunes


def _render_detalle_desayuno(d) -> None:
    """Desglose completo de un registro de desayuno (recetas, extras/omisiones
    y productos), reutilizando la misma lógica que la exportación a Excel."""
    hasta = datetime.combine(d.fecha, time.max)
    registros = [r for r in desayuno_service.registros_exportables(d.fecha, hasta) if r.identificador == d.id]
    if not registros:
        return
    registro = registros[0]
    hora_txt = registro.hora.strftime("%H:%M") if registro.hora else "—"
    st.caption(f"Nº {registro.identificador} · Hora {hora_txt} · {registro.usuario or '—'}")
    st.dataframe(
        {col: [fila[i] for fila in registro.filas] for i, col in enumerate(registro.columnas)},
        use_container_width=True,
        hide_index=True,
    )
    if registro.resumen:
        st.caption(" · ".join(f"{clave}: {valor}" for clave, valor in registro.resumen))


def _render_cesta_desayuno(repo) -> None:
    grupos = get_cesta_recetas()
    cesta = get_cesta()
    hay_contenido = bool(grupos or cesta)

    with st.container(border=True):
        st.markdown(
            '<div class="bm-cesta-scope"></div>'
            '<div class="bm-cesta-title">Desayuno</div>',
            unsafe_allow_html=True,
        )

        if not hay_contenido:
            st.markdown(
                '<p class="bm-cesta-empty">Todavía no has añadido productos al desayuno.</p>',
                unsafe_allow_html=True,
            )
            return

        elementos = [("receta", g) for g in grupos] + [("suelto", l) for l in cesta]
        elementos.sort(
            key=lambda e: _clave_orden(e[1].nombre_receta if e[0] == "receta" else e[1].nombre)
        )

        for indice, (tipo, elemento) in enumerate(elementos):
            if indice > 0:
                st.markdown('<div class="bm-cesta-divider"></div>', unsafe_allow_html=True)

            if tipo == "receta":
                grupo = elemento
                _fila_cesta(
                    f'<div class="bm-cesta-nombre">{grupo.nombre_receta}</div>',
                    f"grp_{grupo.grupo_id}",
                    lambda g=grupo: _quitar_y_rerun(quitar_grupo_receta, g.grupo_id),
                    cantidad_texto=f"{grupo.porciones:g}",
                    on_menos=lambda g=grupo: _ok_o_error(ajustar_porciones_grupo(g.grupo_id, -1)),
                    on_mas=lambda g=grupo: _ok_o_error(
                        modificar_porciones_grupo(g.grupo_id, g.porciones + 1)
                    ),
                    ayuda_quitar="Eliminar receta",
                )
                for ing in grupo.ingredientes:
                    paso = paso_linea_grupo(grupo.grupo_id, ing.linea_id)
                    _fila_cesta(
                        f'<div class="bm-cesta-detalle">{etiqueta_linea_receta(ing)}</div>',
                        f"ing_{grupo.grupo_id}_{ing.linea_id}",
                        lambda g=grupo, i=ing: _quitar_y_rerun(
                            quitar_linea_grupo, g.grupo_id, i.linea_id
                        ),
                        cantidad_texto=cantidad_texto_linea_receta(ing),
                        on_menos=lambda g=grupo, i=ing, p=paso: _ok_o_error(
                            ajustar_linea_grupo(g.grupo_id, i.linea_id, -p)
                        ),
                        on_mas=lambda g=grupo, i=ing, p=paso: _ok_o_error(
                            ajustar_linea_grupo(g.grupo_id, i.linea_id, p)
                        ),
                        ayuda_quitar="Eliminar ingrediente",
                    )
            else:
                linea = elemento
                paso = paso_linea_suelta(linea.linea_id)
                _fila_cesta(
                    f'<div class="bm-cesta-nombre">{etiqueta_linea_suelta(linea)}</div>',
                    f"suelto_{linea.linea_id}",
                    lambda l=linea: _quitar_y_rerun(quitar_linea_suelta, l.linea_id),
                    cantidad_texto=f"{abs(linea.cantidad):g}",
                    on_menos=lambda l=linea, p=paso: _ok_o_error(ajustar_cantidad_suelto(l.linea_id, -p)),
                    on_mas=lambda l=linea, p=paso: _ok_o_error(ajustar_cantidad_suelto(l.linea_id, p)),
                    ayuda_quitar="Eliminar producto",
                )

        total = coste_total_cesta()
        st.markdown(
            '<div class="bm-cesta-total">'
            "<span>Coste estimado</span>"
            f"<span>{repo.formato_precio(total)}</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.caption("Coste calculado por FIFO según lotes actuales.")

        if st.button("Vaciar cesta", use_container_width=True, key="desayuno_vaciar_cesta"):
            limpiar_cesta()
            st.rerun()


def _render_registro_desayuno() -> None:
    repo = get_repository()
    servicio = TipoServicio.DESAYUNO.value

    st.markdown("#### Registro rápido de desayuno")
    st.caption(
        "Añada recetas o productos sueltos a la cesta. Use cantidades positivas (c/ extra) "
        "o negativas (s/) para ajustar ingredientes."
    )
    aviso_servicios_pendientes(key_prefix="desayuno_aviso_serv")

    col_buscar, col_cesta = st.columns([2, 1])

    with col_buscar:
        fecha = st.date_input("Fecha", value=date.today(), max_value=date.today(), key="desayuno_fecha")
        num_huespedes = st.number_input(
            "Nº de huéspedes",
            min_value=1,
            value=30,
            step=1,
            key="desayuno_num_huespedes",
        )

        section_divider()
        st.markdown("##### Añadir receta")
        recetas = listar_recetas(servicio_disponible=servicio)
        if recetas:
            mapa_recetas = {r.nombre: r.id for r in recetas}
            receta_nombre = st.selectbox(
                "Receta",
                list(mapa_recetas.keys()),
                key="desayuno_sel_receta",
            )
            receta_id = mapa_recetas[receta_nombre]

            porciones = st.number_input(
                "Porciones",
                min_value=1.0,
                value=1.0,
                step=1.0,
                format="%.0f",
                key="desayuno_porciones",
            )

            st.caption("Extras u omisiones para esta receta (antes de añadir a la cesta)")
            catalogo = productos_catalogo("", servicio=servicio)
            producto_mod = render_buscador_producto(
                catalogo,
                "desayuno_mod_receta",
                label="Buscar producto",
                placeholder="Escriba para buscar producto...",
            )
            if producto_mod:
                unidad_mod = producto_mod.get("unidad", "Ud")
                cant_mod = st.number_input(
                    "Cantidad (+ extra / − omitir)",
                    value=float(paso_unidad(unidad_mod)),
                    step=paso_unidad(unidad_mod),
                    format=formato_number_input(unidad_mod),
                    key="desayuno_cant_mod",
                )
                cant_mod = normalizar_cantidad(cant_mod, unidad_mod)
                if st.button(
                    "Añadir extra/omisión",
                    key="desayuno_btn_mod",
                    use_container_width=True,
                ):
                    resultado = anadir_mod_pendiente_receta(producto_mod["id"], cant_mod)
                    if resultado.ok:
                        st.success(resultado.mensaje)
                        st.rerun()
                    else:
                        st.error(resultado.mensaje)

            mods = get_mods_pendientes()
            if mods:
                st.markdown("**Pendientes para esta receta:**")
                for mod in mods:
                    col_txt, col_q = st.columns([5, 1])
                    etiqueta = f"c/ extra {mod.nombre}" if mod.cantidad > 0 else f"s/ {mod.nombre}"
                    with col_txt:
                        st.markdown(f"- {etiqueta} — {abs(mod.cantidad):g} {mod.unidad}")
                    with col_q:
                        if st.button("✕", key=f"quitar_mod_{mod.mod_id}"):
                            quitar_mod_pendiente(mod.mod_id)
                            st.rerun()

            if st.button(
                "Añadir receta a la cesta",
                type="secondary",
                use_container_width=True,
                key="desayuno_btn_receta",
            ):
                resultado = anadir_receta_a_cesta(receta_id, porciones, list(mods))
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)
        else:
            empty_state(
                "No hay recetas con servicio desayuno disponible. "
                "Configúrelas en Recetas.",
                icon="📖",
            )

        section_divider()
        st.markdown("##### Añadir producto suelto")
        todos_productos = productos_catalogo("", servicio=servicio)
        producto_sel = render_buscador_producto(
            todos_productos,
            "desayuno",
            label="Buscar producto",
            placeholder="Escriba el nombre del producto...",
        )
        if producto_sel:
            unidad_prod = producto_sel.get("unidad", "Ud")
            cantidad = st.number_input(
                "Cantidad (+ extra / − omitir)",
                value=float(paso_unidad(unidad_prod)),
                step=paso_unidad(unidad_prod),
                format=formato_number_input(unidad_prod),
                key="desayuno_cantidad",
            )
            cantidad = normalizar_cantidad(cantidad, unidad_prod)
            if st.button(
                "Añadir producto a la cesta",
                type="secondary",
                use_container_width=True,
                key="desayuno_btn_anadir",
            ):
                resultado = anadir_a_cesta(producto_sel["id"], cantidad)
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)
        elif todos_productos:
            empty_state("No hay coincidencias para la búsqueda.", icon="🔍")
        else:
            empty_state(
                "No hay productos con servicio desayuno disponible. "
                "Configúrelos en Stock.",
                icon="🔍",
            )

    with col_cesta:
        _render_cesta_desayuno(repo)

        if st.button("Registrar desayuno", type="primary", use_container_width=True, key="btn_registrar_desayuno"):
            resultado = registrar_desayuno(fecha, int(num_huespedes))
            if resultado.ok:
                st.session_state.pop(STOCK_PENDIENTE_KEY, None)
                st.success(resultado.mensaje)
                st.rerun()
            elif resultado.codigo == "STOCK_INSUFICIENTE":
                st.session_state[STOCK_PENDIENTE_KEY] = True
                st.error(resultado.mensaje)
                if resultado.detalle_stock:
                    for linea in resultado.detalle_stock:
                        st.markdown(f"- {linea}")
            else:
                st.session_state.pop(STOCK_PENDIENTE_KEY, None)
                st.error(resultado.mensaje)

        if st.session_state.get(STOCK_PENDIENTE_KEY):
            st.warning("Hay productos sin stock suficiente. Puede ignorar la validación y registrar igual.")
            if st.button(
                "Ignorar y registrar igual",
                type="secondary",
                use_container_width=True,
                key="btn_ignorar_stock",
            ):
                resultado = registrar_desayuno(fecha, int(num_huespedes), ignorar_stock=True)
                if resultado.ok:
                    st.session_state.pop(STOCK_PENDIENTE_KEY, None)
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)

    section_divider()
    st.markdown("#### Historial de desayunos")
    st.caption("Solo se muestran los registros de la semana en curso. Las semanas anteriores quedan archivadas y disponibles en las exportaciones.")
    _boton_exportar_semana(desayuno_service.configuracion_exportacion(), "desayuno")

    desayunos = repo.desayunos_ordenados()
    desayunos_semana = [d for d in desayunos if d.fecha >= _lunes_semana_actual()]
    if desayunos_semana:
        st.dataframe(
            {
                "Fecha": [formato_fecha(d.fecha) for d in desayunos_semana],
                "Hora": [d.hora.strftime("%H:%M") if d.hora else "—" for d in desayunos_semana],
                "Huéspedes": [d.num_huespedes for d in desayunos_semana],
                "Elementos": [len(d.lineas) + len(d.registros_recetas) for d in desayunos_semana],
                "Cantidad total": [round(sum(abs(l.cantidad) for l in d.lineas), 2) for d in desayunos_semana],
                "Coste": [repo.formato_precio(d.coste_total) for d in desayunos_semana],
                "Registrado por": [d.registrado_por for d in desayunos_semana],
            },
            use_container_width=True,
            hide_index=True,
        )

        opciones_detalle = {
            f"{d.id} — {formato_fecha(d.fecha)} {d.hora.strftime('%H:%M') if d.hora else ''}".strip(): d
            for d in desayunos_semana
        }
        etiqueta_sel = st.selectbox(
            "Ver detalle de un registro",
            ["—"] + list(opciones_detalle.keys()),
            key="desayuno_detalle_sel",
        )
        if etiqueta_sel != "—":
            _render_detalle_desayuno(opciones_detalle[etiqueta_sel])
    else:
        empty_state("No hay registros de desayuno esta semana.", icon="📅")


def _render_registro_merma() -> None:
    from app.core.services.merma_service import (
        MOTIVOS,
        OPCIONES_SERVICIO_UI,
        anadir_a_cesta_merma,
        configuracion_exportacion as configuracion_exportacion_merma,
        coste_total_cesta_merma,
        etiqueta_servicio_merma,
        get_cesta_merma,
        limpiar_cesta_merma,
        lotes_disponibles,
        productos_con_stock,
        quitar_de_cesta_merma,
        registrar_merma,
        valor_servicio_desde_ui,
    )
    from app.ui.search import opciones_desde_etiquetas

    repo = get_repository()

    st.markdown("#### Registro de merma")
    st.caption(
        "Seleccione primero dónde se produjo la merma; luego elija producto y lote. "
        "Lista vacía de servicios ≠ todos (excepto Almacén / General)."
    )
    aviso_servicios_pendientes(key_prefix="merma_aviso_serv")

    col_buscar, col_cesta = st.columns([2, 1])

    with col_buscar:
        fecha = st.date_input("Fecha", value=date.today(), max_value=date.today(), key="merma_fecha")
        servicio_ui = st.selectbox(
            "¿Dónde se produjo la merma?",
            OPCIONES_SERVICIO_UI,
            key="merma_servicio",
        )
        servicio_val = valor_servicio_desde_ui(servicio_ui)
        if not servicio_val:
            st.info("Seleccione el servicio o área para filtrar productos disponibles.")
            todos_productos = []
        else:
            todos_productos = productos_con_stock("", servicio=servicio_val)

        producto_sel = None
        if todos_productos or servicio_val:
            producto_sel = render_buscador_producto(todos_productos, "merma")

        if producto_sel:
            producto_id = producto_sel["id"]

            lotes = lotes_disponibles(producto_id)
            if lotes:
                opciones_lotes = opciones_desde_etiquetas(lotes)
                lote_sel = render_autocomplete(
                    opciones_lotes,
                    "merma_lote",
                    "Lote (fecha de compra)",
                    "Buscar lote por fecha o ID...",
                    etiqueta_selectbox="Lote",
                )
                if not lote_sel:
                    st.caption("Seleccione un lote de la lista.")
                else:
                    lote_id = lote_sel["id"]

                    motivo = st.selectbox("Motivo", MOTIVOS, key="merma_motivo")
                    unidad_merma = producto_sel.get("unidad", "Ud") if producto_sel else "Ud"
                    cantidad = st.number_input(
                        "Cantidad",
                        min_value=0.0,
                        value=0.0,
                        step=paso_unidad(unidad_merma),
                        format=formato_number_input(unidad_merma),
                        key="merma_cantidad",
                    )
                    cantidad = normalizar_cantidad(cantidad, unidad_merma)
                    comentario = st.text_area("Comentario (opcional)", key="merma_comentario")

                    if st.button("Añadir a la cesta", type="secondary", use_container_width=True, key="merma_btn_anadir"):
                        resultado = anadir_a_cesta_merma(
                            lote_id, cantidad, motivo, servicio_val, comentario,
                        )
                        if resultado.ok:
                            st.success(resultado.mensaje)
                            st.rerun()
                        else:
                            st.error(resultado.mensaje)
            else:
                empty_state("No hay lotes con stock para este producto.", icon="🏷️")
        elif not servicio_val:
            pass
        elif todos_productos:
            empty_state("No hay coincidencias para la búsqueda.", icon="🔍")
        else:
            empty_state(
                "No hay productos con stock para este servicio. "
                "Configure servicios disponibles en Stock (Almacén / General no filtra).",
                icon="🔍",
            )

    with col_cesta:
        cesta = get_cesta_merma()
        with st.container(border=True):
            st.markdown(
                '<div class="bm-cesta-scope"></div>'
                '<div class="bm-cesta-title">Merma</div>',
                unsafe_allow_html=True,
            )

            if not cesta:
                st.markdown(
                    '<p class="bm-cesta-empty">Todavía no has añadido productos a la merma.</p>',
                    unsafe_allow_html=True,
                )
            else:
                lineas_orden = sorted(cesta, key=lambda l: _clave_orden(l.nombre))
                for indice, linea in enumerate(lineas_orden):
                    if indice > 0:
                        st.markdown('<div class="bm-cesta-divider"></div>', unsafe_allow_html=True)

                    servicio_txt = etiqueta_servicio_merma(linea.tipo_servicio_snapshot)
                    detalle = (
                        f"Lote {linea.lote_id} · compra {linea.fecha_compra_txt} · "
                        f"{linea.motivo} · {servicio_txt}"
                    )
                    if linea.comentario:
                        detalle += f" · {linea.comentario}"

                    _fila_cesta(
                        f'<div class="bm-cesta-nombre">{linea.nombre} — {linea.cantidad:g} {linea.unidad}</div>'
                        f'<div class="bm-cesta-detalle">{detalle}</div>',
                        f"merma_{linea.lote_id}_{linea.motivo}_{linea.tipo_servicio_snapshot}",
                        lambda l=linea: _quitar_y_rerun(
                            quitar_de_cesta_merma,
                            l.lote_id,
                            l.motivo,
                            l.tipo_servicio_snapshot,
                        ),
                        ayuda_quitar="Eliminar de la cesta",
                    )

                total = coste_total_cesta_merma()
                st.markdown(
                    '<div class="bm-cesta-total">'
                    "<span>Coste estimado</span>"
                    f"<span>{repo.formato_precio(total)}</span>"
                    "</div>",
                    unsafe_allow_html=True,
                )

        if cesta and st.button("Vaciar cesta", use_container_width=True, key="merma_vaciar_cesta"):
            limpiar_cesta_merma()
            st.rerun()

        if st.button("Registrar merma", type="primary", use_container_width=True, key="btn_registrar_merma"):
            resultado = registrar_merma(fecha)
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)

    section_divider()
    st.markdown("#### Historial de merma")
    st.caption("Solo se muestran los registros de la semana en curso. Las semanas anteriores quedan archivadas y disponibles en las exportaciones.")
    _boton_exportar_semana(configuracion_exportacion_merma(), "merma")

    mermas = repo.mermas_ordenadas()
    mermas_semana = [m for m in mermas if m.fecha >= _lunes_semana_actual()]
    if mermas_semana:
        st.dataframe(
            {
                "Fecha": [formato_fecha(m.fecha) for m in mermas_semana],
                "Hora": [m.hora.strftime("%H:%M") if m.hora else "—" for m in mermas_semana],
                "Productos": [_lineas_merma_texto(repo, m) for m in mermas_semana],
                "Coste": [repo.formato_precio(m.coste_total) for m in mermas_semana],
                "Registrado por": [m.registrado_por for m in mermas_semana],
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        empty_state("No hay registros de merma esta semana.", icon="📋")


_SUBTABS = {
    "Registro desayuno": _render_registro_desayuno,
    "Registro merma": _render_registro_merma,
}


def render_registro_desayuno() -> None:
    """Contenido de desayuno sin cabecera (p. ej. pestaña Registros)."""
    _render_registro_desayuno()


def render_registro_merma() -> None:
    """Contenido de merma sin cabecera (p. ej. pestaña Registros)."""
    _render_registro_merma()


def render() -> None:
    page_header("Desayuno", "Registro diario de consumo y merma")

    selected = render_sub_tabs(list(_SUBTABS.keys()), key="desayuno_subtab")
    _SUBTABS[selected]()
