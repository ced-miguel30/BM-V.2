"""Vista de entrada al Terminal Restaurante."""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.presentation.flet import theme as ui_theme
from app.presentation.flet import ui_components as ui
from app.presentation.flet.views.menu_nav import build_volver_al_menu_button


def build_login_view(
    *,
    on_enter: Callable[[], None],
    on_volver_menu: Callable[[], None] | None = None,
) -> ft.Control:
    extras: list[ft.Control] = [
        ui.primary_button(
            "Entrar al terminal",
            on_enter,
            icon=ft.Icons.LOGIN,
        ),
    ]
    volver = build_volver_al_menu_button(on_volver_menu)
    if volver is not None:
        extras.append(volver)
    extras.append(
        ft.Text(
            "Registro de Desayuno, Comida, Cena y Bebidas · sin economía en pantalla",
            size=11,
            color=ui_theme.MID_GRAY,
            text_align=ft.TextAlign.CENTER,
        )
    )
    return ui.branded_page(
        ui.auth_card(
            *extras,
            titulo="Terminal Restaurante",
            subtitulo="Servicio de sala · registro operativo",
        )
    )
