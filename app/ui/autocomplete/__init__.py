"""Componente Streamlit de autocompletado en tiempo real."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit.components.v1 as components

_COMPONENT_PATH = Path(__file__).parent
_autocomplete = components.declare_component("bm_autocomplete", path=str(_COMPONENT_PATH))


def autocomplete_input(
    options: list[dict],
    label: str = "",
    placeholder: str = "Escriba para buscar...",
    default_label: str = "",
    key: str | None = None,
    height: int = 100,
) -> dict | None:
    """
    Muestra un campo con dropdown de sugerencias en tiempo real.
    options: lista de {id, label, ...}
    Devuelve el dict de la opción seleccionada o None.
    """
    result = _autocomplete(
        options=json.dumps(options, ensure_ascii=False),
        label=label,
        placeholder=placeholder,
        defaultLabel=default_label,
        key=key,
        default=None,
    )
    if result is None:
        return None
    if isinstance(result, dict):
        return result
    return None
