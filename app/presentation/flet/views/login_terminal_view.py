"""Vista de entrada al Terminal Restaurante."""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.presentation.flet.views.menu_nav import build_volver_al_menu_button


def build_login_view(
    *,
    on_enter: Callable[[], None],
    on_volver_menu: Callable[[], None] | None = None,
) -> ft.Control:
    controls: list[ft.Control] = [
        ft.Text(
            "Terminal Restaurante",
            size=36,
            weight=ft.FontWeight.BOLD,
        ),
        ft.Text(
            "Registro operativo de Desayuno, Comida, Cena y Bebidas.",
            size=16,
            color=ft.Colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.CENTER,
        ),
        ft.Container(height=12),
        ft.FilledButton(
            "Entrar al terminal",
            icon=ft.Icons.LOGIN,
            style=ft.ButtonStyle(padding=20),
            on_click=lambda _e: on_enter(),
        ),
    ]
    volver = build_volver_al_menu_button(on_volver_menu)
    if volver is not None:
        controls.append(volver)
    controls.append(
        ft.Text(
            "Sin menús administrativos ni información económica.",
            size=12,
            color=ft.Colors.OUTLINE,
        )
    )
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        padding=24,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20,
            tight=True,
            controls=controls,
        ),
    )
