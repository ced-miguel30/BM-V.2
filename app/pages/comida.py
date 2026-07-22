"""Comida — registro de consumo del mediodía."""

from app.core.services import comida_service
from app.ui.registro_servicio_page import render_pagina_registro_servicio


def render() -> None:
    render_pagina_registro_servicio(
        comida_service.servicio,
        titulo_pagina="Comida",
        subtitulo="Registro de consumo de comida",
        etiqueta="Comida",
        key_prefix="comida",
        categorias_receta=comida_service.CATEGORIAS_RECETA,
        mensaje_vacio_historial="Todavía no hay registros de comida esta semana.",
    )
