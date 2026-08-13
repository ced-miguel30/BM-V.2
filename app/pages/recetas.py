"""Recetas — crear, editar y eliminar platos con ingredientes."""

import streamlit as st

from app.core.models import (
    CATEGORIA_RECETA_LABEL,
    CategoriaReceta,
    IngredienteReceta,
    SERVICIO_DISPONIBLE_LABEL,
    TipoServicio,
    UnidadProducto,
)
from app.core.services.data_service import get_repository
from app.core.services.receta_service import (
    crear_receta,
    desactivar_receta,
    editar_receta,
    eliminar_receta,
    etiqueta_categoria,
    etiqueta_porciones_estandar,
    listar_recetas,
    normalizar_porciones_estandar,
    obtener_receta,
    reactivar_receta,
    resumen_ingredientes,
    valorar_receta,
)
from app.core.services.stock_service import mapa_productos
from app.core.services.unidad_service import (
    cantidad_y_unidad_mostrar,
    convertir_a_unidad_producto,
    formato_number_input,
    normalizar_cantidad,
    paso_unidad,
    unidades_seleccionables,
)
from app.ui.components import empty_state, page_header, section_divider
from app.ui.search import render_autocomplete

_OPCIONES_CATEGORIA = list(CATEGORIA_RECETA_LABEL.values())
_CATEGORIA_POR_ETIQUETA = {etiqueta: cat for cat, etiqueta in CATEGORIA_RECETA_LABEL.items()}
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
            "En qué registros puede usarse esta receta. "
            "Vacío = No configurado (no significa «todos»). "
            "Distinto de la categoría de la receta (arriba)."
        ),
    )
    return [_VALOR_SERVICIO[e] for e in seleccion]


def _etiqueta_servicios(valores: list[str]) -> str:
    if not valores:
        return "No configurado"
    return ", ".join(_ETIQUETA_SERVICIO.get(v, v) for v in valores)


def _ingredientes_desde_sesion(session_key: str) -> list[dict]:
    if session_key not in st.session_state:
        st.session_state[session_key] = []
    return st.session_state[session_key]


def _cargar_ingredientes(session_key: str, ingredientes: list[IngredienteReceta]) -> None:
    repo = get_repository()
    filas = []
    for ing in ingredientes:
        producto = repo.get_producto(ing.producto_id)
        unidad_producto = producto.unidad if producto else UnidadProducto.UD
        cantidad_ui, unidad_ui = cantidad_y_unidad_mostrar(
            ing.cantidad, unidad_producto, ing.cantidad_presentacion, ing.unidad_presentacion,
        )
        filas.append({
            "producto_id": ing.producto_id,
            "cantidad": cantidad_ui,
            "unidad": unidad_ui,
        })
    st.session_state[session_key] = filas


def _limpiar_autocomplete(key: str) -> None:
    for suffix in ("_buscar", "_sel", "_sug_pick"):
        state_key = f"{key}{suffix}"
        if state_key in st.session_state:
            del st.session_state[state_key]


def _sembrar_autocomplete(opciones: list[dict], key: str, producto_id: str) -> None:
    if not producto_id:
        return
    opcion = next((o for o in opciones if o["id"] == producto_id), None)
    if not opcion:
        return
    st.session_state[f"{key}_buscar"] = opcion["label"]
    st.session_state[f"{key}_sel"] = opcion["label"]


def _ingredientes_a_modelo(session_key: str) -> list[IngredienteReceta]:
    repo = get_repository()
    resultado: list[IngredienteReceta] = []
    for fila in _ingredientes_desde_sesion(session_key):
        producto_id = fila.get("producto_id")
        if not producto_id:
            continue
        producto = repo.get_producto(producto_id)
        if not producto:
            continue
        unidad_ui = fila.get("unidad", producto.unidad.value)
        cantidad_ui = float(fila["cantidad"])
        cantidad_nativa = convertir_a_unidad_producto(cantidad_ui, unidad_ui, producto.unidad)
        resultado.append(IngredienteReceta(producto_id, cantidad_nativa, cantidad_ui, unidad_ui))
    return resultado


