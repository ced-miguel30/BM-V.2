"""Registros — punto unificado de desayuno, comida, cena, bebidas y merma."""

from app.pages import bebidas, cena, comida, desayuno
from app.ui.components import page_header, render_sub_tabs

_SUBTABS = {
    "Desayuno": lambda: desayuno.render_registro_desayuno(),
    "Comida": lambda: comida.render(mostrar_cabecera=False),
    "Cena": lambda: cena.render(mostrar_cabecera=False),
    "Bebidas": lambda: bebidas.render(mostrar_cabecera=False),
    "Merma": lambda: desayuno.render_registro_merma(),
}


def render() -> None:
    page_header(
        "Registros",
        "Registro diario de desayuno, comida, cena, bebidas y merma",
    )
    selected = render_sub_tabs(list(_SUBTABS.keys()), key="registros_subtab")
    _SUBTABS[selected]()
