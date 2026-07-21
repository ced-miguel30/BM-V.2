"""Desayuno — registro de consumo y merma."""

import unicodedata
from datetime import date

import streamlit as st

from app.core.services.data_service import get_repository
from app.core.services.desayuno_service import (
    PASO_CANTIDAD,
    ajustar_cantidad_suelto,
    ajustar_linea_grupo,
    ajustar_porciones_grupo,
    anadir_a_cesta,
    anadir_mod_pendiente_receta,
    anadir_receta_a_cesta,
    coste_total_cesta,
    etiqueta_linea_receta,
    etiqueta_linea_suelta,
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
from app.core.services.formatting import formato_fecha
from app.core.services.receta_service import listar_recetas
from app.ui.components import empty_state, page_header, render_sub_tabs, section_divider
from app.ui.search import render_autocomplete, render_buscador_producto

STOCK_PENDIENTE_KEY = "bm_stock_pendiente_registro"


def _lineas_desayuno_texto(repo, desayuno) -> str:
    partes = []
    for linea in desayuno.lineas:
        nombre = repo.get_nombre_producto(linea.producto_id)
        producto = repo.get_producto(linea.producto_id)
        unidad = producto.unidad.value if producto else ""
        texto = f"{nombre} ({linea.cantidad:g} {unidad})"
        if linea.es_extra:
            texto += " [extra]"
        partes.append(texto)
    return ", ".join(partes)


def _lineas_merma_texto(repo, merma) -> str:
    partes = []
    for linea in merma.lineas:
        nombre = repo.get_nombre_producto(linea.producto_id)
        partes.append(f"{nombre} ({linea.cantidad}) — {linea.motivo.value}")
    return ", ".join(partes)


def _clave_orden(texto: str) -> str:
    """Clave de orden alfabético insensible a mayúsculas/minúsculas y acentos."""
    normalizado = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in normalizado if not unicodedata.combining(c))
    return sin_acentos.casefold()


def _ok_o_error(resultado) -> None:
    if resultado.ok:
        st.rerun()
    else:
        st.error(resultado.mensaje)


def _quitar_y_rerun(accion, *args) -> None:
    accion(*args)
    st.rerun()


def _fila_desayuno(
    nombre_html: str,
    cantidad_texto: str,
    key_prefix: str,
    on_menos,
    on_mas,
    on_quitar,
    *,
    ayuda_quitar: str = "Eliminar",
) -> None:
    col_nombre, col_menos, col_qty, col_mas, col_quitar = st.columns(
        [5, 1, 1, 1, 1], vertical_alignment="center",
    )
    with col_nombre:
        st.markdown(nombre_html, unsafe_allow_html=True)
    with col_menos:
        if st.button("−", key=f"{key_prefix}_menos", use_container_width=True, help="Disminuir"):
            on_menos()
    with col_qty:
        st.markdown(f'<div class="bm-desayuno-qty">{cantidad_texto}</div>', unsafe_allow_html=True)
    with col_mas:
        if st.button("+", key=f"{key_prefix}_mas", use_container_width=True, help="Aumentar"):
            on_mas()
    with col_quitar:
        if st.button(
            "",
            key=f"{key_prefix}_quitar",
            icon=":material/delete:",
            help=ayuda_quitar,
            use_container_width=True,
        ):
            on_quitar()


