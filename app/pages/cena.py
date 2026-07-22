"""Cena — registro de consumo de la noche."""

from app.core.services import cena_service
from app.ui.registro_servicio_page import render_pagina_registro_servicio


def render() -> None:
    render_pagina_registro_servicio(
        cena_service.servicio,
        titulo_pagina="Cena",
        subtitulo="Registro de consumo de cena",
        etiqueta="Cena",
        key_prefix="cena",
        categorias_receta=cena_service.CATEGORIAS_RECETA,
        mensaje_vacio_historial="Todavía no hay registros de cena esta semana.",
    )
