"""Desayuno — registro de consumo (UI compartida) y merma."""

from datetime import date

import streamlit as st

from app.core.models import CategoriaReceta
from app.core.services.data_service import get_repository
from app.core.services.desayuno_service import desayuno_registro
from app.core.services.exportacion_semanal_service import limite_semana
from app.core.services.formatting import formato_fecha
from app.core.services.unidad_service import (
    formato_number_input,
    normalizar_cantidad,
    paso_unidad,
)
from app.ui.cesta_render import (
    boton_exportar_semana as _boton_exportar_semana,
    clave_orden as _clave_orden,
    fila_cesta as _fila_cesta,
    quitar_y_rerun as _quitar_y_rerun,
)
from app.ui.components import (
    aviso_servicios_pendientes,
    empty_state,
    page_header,
    render_sub_tabs,
    section_divider,
)
from app.ui.registro_servicio_page import render_pagina_registro_servicio
from app.ui.search import render_autocomplete, render_buscador_producto


def _lineas_merma_texto(repo, merma) -> str:
    partes = []
    for linea in merma.lineas:
        nombre = linea.producto_nombre_snapshot or repo.get_nombre_producto(linea.producto_id)
        partes.append(f"{nombre} ({linea.cantidad}) — {linea.motivo.value}")
    return ", ".join(partes)


def _lunes_semana_actual() -> date:
    lunes, _ = limite_semana(date.today())
    return lunes