def _selector_categoria(key: str, valor_inicial: CategoriaReceta = CategoriaReceta.DESAYUNO) -> CategoriaReceta:
    etiqueta_inicial = etiqueta_categoria(valor_inicial)
    indice = (
        _OPCIONES_CATEGORIA.index(etiqueta_inicial)
        if etiqueta_inicial in _OPCIONES_CATEGORIA
        else 0
    )
    seleccion = st.selectbox(
        "Categoría de receta",
        _OPCIONES_CATEGORIA,
        index=indice,
        key=key,
        help=(
            "Clasificación de la receta (analítica / listados). "
            "Distinta de «Servicios disponibles»."
        ),
    )
    return _CATEGORIA_POR_ETIQUETA[seleccion]


def _render_editor_ingredientes(
    session_key: str,
    key_prefix: str,
    *,
    ids_existentes: set[str] | None = None,
) -> None:
    repo = get_repository()
    # Nuevas selecciones: solo activos. Conservar inactivos ya en la receta.
    productos_map = mapa_productos(repo.data, solo_activos=True)
    ids_existentes = ids_existentes or set()
    for p in repo.data.productos:
        if p.id in ids_existentes and p.id not in productos_map.values():
            productos_map[p.nombre] = p.id
    opciones = []
    for nombre, pid in sorted(productos_map.items()):
        prod = repo.get_producto(pid)
        label = nombre
        if prod is not None and not getattr(prod, "activo", True):
            label = f"{nombre} (inactivo)"
        opciones.append(
            {
                "id": pid,
                "label": label,
                "unidad": prod.unidad if prod else UnidadProducto.UD,
            }
        )
    filas = _ingredientes_desde_sesion(session_key)

    if not filas:
        st.caption("Sin ingredientes. Pulse «Añadir ingrediente».")
    for idx, fila in enumerate(filas):
        autocomplete_key = f"{key_prefix}_ing_{idx}"
        _sembrar_autocomplete(opciones, autocomplete_key, fila.get("producto_id", ""))

        col_prod, col_cant, col_unidad, col_btn = st.columns([3, 1, 1, 1])
        with col_prod:
            producto_sel = render_autocomplete(
                opciones,
                autocomplete_key,
                f"Ingrediente {idx + 1}",
                "Buscar producto...",
                etiqueta_selectbox="Producto",
                requiere_busqueda=not bool(fila.get("producto_id")),
            )
            if producto_sel:
                if fila.get("producto_id") != producto_sel["id"]:
                    fila["producto_id"] = producto_sel["id"]
                    fila["unidad"] = producto_sel["unidad"].value
                else:
                    fila["producto_id"] = producto_sel["id"]
        with col_cant:
            unidad_fila = fila.get("unidad", UnidadProducto.UD.value)
            valor_cant = float(fila.get("cantidad", paso_unidad(unidad_fila)))
            fila["cantidad"] = normalizar_cantidad(
                st.number_input(
                    "Cantidad",
                    min_value=0.0,
                    value=valor_cant if valor_cant > 0 else float(paso_unidad(unidad_fila)),
                    step=paso_unidad(unidad_fila),
                    format=formato_number_input(unidad_fila),
                    key=f"{key_prefix}_cant_{idx}",
                ),
                unidad_fila,
            )
        with col_unidad:
            producto = repo.get_producto(fila.get("producto_id", ""))
            if producto:
                opciones_unidad = unidades_seleccionables(producto.unidad)
                unidad_actual = fila.get("unidad", producto.unidad.value)
                if unidad_actual not in opciones_unidad:
                    unidad_actual = producto.unidad.value
                fila["unidad"] = st.selectbox(
                    "Unidad",
                    opciones_unidad,
                    index=opciones_unidad.index(unidad_actual),
                    key=f"{key_prefix}_unidad_{idx}",
                    label_visibility="collapsed",
                )
            else:
                st.caption("—")
        with col_btn:
            st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
            prod_btn = repo.get_producto(fila.get("producto_id", ""))
            nom_btn = prod_btn.nombre if prod_btn else "ingrediente"
            if st.button(
                "✕",
                key=f"{key_prefix}_quitar_{idx}",
                help=f"Quitar «{nom_btn}»",
            ):
                filas.pop(idx)
                st.session_state[session_key] = filas
                st.success(f"Se quitó «{nom_btn}» de la receta (sin guardar aún).")
                st.rerun()

    if st.button("Añadir ingrediente", key=f"{key_prefix}_anadir"):
        nuevo_idx = len(filas)
        filas.append({"producto_id": "", "cantidad": 1.0, "unidad": UnidadProducto.UD.value})
        st.session_state[session_key] = filas
        _limpiar_autocomplete(f"{key_prefix}_ing_{nuevo_idx}")
        st.rerun()