def _render_cesta_desayuno(repo) -> None:
    grupos = get_cesta_recetas()
    cesta = get_cesta()
    hay_contenido = bool(grupos or cesta)

    with st.container(border=True):
        st.markdown(
            '<div class="bm-desayuno-scope"></div>'
            '<div class="bm-desayuno-title">Desayuno</div>',
            unsafe_allow_html=True,
        )

        if not hay_contenido:
            st.markdown(
                '<p class="bm-desayuno-empty">Todavía no has añadido productos al desayuno.</p>',
                unsafe_allow_html=True,
            )
            return

        elementos = [("receta", g) for g in grupos] + [("suelto", l) for l in cesta]
        elementos.sort(
            key=lambda e: _clave_orden(e[1].nombre_receta if e[0] == "receta" else e[1].nombre)
        )

        for indice, (tipo, elemento) in enumerate(elementos):
            if indice > 0:
                st.markdown('<div class="bm-desayuno-divider"></div>', unsafe_allow_html=True)

            if tipo == "receta":
                grupo = elemento
                _fila_desayuno(
                    f'<div class="bm-desayuno-nombre">{grupo.nombre_receta}</div>',
                    f"{grupo.porciones:g}",
                    f"grp_{grupo.grupo_id}",
                    lambda g=grupo: _ok_o_error(ajustar_porciones_grupo(g.grupo_id, -1)),
                    lambda g=grupo: _ok_o_error(modificar_porciones_grupo(g.grupo_id, g.porciones + 1)),
                    lambda g=grupo: _quitar_y_rerun(quitar_grupo_receta, g.grupo_id),
                    ayuda_quitar="Eliminar receta",
                )
                for ing in grupo.ingredientes:
                    paso = paso_linea_grupo(grupo.grupo_id, ing.linea_id)
                    _fila_desayuno(
                        f'<div class="bm-desayuno-ingrediente">{etiqueta_linea_receta(ing)}</div>',
                        f"{abs(ing.cantidad):g}",
                        f"ing_{grupo.grupo_id}_{ing.linea_id}",
                        lambda g=grupo, i=ing, p=paso: _ok_o_error(
                            ajustar_linea_grupo(g.grupo_id, i.linea_id, -p)
                        ),
                        lambda g=grupo, i=ing, p=paso: _ok_o_error(
                            ajustar_linea_grupo(g.grupo_id, i.linea_id, p)
                        ),
                        lambda g=grupo, i=ing: _quitar_y_rerun(
                            quitar_linea_grupo, g.grupo_id, i.linea_id
                        ),
                        ayuda_quitar="Eliminar ingrediente",
                    )
            else:
                linea = elemento
                paso = paso_linea_suelta(linea.linea_id)
                _fila_desayuno(
                    f'<div class="bm-desayuno-nombre">{etiqueta_linea_suelta(linea)}</div>',
                    f"{abs(linea.cantidad):g}",
                    f"suelto_{linea.linea_id}",
                    lambda l=linea, p=paso: _ok_o_error(ajustar_cantidad_suelto(l.linea_id, -p)),
                    lambda l=linea, p=paso: _ok_o_error(ajustar_cantidad_suelto(l.linea_id, p)),
                    lambda l=linea: _quitar_y_rerun(quitar_linea_suelta, l.linea_id),
                    ayuda_quitar="Eliminar producto",
                )

        total = coste_total_cesta()
        st.markdown(
            '<div class="bm-desayuno-total">'
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

    st.markdown("#### Registro rápido de desayuno")
    st.caption(
        "Añada recetas o productos sueltos a la cesta. Use cantidades positivas (c/ extra) "
        "o negativas (s/) para ajustar ingredientes."
    )

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
        recetas = listar_recetas()
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
            catalogo = productos_catalogo("")
            producto_mod = render_buscador_producto(
                catalogo,
                "desayuno_mod_receta",
                label="Buscar producto",
                placeholder="Escriba para buscar producto...",
            )
            if producto_mod:
                cant_mod = st.number_input(
                    "Cantidad (+ extra / − omitir)",
                    value=1.0,
                    step=PASO_CANTIDAD,
                    format="%.1f",
                    key="desayuno_cant_mod",
                )
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
            empty_state("No hay recetas definidas. Créelas en la sección Recetas.", icon="📖")

        section_divider()
        st.markdown("##### Añadir producto suelto")
        todos_productos = productos_catalogo("")
        producto_sel = render_buscador_producto(
            todos_productos,
            "desayuno",
            label="Buscar producto",
            placeholder="Escriba el nombre del producto...",
        )
        if producto_sel:
            cantidad = st.number_input(
                "Cantidad (+ extra / − omitir)",
                value=1.0,
                step=PASO_CANTIDAD,
                format="%.1f",
                key="desayuno_cantidad",
            )
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
        elif productos_catalogo(""):
            empty_state("No hay coincidencias para la búsqueda.", icon="🔍")
        else:
            empty_state("No hay productos registrados en el catálogo.", icon="🔍")

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

    desayunos = repo.desayunos_ordenados()
    if desayunos:
        st.dataframe(
            {
                "Fecha": [formato_fecha(d.fecha) for d in desayunos],
                "Hora": [d.hora.strftime("%H:%M") if d.hora else "—" for d in desayunos],
                "Huéspedes": [d.num_huespedes for d in desayunos],
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
    from app.core.services.merma_service import (
        MOTIVOS,
        anadir_a_cesta_merma,
        coste_total_cesta_merma,
        get_cesta_merma,
        limpiar_cesta_merma,
        lotes_disponibles,
        productos_con_stock,
        quitar_de_cesta_merma,
        registrar_merma,
    )
    from app.ui.search import opciones_desde_etiquetas

    repo = get_repository()

    st.markdown("#### Registro de merma")
    st.caption("Seleccione el lote concreto (con fecha de compra) y añádalo a la cesta.")

    col_buscar, col_cesta = st.columns([2, 1])

    with col_buscar:
        todos_productos = productos_con_stock("")
        producto_sel = render_buscador_producto(todos_productos, "merma")
        fecha = st.date_input("Fecha", value=date.today(), max_value=date.today(), key="merma_fecha")

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
                    cantidad = st.number_input(
                        "Cantidad",
                        min_value=0.0,
                        value=0.0,
                        step=0.1,
                        format="%.2f",
                        key="merma_cantidad",
                    )
                    comentario = st.text_area("Comentario (opcional)", key="merma_comentario")

                    if st.button("Añadir a la cesta", type="secondary", use_container_width=True, key="merma_btn_anadir"):
                        resultado = anadir_a_cesta_merma(lote_id, cantidad, motivo, comentario)
                        if resultado.ok:
                            st.success(resultado.mensaje)
                            st.rerun()
                        else:
                            st.error(resultado.mensaje)
            else:
                empty_state("No hay lotes con stock para este producto.", icon="🏷️")
        elif todos_productos:
            empty_state("No hay coincidencias para la búsqueda.", icon="🔍")
        else:
            empty_state("No hay productos con stock disponible.", icon="🔍")

    with col_cesta:
        st.markdown(
            """
            <div class="bm-basket-panel">
                <div class="bm-basket-title">Cesta de merma</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        cesta = get_cesta_merma()
        if cesta:
            for linea in cesta:
                col_info, col_quitar = st.columns([4, 1])
                with col_info:
                    st.markdown(
                        f"**{linea.nombre}** — {linea.cantidad:g} {linea.unidad}  \n"
                        f"Lote {linea.lote_id} · compra {linea.fecha_compra_txt}  \n"
                        f"*{linea.motivo}*"
                    )
                with col_quitar:
                    if st.button("✕", key=f"quitar_merma_{linea.lote_id}_{linea.motivo}", help="Quitar"):
                        quitar_de_cesta_merma(linea.lote_id, linea.motivo)
                        st.rerun()

            total = coste_total_cesta_merma()
            st.markdown(f"**Coste estimado:** {repo.formato_precio(total)}")

            if st.button("Vaciar cesta", use_container_width=True, key="merma_vaciar_cesta"):
                limpiar_cesta_merma()
                st.rerun()
        else:
            empty_state("La cesta está vacía", icon="🧺")

        if st.button("Registrar merma", type="primary", use_container_width=True, key="btn_registrar_merma"):
            resultado = registrar_merma(fecha)
            if resultado.ok:
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)

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
