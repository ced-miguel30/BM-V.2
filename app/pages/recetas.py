"""Recetas — crear, editar y eliminar platos con ingredientes."""

import streamlit as st

from app.core.models import IngredienteReceta
from app.core.services.data_service import get_repository
from app.core.services.receta_service import (
    crear_receta,
    editar_receta,
    eliminar_receta,
    listar_recetas,
    obtener_receta,
    resumen_ingredientes,
)
from app.core.services.stock_service import mapa_productos
from app.ui.components import empty_state, page_header, section_divider
from app.ui.search import render_autocomplete


def _ingredientes_desde_sesion(session_key: str) -> list[dict]:
    if session_key not in st.session_state:
        st.session_state[session_key] = []
    return st.session_state[session_key]


def _cargar_ingredientes(session_key: str, ingredientes: list[IngredienteReceta]) -> None:
    st.session_state[session_key] = [
        {"producto_id": i.producto_id, "cantidad": i.cantidad}
        for i in ingredientes
    ]


def _ingredientes_a_modelo(session_key: str) -> list[IngredienteReceta]:
    resultado: list[IngredienteReceta] = []
    for fila in _ingredientes_desde_sesion(session_key):
        if fila.get("producto_id"):
            resultado.append(IngredienteReceta(fila["producto_id"], float(fila["cantidad"])))
    return resultado


def _render_editor_ingredientes(session_key: str, key_prefix: str) -> None:
    repo = get_repository()
    productos_map = mapa_productos(repo.data)
    opciones = [{"id": pid, "label": nombre} for nombre, pid in sorted(productos_map.items())]
    filas = _ingredientes_desde_sesion(session_key)

    if not filas:
        st.caption("Sin ingredientes. Pulse «Añadir ingrediente».")
    for idx, fila in enumerate(filas):
        col_prod, col_cant, col_btn = st.columns([3, 1, 1])
        with col_prod:
            producto_sel = render_autocomplete(
                opciones,
                f"{key_prefix}_ing_{idx}",
                f"Ingrediente {idx + 1}",
                "Buscar producto...",
                etiqueta_selectbox="Producto",
            )
            if producto_sel:
                fila["producto_id"] = producto_sel["id"]
        with col_cant:
            fila["cantidad"] = st.number_input(
                "Cantidad",
                min_value=0.0,
                value=float(fila.get("cantidad", 1.0)),
                step=0.01,
                format="%.2f",
                key=f"{key_prefix}_cant_{idx}",
            )
        with col_btn:
            st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
            if st.button("✕", key=f"{key_prefix}_quitar_{idx}", help="Quitar ingrediente"):
                filas.pop(idx)
                st.session_state[session_key] = filas
                st.rerun()

    if st.button("Añadir ingrediente", key=f"{key_prefix}_anadir"):
        filas.append({"producto_id": "", "cantidad": 1.0})
        st.session_state[session_key] = filas
        st.rerun()


def _render_listado() -> None:
    recetas = listar_recetas()
    st.markdown("#### Recetas registradas")
    st.caption("Platos definidos con productos del catálogo de stock.")

    if recetas:
        repo = get_repository()
        filas = []
        for receta in recetas:
            filas.append({
                "Receta": receta.nombre,
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
    st.markdown("##### Ingredientes")
    _render_editor_ingredientes(session_key, "receta_nuevo")

    if st.button("Crear receta", type="primary", key="receta_btn_crear"):
        ingredientes = _ingredientes_a_modelo(session_key)
        resultado = crear_receta(nombre, ingredientes)
        if resultado.ok:
            st.session_state[session_key] = []
            st.success(resultado.mensaje)
            st.rerun()
        else:
            st.error(resultado.mensaje)


def _render_editar_eliminar() -> None:
    recetas = listar_recetas()
    st.markdown("#### Editar / eliminar")
    if not recetas:
        empty_state("Cree una receta para poder editarla.", icon="✏️")
        return

    opciones = {r.nombre: r.id for r in recetas}
    sel_nombre = st.selectbox("Seleccionar receta", list(opciones.keys()), key="receta_sel_editar")
    receta_id = opciones[sel_nombre]
    receta = obtener_receta(receta_id)
    if not receta:
        return

    session_key = f"receta_edit_ingredientes_{receta_id}"
    if st.session_state.get("receta_edit_loaded") != receta_id:
        _cargar_ingredientes(session_key, receta.ingredientes)
        st.session_state["receta_edit_loaded"] = receta_id

    nuevo_nombre = st.text_input("Nombre", value=receta.nombre, key="receta_edit_nombre")
    st.markdown("##### Ingredientes")
    _render_editor_ingredientes(session_key, f"receta_edit_{receta_id}")

    if st.button("Guardar cambios", type="primary", use_container_width=True, key="receta_btn_guardar"):
        ingredientes = _ingredientes_a_modelo(session_key)
        resultado = editar_receta(receta_id, nuevo_nombre, ingredientes)
        if resultado.ok:
            st.success(resultado.mensaje)
            st.rerun()
        else:
            st.error(resultado.mensaje)

    if st.button("Eliminar receta", use_container_width=True, key="receta_btn_eliminar"):
        resultado = eliminar_receta(receta_id)
        if resultado.ok:
            st.session_state.pop("receta_edit_loaded", None)
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
