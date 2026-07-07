"""Componentes de búsqueda con sugerencias."""

from __future__ import annotations

from typing import Any

import streamlit as st

from app.core.services.text_search import coincide_busqueda, filtrar_por_prefijo


def render_buscador_producto(
    productos: list[dict[str, Any]],
    key_prefix: str,
    label: str = "Buscar producto",
    placeholder: str = "Escriba el nombre del producto...",
) -> dict[str, Any] | None:
    """
    Buscador con sugerencias por prefijo y selectbox filtrado.
    Devuelve el producto seleccionado o None si no hay coincidencias.
    """
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
