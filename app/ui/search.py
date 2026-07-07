"""Componentes de búsqueda con autocompletado en tiempo real."""

from __future__ import annotations

from typing import Any

import streamlit as st

from app.ui.autocomplete import autocomplete_input


def _opciones_a_dict(opciones: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(o["id"]): o for o in opciones}


def render_autocomplete(
    opciones: list[dict[str, Any]],
    key: str,
    label: str,
    placeholder: str = "Escriba para buscar...",
    mostrar_seleccion: bool = True,
    permitir_limpiar: bool = True,
) -> dict[str, Any] | None:
    """
    Autocompletado tipo Google sobre datos registrados.
    opciones: [{id, label, ...campos extra}]
    """
    if not opciones:
        return None

    state_sel_key = f"{key}_seleccion"
    default_label = ""
    if state_sel_key in st.session_state:
        default_label = st.session_state[state_sel_key].get("label", "")

    payload = [{"id": o["id"], "label": o["label"]} for o in opciones]
    seleccion = autocomplete_input(
        options=payload,
        label=label,
        placeholder=placeholder,
        default_label=default_label,
        key=f"{key}_ac",
        height=100,
    )

    if seleccion:
        mapa = _opciones_a_dict(opciones)
        completo = mapa.get(str(seleccion.get("id")))
        if completo:
            st.session_state[state_sel_key] = completo

    if state_sel_key in st.session_state:
        previo = st.session_state[state_sel_key]
        if mostrar_seleccion:
            col_t, col_x = st.columns([6, 1])
            with col_t:
                st.caption(f"Seleccionado: **{previo['label']}**")
            with col_x:
                if permitir_limpiar and st.button("✕", key=f"{key}_limpiar", help="Limpiar"):
                    del st.session_state[state_sel_key]
                    st.rerun()
        return previo

    return None


def render_buscador_producto(
    productos: list[dict[str, Any]],
    key_prefix: str,
    label: str = "Buscar producto",
    placeholder: str = "Escriba el nombre del producto...",
) -> dict[str, Any] | None:
    """Autocompletado para productos con stock."""
    opciones = [
        {
            "id": p["id"],
            "label": p["nombre"],
            "nombre": p["nombre"],
            "unidad": p["unidad"],
            "stock": p["stock"],
            "etiqueta": p["etiqueta"],
        }
        for p in productos
    ]
    return render_autocomplete(opciones, key_prefix, label, placeholder)


def opciones_desde_etiquetas(
    items: list[dict[str, Any]],
    id_key: str = "id",
    label_key: str = "etiqueta",
) -> list[dict[str, Any]]:
    return [
        {"id": item[id_key], "label": item[label_key], **item}
        for item in items
    ]
