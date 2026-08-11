"""Controles de navegación compartidos (sin acoplar al módulo launcher)."""

from __future__ import annotations

from typing import Callable

import flet as ft

LABEL_VOLVER_AL_MENU = "Volver al menú"


def build_volver_al_menu_button(
    on_volver: Callable[[], None] | None,
    *,
    light: bool = False,
) -> ft.Control | None:
    """Botón opcional; ``None`` si la vertical no tiene launcher padre."""
    if on_volver is None:
        return None
    style = ft.ButtonStyle(color=ft.Colors.WHITE) if light else None
    return ft.TextButton(
        LABEL_VOLVER_AL_MENU,
        icon=ft.Icons.HOME,
        style=style,
        on_click=lambda _e: on_volver(),
    )


def header_action_row(
    *,
    on_logout: Callable[[], None],
    on_volver_menu: Callable[[], None] | None = None,
    light: bool = True,
) -> ft.Control:
    """Fila de acciones de cabecera (volver opcional + cerrar sesión)."""
    controls: list[ft.Control] = []
    volver = build_volver_al_menu_button(on_volver_menu, light=light)
    if volver is not None:
        controls.append(volver)
    controls.append(
        ft.TextButton(
            "Cerrar sesión",
            icon=ft.Icons.LOGOUT,
            style=ft.ButtonStyle(color=ft.Colors.WHITE) if light else None,
            on_click=lambda _e: on_logout(),
        )
    )
    return ft.Row(spacing=4, tight=True, controls=controls)
