"""Bebidas — registro independiente de consumo de bebidas."""

from app.core.services import bebida_service
from app.ui.registro_servicio_page import render_pagina_registro_servicio


def render() -> None:
    render_pagina_registro_servicio(
        bebida_service.servicio,
        titulo_pagina="Bebidas",
        subtitulo="Registro independiente de consumo de bebidas",
        etiqueta="Bebidas",
        key_prefix="bebidas",
        categorias_receta=bebida_service.CATEGORIAS_RECETA,
        mensaje_vacio_historial="Todavía no hay registros de bebidas esta semana.",
    )