def _render_coste_panel(receta_id: str) -> None:
    val = valorar_receta(receta_id)
    if not val.ok:
        st.warning(val.mensaje)
        return
    estado = (
        "Coste completo"
        if val.coste_completo
        else f"Coste incompleto: faltan precios o lotes para {val.ingredientes_sin_coste} ingrediente(s)"
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Coste teórico total", f"{val.coste_total:.2f} €")
    c2.metric(
        "Coste por ración",
        f"{val.coste_por_racion:.4f} €" if val.coste_por_racion is not None else "—",
    )
    c3.metric("Rendimiento", f"{val.porciones_estandar:g}" if val.porciones_estandar else "—")
    st.caption(f"{estado} · valoración FIFO de lotes activos · €")
    if val.lineas:
        st.dataframe(
            [
                {
                    "Ingrediente": ln.nombre
                    + (" (inactivo)" if ln.producto_inactivo else ""),
                    "Cantidad": f"{ln.cantidad_nativa:g} {ln.unidad_nativa}",
                    "Coste unitario": (
                        f"{ln.coste_unitario_aplicable:.4f} €/{ln.unidad_nativa}"
                        if ln.coste_unitario_aplicable is not None
                        else "—"
                    ),
                    "Coste": f"{ln.coste_estimado:.2f} €",
                    "Estado": "Incompleto" if ln.coste_incompleto else "OK",
                }
                for ln in val.lineas
            ],
            use_container_width=True,
            hide_index=True,
        )


def _render_listado() -> None:
    recetas = listar_recetas(solo_activas=False)
    st.markdown("#### Recetas registradas")
    st.caption(
        "Maestro único de preparaciones del buffet. "
        "Las activas aparecen directamente en el registro operativo "
        "(no hace falta un menú buffet duplicado)."
    )

    if recetas:
        filas = []
        for receta in recetas:
            val = valorar_receta(receta.id) if receta.porciones_estandar else None
            filas.append({
                "Receta": receta.nombre,
                "Estado": "Activa" if getattr(receta, "activo", True) else "Inactiva",
                "Categoría receta": etiqueta_categoria(receta.categoria),
                "Servicios disponibles": _etiqueta_servicios(receta.servicios_disponibles),
                "Porciones estándar": etiqueta_porciones_estandar(receta.porciones_estandar),
                "Coste total €": (
                    f"{val.coste_total:.2f}" if val and val.ok else "—"
                ),
                "Coste/ración €": (
                    f"{val.coste_por_racion:.4f}"
                    if val and val.ok and val.coste_por_racion is not None
                    else "—"
                ),
                "Valoración": (
                    "Completo"
                    if val and val.ok and val.coste_completo
                    else ("Incompleto" if val and val.ok else "—")
                ),
                "Ingredientes": len(receta.ingredientes),
                "Detalle": resumen_ingredientes(receta),
            })
        st.dataframe(filas, use_container_width=True, hide_index=True)
    else:
        empty_state("No hay recetas creadas todavía.", icon="📖")


def _render_crear() -> None:
    st.markdown("#### Crear receta")
    session_key = "receta_nuevo_ingredientes"

    nombre = st.text_input("Nombre de la receta", placeholder="Ej: Sándwich mixto", key="receta_nuevo_nombre")
    categoria = _selector_categoria("receta_nuevo_categoria")
    servicios = _selector_servicios_disponibles("receta_nuevo_servicios")
    porciones_std = st.number_input(
        "Porciones estándar (rendimiento)",
        min_value=0.0,
        value=1.0,
        step=1.0,
        format="%.0f",
        key="receta_nuevo_porciones_std",
        help="Rendimiento obligatorio (> 0). Base del coste por ración.",
    )
    st.markdown("##### Ingredientes")
    _render_editor_ingredientes(session_key, "receta_nuevo")

    if st.button("Crear receta", type="primary", key="receta_btn_crear"):
        ingredientes = _ingredientes_a_modelo(session_key)
        resultado = crear_receta(
            nombre,
            ingredientes,
            categoria,
            servicios_disponibles=servicios,
            porciones_estandar=normalizar_porciones_estandar(porciones_std),
        )
        if resultado.ok:
            st.session_state[session_key] = []
            st.success(resultado.mensaje)
            st.rerun()
        else:
            st.error(resultado.mensaje)


def _render_editar_eliminar() -> None:
    recetas = listar_recetas(solo_activas=False)
    st.markdown("#### Editar / activar / desactivar")
    if not recetas:
        empty_state("Cree una receta para poder editarla.", icon="✏️")
        return

    opciones = {
        f"{r.nombre} ({'activa' if getattr(r, 'activo', True) else 'inactiva'})": r.id
        for r in recetas
    }
    sel_nombre = st.selectbox("Seleccionar receta", list(opciones.keys()), key="receta_sel_editar")
    receta_id = opciones[sel_nombre]
    receta = obtener_receta(receta_id)
    if not receta:
        return

    session_key = f"receta_edit_ingredientes_{receta_id}"
    if st.session_state.get("receta_edit_prev_id") != receta_id:
        _cargar_ingredientes(session_key, receta.ingredientes)
        st.session_state["receta_edit_prev_id"] = receta_id
        st.rerun()

    st.markdown("##### Coste teórico")
    _render_coste_panel(receta_id)

    nuevo_nombre = st.text_input("Nombre", value=receta.nombre, key=f"receta_edit_nombre_{receta_id}")
    categoria = _selector_categoria(f"receta_edit_categoria_{receta_id}", receta.categoria)
    servicios = _selector_servicios_disponibles(
        f"receta_edit_servicios_{receta_id}",
        receta.servicios_disponibles,
    )
    valor_std = float(receta.porciones_estandar) if receta.porciones_estandar else 1.0
    porciones_std = st.number_input(
        "Porciones estándar (rendimiento)",
        min_value=0.0,
        value=valor_std if valor_std > 0 else 1.0,
        step=1.0,
        format="%.0f",
        key=f"receta_edit_porciones_std_{receta_id}",
        help="Obligatorio > 0 para guardar y para el coste por ración.",
    )
    st.markdown("##### Ingredientes")
    ids_exist = {i.producto_id for i in receta.ingredientes}
    _render_editor_ingredientes(
        session_key, f"receta_edit_{receta_id}", ids_existentes=ids_exist
    )

    if st.button("Guardar cambios", type="primary", use_container_width=True, key="receta_btn_guardar"):
        ingredientes = _ingredientes_a_modelo(session_key)
        resultado = editar_receta(
            receta_id,
            nuevo_nombre,
            ingredientes,
            categoria,
            servicios_disponibles=servicios,
            porciones_estandar=normalizar_porciones_estandar(porciones_std),
        )
        if resultado.ok:
            st.success(resultado.mensaje)
            st.rerun()
        else:
            st.error(resultado.mensaje)

    c1, c2 = st.columns(2)
    with c1:
        if getattr(receta, "activo", True):
            if st.button("Desactivar receta", use_container_width=True, key="receta_btn_off"):
                resultado = desactivar_receta(receta_id)
                st.success(resultado.mensaje) if resultado.ok else st.error(resultado.mensaje)
                if resultado.ok:
                    st.rerun()
        else:
            if st.button("Reactivar receta", use_container_width=True, key="receta_btn_on"):
                resultado = reactivar_receta(receta_id)
                st.success(resultado.mensaje) if resultado.ok else st.error(resultado.mensaje)
                if resultado.ok:
                    st.rerun()
    with c2:
        if st.button(
            "Eliminar receta",
            use_container_width=True,
            key="receta_btn_eliminar",
        ):
            resultado = eliminar_receta(receta_id)
            if resultado.ok:
                st.session_state.pop("receta_edit_prev_id", None)
                st.success(resultado.mensaje)
                st.rerun()
            else:
                st.error(resultado.mensaje)


def render() -> None:
    page_header("Recetas", "Defina platos con ingredientes del catálogo de productos")

    _render_listado()
    section_divider()
    _render_crear()
    section_divider()
    _render_editar_eliminar()
