"""Componentes de búsqueda con sugerencias."""

from __future__ import annotations

from typing import Any

import streamlit as st

from app.core.services.text_search import coincide_busqueda, filtrar_por_prefijo


def _filtrar_por_label(opciones: list[dict[str, Any]], termino: str) -> list[dict[str, Any]]:
    termino = termino.strip()
    if not termino:
        return opciones[:15]
    prefijo = filtrar_por_prefijo(opciones, termino, campo="label")
    if prefijo:
        return prefijo[:15]
    return [o for o in opciones if coincide_busqueda(o["label"], termino)][:15]


def render_autocomplete(
    opciones: list[dict[str, Any]],
    key: str,
    label: str,
    placeholder: str = "Escriba para buscar...",
    mostrar_seleccion: bool = True,
    permitir_limpiar: bool = True,
    etiqueta_selectbox: str = "Selección",
) -> dict[str, Any] | None:
    """
    Buscador con sugerencias por prefijo y selectbox filtrado.
    opciones: [{id, label, ...campos extra}]
    """
    if not opciones:
        return None

    buscar_key = f"{key}_buscar"
    sel_key = f"{key}_sel"
    sug_key = f"{key}_sug_pick"

    if sug_key in st.session_state:
        picked = st.session_state.pop(sug_key)
        st.session_state[buscar_key] = picked["label"]
        if picked["label"] in {o["label"] for o in opciones}:
            st.session_state[sel_key] = picked["label"]

    termino = st.text_input(label, placeholder=placeholder, key=buscar_key)

    if termino.strip():
        sugerencias = _filtrar_por_label(opciones, termino)[:8]
        if sugerencias:
            st.caption("Sugerencias:")
            cols = st.columns(min(len(sugerencias), 4))
            for i, opcion in enumerate(sugerencias):
                with cols[i % len(cols)]:
                    if st.button(
                        opcion["label"],
                        key=f"{key}_sug_{opcion['id']}",
                        use_container_width=True,
                    ):
                        st.session_state[sug_key] = opcion
                        st.rerun()

    disponibles = [
        o for o in opciones
        if coincide_busqueda(o["label"], termino)
    ]

    if not disponibles:
        return None

    etiquetas = [o["label"] for o in disponibles]
    mapa = {o["label"]: o for o in disponibles}

    if sel_key in st.session_state and st.session_state[sel_key] not in mapa:
        del st.session_state[sel_key]

    seleccion = st.selectbox(etiqueta_selectbox, etiquetas, key=sel_key)
    resultado = mapa[seleccion]

    if permitir_limpiar and mostrar_seleccion and resultado:
        col_t, col_x = st.columns([6, 1])
        with col_t:
            st.caption(f"Seleccionado: **{resultado['label']}**")
        with col_x:
            if st.button("✕", key=f"{key}_limpiar", help="Limpiar"):
                for k in (buscar_key, sel_key):
                    if k in st.session_state:
                        del st.session_state[k]
                st.rerun()

    return resultado


def render_buscador_producto(
    productos: list[dict[str, Any]],
    key_prefix: str,
    label: str = "Buscar producto",
    placeholder: str = "Escriba el nombre del producto...",
) -> dict[str, Any] | None:
    """Buscador con sugerencias por prefijo y selectbox filtrado para productos."""
    if not productos:
        return None

    buscar_key = f"{key_prefix}_buscar"
    sel_key = f"{key_prefix}_sel_producto"
    sug_key = f"{key_prefix}_sug_pick"

    if sug_key in st.session_state:
        picked = st.session_state.pop(sug_key)
        st.session_state[buscar_key] = picked["nombre"]
        if picked["etiqueta"] in {p["etiqueta"] for p in productos}:
            st.session_state[sel_key] = picked["etiqueta"]

    termino = st.text_input(label, placeholder=placeholder, key=buscar_key)

    if termino.strip():
        sugerencias = filtrar_por_prefijo(productos, termino)[:8]
        if sugerencias:
            st.caption("Sugerencias:")
            cols = st.columns(min(len(sugerencias), 4))
            for i, producto in enumerate(sugerencias):
                with cols[i % len(cols)]:
                    if st.button(
                        producto["nombre"],
                        key=f"{key_prefix}_sug_{producto['id']}",
                        use_container_width=True,
                    ):
                        st.session_state[sug_key] = producto
                        st.rerun()

    disponibles = [
        p for p in productos
        if coincide_busqueda(p["nombre"], termino)
    ]

    if not disponibles:
        return None

    etiquetas = [p["etiqueta"] for p in disponibles]
    mapa = {p["etiqueta"]: p for p in disponibles}

    if sel_key in st.session_state and st.session_state[sel_key] not in mapa:
        del st.session_state[sel_key]

    seleccion = st.selectbox("Producto", etiquetas, key=sel_key)
    return mapa[seleccion]


def opciones_desde_etiquetas(
    items: list[dict[str, Any]],
    id_key: str = "id",
    label_key: str = "etiqueta",
) -> list[dict[str, Any]]:
    return [
        {"id": item[id_key], "label": item[label_key], **item}
        for item in items
    ]