def _render_registro_merma() -> None:
    from app.core.services.merma_service import (
        MOTIVOS,
        OPCIONES_SERVICIO_UI,
        OPCIONES_TURNO_UI,
        PLACEHOLDER_RESPONSABLE,
        anadir_a_cesta_merma,
        configuracion_exportacion as configuracion_exportacion_merma,
        coste_total_cesta_merma,
        etiqueta_servicio_merma,
        etiqueta_turno_merma,
        get_cesta_merma,
        limpiar_cesta_merma,
        listar_responsables_merma,
        lotes_disponibles,
        productos_con_stock,
        quitar_de_cesta_merma,
        registrar_merma,
        valor_servicio_desde_ui,
        valor_turno_desde_ui,
    )
    from app.ui.search import opciones_desde_etiquetas

    repo = get_repository()

    st.markdown("#### Registro de merma")
    st.caption(
        "Orden: fecha → servicio → turno → responsable → producto → lote → motivo → cantidad. "
        "Lista vacía de servicios ≠ todos (excepto Almacén / General)."
    )
    aviso_servicios_pendientes(key_prefix="merma_aviso_serv")

    col_buscar, col_cesta = st.columns([2, 1])

    with col_buscar:
        fecha = st.date_input("Fecha", value=date.today(), max_value=date.today(), key="merma_fecha")
        # Aplicar cambio pendiente ANTES del selectbox (Streamlit no permite
        # mutar la key del widget una vez instanciado en el mismo run).
        if "merma_servicio_pending" in st.session_state:
            st.session_state["merma_servicio"] = st.session_state.pop(
                "merma_servicio_pending"
            )
        servicio_ui = st.selectbox(
            "¿Dónde se produjo la merma?",
            OPCIONES_SERVICIO_UI,
            key="merma_servicio",
        )
        servicio_val = valor_servicio_desde_ui(servicio_ui)
        turno_ui = st.selectbox("Turno", OPCIONES_TURNO_UI, key="merma_turno")
        turno_val = valor_turno_desde_ui(turno_ui)

        responsables = listar_responsables_merma(solo_activos=True)
        if not responsables:
            st.warning(
                "No hay responsables activos. Sin responsable no se pueden elegir productos."
            )
            col_ir, col_crear = st.columns(2)
            with col_ir:
                if st.button("Ir a Responsables merma", key="merma_ir_responsables", use_container_width=True):
                    st.session_state["nav_section_pending"] = "Configuración"
                    st.session_state["settings_subtab_pending"] = "Responsables merma"
                    st.rerun()
            with col_crear:
                from app.core.services.merma_service import crear_responsable_merma

                nombre_sugerido = next(
                    (u.nombre for u in repo.data.usuarios if u.id == repo.data.usuario_actual_id),
                    None,
                ) or (repo.data.usuarios[0].nombre if repo.data.usuarios else "Cocina")
                if st.button(
                    f"Crear «{nombre_sugerido}»",
                    key="merma_crear_resp_rapido",
                    type="primary",
                    use_container_width=True,
                ):
                    resultado = crear_responsable_merma(nombre_sugerido)
                    if resultado.ok:
                        st.success(resultado.mensaje)
                        st.rerun()
                    else:
                        st.error(resultado.mensaje)
            mapa_resp: dict[str, str] = {}
            resp_sel = PLACEHOLDER_RESPONSABLE
        else:
            mapa_resp = {r.nombre: r.id for r in responsables}
            opciones_resp = [PLACEHOLDER_RESPONSABLE] + list(mapa_resp.keys())
            resp_sel = st.selectbox("Responsable", opciones_resp, key="merma_responsable")

        resp_id = mapa_resp.get(resp_sel) if resp_sel != PLACEHOLDER_RESPONSABLE else None
        resp_nombre = resp_sel if resp_id else None

        if not servicio_val:
            st.info("Seleccione el servicio o área para filtrar productos disponibles.")
            todos_productos = []
        elif not turno_val or not resp_id:
            st.info("Seleccione turno y responsable antes de elegir producto.")
            todos_productos = []
        else:
            todos_productos = productos_con_stock("", servicio=servicio_val)

        producto_sel = None
        if todos_productos:
            producto_sel = render_buscador_producto(todos_productos, "merma")

        if producto_sel and servicio_val and turno_val and resp_id:
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
                            turno_snapshot=turno_val,
                            responsable_id=resp_id,
                            responsable_nombre=resp_nombre,
                        )
                        if resultado.ok:
                            st.success(resultado.mensaje)
                            st.rerun()
                        else:
                            st.error(resultado.mensaje)
            else:
                empty_state("No hay lotes con stock para este producto.", icon="🏷️")
        elif not servicio_val or not turno_val or not resp_id:
            pass
        elif todos_productos:
            empty_state("No hay coincidencias para la búsqueda.", icon="🔍")
        else:
            con_stock_total = productos_con_stock("")
            n_total = len(con_stock_total)
            if n_total == 0:
                empty_state(
                    "No hay productos con stock disponible en ningún lote.",
                    icon="🔍",
                )
            else:
                etiqueta_serv = servicio_ui if servicio_val else "este servicio"
                st.warning(
                    f"Ningún producto con stock está configurado para «{etiqueta_serv}». "
                    f"Hay {n_total} producto(s) con stock, pero lista vacía de servicios ≠ todos. "
                    "Elija «Almacén / General» para verlos todos, o asigne servicios en Stock "
                    "(Configurar producto/bebida existente)."
                )
                col_g, col_s = st.columns(2)
                with col_g:
                    if st.button(
                        "Usar Almacén / General",
                        key="merma_usar_general",
                        use_container_width=True,
                    ):
                        st.session_state["merma_servicio_pending"] = "Almacén / General"
                        st.rerun()
                with col_s:
                    if st.button(
                        "Ir a Stock",
                        key="merma_ir_stock",
                        use_container_width=True,
                    ):
                        st.session_state["nav_section_pending"] = "Stock"
                        st.rerun()

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
                    turno_txt = etiqueta_turno_merma(linea.turno_snapshot)
                    detalle = (
                        f"Lote {linea.lote_id} · compra {linea.fecha_compra_txt} · "
                        f"{linea.motivo} · {servicio_txt} · {turno_txt} · "
                        f"{linea.responsable_nombre}"
                    )
                    if linea.comentario:
                        detalle += f" · {linea.comentario}"

                    _fila_cesta(
                        f'<div class="bm-cesta-nombre">{linea.nombre} — {linea.cantidad:g} {linea.unidad}</div>'
                        f'<div class="bm-cesta-detalle">{detalle}</div>',
                        (
                            f"merma_{linea.lote_id}_{linea.motivo}_"
                            f"{linea.tipo_servicio_snapshot}_{linea.turno_snapshot}_"
                            f"{linea.responsable_id}"
                        ),
                        lambda l=linea: _quitar_y_rerun(
                            quitar_de_cesta_merma,
                            l.lote_id,
                            l.motivo,
                            l.tipo_servicio_snapshot,
                            l.turno_snapshot,
                            l.responsable_id,
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
    st.caption(
        "Solo se muestran los registros de la semana en curso. "
        "Líneas antiguas sin turno/responsable muestran «Dato no disponible» en exportación."
    )
    _boton_exportar_semana(configuracion_exportacion_merma(), "merma")

    mermas = repo.mermas_ordenadas()
    mermas_semana = [m for m in mermas if m.fecha >= _lunes_semana_actual()]
    mermas_activas = [m for m in mermas_semana if not getattr(m, "anulado", False)]
    mermas_anuladas = [m for m in mermas_semana if getattr(m, "anulado", False)]

    if mermas_activas:
        st.dataframe(
            {
                "Fecha": [formato_fecha(m.fecha) for m in mermas_activas],
                "Hora": [m.hora.strftime("%H:%M") if m.hora else "—" for m in mermas_activas],
                "Productos": [_lineas_merma_texto(repo, m) for m in mermas_activas],
                "Coste": [repo.formato_precio(m.coste_total) for m in mermas_activas],
                "Registrado por": [m.registrado_por for m in mermas_activas],
            },
            use_container_width=True,
            hide_index=True,
        )
    elif not mermas_semana:
        empty_state("No hay registros de merma esta semana.", icon="📋")
    else:
        st.caption("No hay mermas activas esta semana (solo anuladas).")

    if mermas_anuladas:
        st.caption(
            f"{len(mermas_anuladas)} merma(s) anulada(s) esta semana "
            "(visibles en el selector de detalle)."
        )

    if mermas_semana:
        from app.core.services.anulacion_merma_service import (
            anular_merma,
            merma_esta_anulada,
            puede_anular_merma,
            previsualizar_anulacion_merma,
        )
        from app.core.storage.session_store import get_data

        opciones = {}
        for m in mermas_semana:
            marca = " [Anulado]" if getattr(m, "anulado", False) else ""
            clave = (
                f"{m.id}{marca} — {formato_fecha(m.fecha)} "
                f"{m.hora.strftime('%H:%M') if m.hora else ''}"
            ).strip()
            opciones[clave] = m
        sel = st.selectbox(
            "Ver detalle / anular merma",
            ["—"] + list(opciones.keys()),
            key="merma_detalle_sel",
        )
        if sel != "—":
            merma = opciones[sel]
            data = get_data()
            if merma_esta_anulada(merma):
                st.warning("Estado: **Anulado**")
                st.caption(
                    f"Fecha: {formato_fecha(merma.fecha_anulacion) if merma.fecha_anulacion else '—'} "
                    f"{merma.hora_anulacion.strftime('%H:%M') if merma.hora_anulacion else ''} "
                    f"· Por: {merma.anulado_por or '—'} "
                    f"· Motivo: {merma.motivo_anulacion or '—'} "
                    f"· Ref: {merma.referencia_anulacion or '—'}"
                )
            else:
                st.caption("Estado: Activo")

            st.dataframe(
                {
                    "Producto": [
                        ln.producto_nombre_snapshot or repo.get_nombre_producto(ln.producto_id)
                        for ln in merma.lineas
                    ],
                    "Lote": [ln.lote_id or "—" for ln in merma.lineas],
                    "Cantidad": [ln.cantidad for ln in merma.lineas],
                    "Motivo": [ln.motivo.value for ln in merma.lineas],
                    "Coste": [ln.coste for ln in merma.lineas],
                },
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("##### Anulación")
            puede = puede_anular_merma(data, merma)
            preview = previsualizar_anulacion_merma(data, merma)
            if preview.lineas:
                st.dataframe(
                    {
                        "Producto": [ln.nombre for ln in preview.lineas],
                        "Lote": [ln.lote_id for ln in preview.lineas],
                        "Consumido": [ln.cantidad_consumida for ln in preview.lineas],
                        "Restante actual": [ln.cantidad_restante_actual for ln in preview.lineas],
                        "A devolver": [ln.cantidad_a_devolver for ln in preview.lineas],
                        "Resultante": [ln.cantidad_resultante for ln in preview.lineas],
                        "Ud": [ln.unidad for ln in preview.lineas],
                    },
                    use_container_width=True,
                    hide_index=True,
                )
            if not puede.ok:
                for motivo in puede.motivos_bloqueo:
                    st.error(motivo)
            else:
                motivo_a = st.text_input(
                    "Motivo de anulación (obligatorio)",
                    key=f"merma_anul_motivo_{merma.id}",
                )
                ref_a = st.text_input(
                    "Referencia (opcional)",
                    key=f"merma_anul_ref_{merma.id}",
                )
                conf = st.checkbox(
                    "Confirmo anular esta merma y reponer stock a los lotes originales",
                    key=f"merma_anul_ok_{merma.id}",
                )
                if st.button(
                    "Anular merma",
                    type="primary",
                    disabled=not conf or not (motivo_a or "").strip(),
                    key=f"merma_anul_btn_{merma.id}",
                ):
                    resultado = anular_merma(data, merma.id, motivo_a, ref_a)
                    if resultado.ok:
                        st.success(resultado.mensaje)
                        st.rerun()
                    else:
                        st.error(resultado.mensaje)


def render_registro_desayuno() -> None:
    """Desayuno vía UI compartida (sin fusionar storage)."""
    render_pagina_registro_servicio(
        desayuno_registro,
        titulo_pagina="Desayuno",
        subtitulo="Registro diario de consumo",
        etiqueta="Desayuno",
        key_prefix="desayuno",
        categorias_receta=[CategoriaReceta.DESAYUNO, CategoriaReceta.BEBIDAS],
        mensaje_vacio_historial="No hay registros de desayuno esta semana.",
        mostrar_huespedes=True,
        mostrar_cabecera=False,
        min_huespedes=1,
        default_huespedes=30,
    )


def render_registro_merma() -> None:
    """Contenido de merma sin cabecera (p. ej. pestaña Registros)."""
    _render_registro_merma()


def render() -> None:
    page_header("Desayuno", "Registro diario de consumo y merma")
    selected = render_sub_tabs(
        ["Registro desayuno", "Registro merma"],
        key="desayuno_subtab",
    )
    if selected == "Registro merma":
        _render_registro_merma()
    else:
        render_registro_desayuno()
