"""Desayuno — registro de consumo y merma."""

from datetime import date

import streamlit as st

from app.core.services.data_service import get_repository
from app.core.services.desayuno_service import (
    anadir_a_cesta,
    anadir_extra_a_grupo,
    anadir_receta_a_cesta,
    coste_total_cesta,
    get_cesta,
    get_cesta_recetas,
    limpiar_cesta,
    modificar_cantidad_ingrediente,
    productos_disponibles,
    quitar_de_cesta,
    quitar_grupo_receta,
    quitar_ingrediente_grupo,
    registrar_desayuno,
)
from app.core.services.formatting import formato_fecha
from app.core.services.receta_service import recetas_para_selector
from app.ui.components import empty_state, page_header, render_sub_tabs, section_divider
from app.ui.search import opciones_desde_etiquetas, render_autocomplete, render_buscador_producto


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


def _render_cesta_desayuno(repo) -> None:
    st.markdown(
        """
        <div class="bm-basket-panel">
            <div class="bm-basket-title">Cesta del desayuno</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    grupos = get_cesta_recetas()
    cesta = get_cesta()
    hay_contenido = bool(grupos or cesta)

    if grupos:
        st.markdown("##### Recetas")
        for grupo in grupos:
            st.markdown(f"**{grupo.nombre_receta}** (×{grupo.porciones:g})")
            for ing in grupo.ingredientes:
                etiqueta_extra = " `[extra]`" if ing.es_extra else ""
                col_info, col_cant, col_btn, col_quitar = st.columns([3, 2, 1, 1])
                cant_key = f"ing_cant_{grupo.grupo_id}_{ing.producto_id}_{ing.es_extra}"
                with col_info:
                    st.markdown(f"{ing.nombre}{etiqueta_extra}")
                with col_cant:
                    st.number_input(
                        "Cant.",
                        min_value=0.01,
                        value=float(ing.cantidad),
                        step=0.01,
                        format="%.2f",
                        key=cant_key,
                        label_visibility="collapsed",
                    )
                with col_btn:
                    st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
                    if st.button("✓", key=f"save_{cant_key}", help="Guardar cantidad"):
                        nueva_cant = float(st.session_state[cant_key])
                        resultado = modificar_cantidad_ingrediente(
                            grupo.grupo_id, ing.producto_id, nueva_cant,
                        )
                        if resultado.ok:
                            st.rerun()
                        else:
                            st.error(resultado.mensaje)
                with col_quitar:
                    st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
                    if st.button(
                        "✕",
                        key=f"quitar_ing_{grupo.grupo_id}_{ing.producto_id}_{ing.es_extra}",
                        help="Quitar ingrediente",
                    ):
                        quitar_ingrediente_grupo(grupo.grupo_id, ing.producto_id)
                        st.rerun()
                st.caption(f"Unidad: {ing.unidad}")

            todos_productos = productos_disponibles("")
            if todos_productos:
                extra_sel = render_buscador_producto(
                    todos_productos,
                    f"extra_{grupo.grupo_id}",
                )
                if extra_sel:
                    extra_cant = st.number_input(
                        "Cantidad extra",
                        min_value=0.01,
                        value=1.0,
                        step=0.01,
                        format="%.2f",
                        key=f"extra_cant_{grupo.grupo_id}",
                    )
                    if st.button(
                        "Añadir extra",
                        key=f"btn_extra_{grupo.grupo_id}",
                        use_container_width=True,
                    ):
                        resultado = anadir_extra_a_grupo(
                            grupo.grupo_id, extra_sel["id"], extra_cant,
                        )
                        if resultado.ok:
                            st.success(resultado.mensaje)
                            st.rerun()
                        else:
                            st.error(resultado.mensaje)

            if st.button(
                "Quitar receta",
                key=f"quitar_grupo_{grupo.grupo_id}",
                use_container_width=True,
            ):
                quitar_grupo_receta(grupo.grupo_id)
                st.rerun()
            section_divider()

    if cesta:
        st.markdown("##### Productos sueltos")
        for linea in cesta:
            col_nombre, col_quitar = st.columns([4, 1])
            with col_nombre:
                st.markdown(f"**{linea.nombre}** — {linea.cantidad:g} {linea.unidad}")
            with col_quitar:
                if st.button("✕", key=f"quitar_cesta_{linea.producto_id}", help="Quitar"):
                    quitar_de_cesta(linea.producto_id)
                    st.rerun()

    if hay_contenido:
        total = coste_total_cesta()
        st.markdown(f"**Coste estimado:** {repo.formato_precio(total)}")
        st.caption("Coste calculado por FIFO según lotes actuales.")

        if st.button("Vaciar cesta", use_container_width=True, key="desayuno_vaciar_cesta"):
            limpiar_cesta()
            st.rerun()
    else:
        empty_state("La cesta está vacía", icon="🧺")


def _render_registro_desayuno() -> None:
    repo = get_repository()

    st.markdown("#### Registro rápido de desayuno")
    st.caption(
        "Añada productos sueltos o recetas a la cesta. Puede modificar ingredientes "
        "de cada receta antes de registrar. El stock se descuenta por FIFO."
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
        st.markdown("##### Añadir producto suelto")
        todos_productos = productos_disponibles("")
        producto_sel = render_buscador_producto(todos_productos, "desayuno")
        if producto_sel:
            cantidad = st.number_input(
                "Cantidad",
                min_value=0.0,
                value=1.0,
                step=0.1,
                format="%.2f",
                key="desayuno_cantidad",
            )
            if st.button("Añadir producto a la cesta", type="secondary", use_container_width=True, key="desayuno_btn_anadir"):
                resultado = anadir_a_cesta(producto_sel["id"], cantidad)
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)
        elif todos_productos:
            empty_state("No hay coincidencias para la búsqueda.", icon="🔍")
        else:
            empty_state("No hay productos con stock disponible.", icon="🔍")

        section_divider()
        st.markdown("##### Añadir receta")
        recetas = recetas_para_selector()
        if recetas:
            opciones_recetas = opciones_desde_etiquetas(recetas)
            receta_sel = render_autocomplete(
                opciones_recetas,
                "desayuno_receta",
                "Receta",
                "Buscar receta...",
                etiqueta_selectbox="Receta",
            )
            porciones = st.number_input(
                "Porciones",
                min_value=0.0,
                value=1.0,
                step=1.0,
                format="%.0f",
                key="desayuno_porciones",
            )
            if st.button("Añadir receta a la cesta", type="secondary", use_container_width=True, key="desayuno_btn_receta"):
                if receta_sel:
                    resultado = anadir_receta_a_cesta(receta_sel["id"], porciones)
                    if resultado.ok:
                        st.success(resultado.mensaje)
                        st.rerun()
                    else:
                        st.error(resultado.mensaje)
                else:
                    st.error("Seleccione una receta.")
        else:
            empty_state("No hay recetas definidas. Créelas en la sección Recetas.", icon="📖")

    with col_cesta:
        _render_cesta_desayuno(repo)

        if st.button("Registrar desayuno", type="primary", use_container_width=True, key="btn_registrar_desayuno"):
            resultado = registrar_desayuno(fecha, int(num_huespedes))
            if resultado.ok:
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
