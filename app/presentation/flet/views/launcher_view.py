"""Vista mínima del launcher Flet (sin economía ni datos operativos)."""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.presentation.flet import theme as ui_theme
from app.presentation.flet import ui_components as ui
from app.presentation.flet.launcher_routing import (
    STREAMLIT_ADMIN_HINT,
    DestinoLauncher,
    listar_destinos,
)

_DESTINO_ICONS: dict[str, object] = {
    "restaurante": ft.Icons.RESTAURANT_MENU,
    "inventario": ft.Icons.INVENTORY_2_OUTLINED,
    "administracion": ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED,
}


def build_launcher_view(
    *,
    on_select: Callable[[str], None],
    cargando: bool = False,
    error: str = "",
) -> ft.Control:
    destinos = listar_destinos()
    cards: list[ft.Control] = [
        _destino_boton(d, on_select=on_select, disabled=cargando) for d in destinos
    ]
    feedback: list[ft.Control] = []
    if cargando:
        feedback.append(
            ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.ProgressRing(width=28, height=28, color=ui_theme.NAVY),
                    ft.Text(
                        "Abriendo destino…",
                        size=14,
                        color=ui_theme.DARK_TEXT,
                    ),
                ],
            )
        )
    if error:
        feedback.append(ui.alert_banner(error, severity="error"))

    return ui.branded_page(
        ui.auth_card(
            *feedback,
            *cards,
            ft.Text(
                f"{ui_theme.APP_NAME} · {ui_theme.APP_SUBTITLE}",
                size=11,
                color=ui_theme.MID_GRAY,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Text(
                STREAMLIT_ADMIN_HINT,
                size=11,
                color=ui_theme.MID_GRAY,
                text_align=ft.TextAlign.CENTER,
            ),
            titulo="Consola operativa",
            subtitulo=(
                "Elija la vertical. La selección no inicia sesión "
                "ni concede permisos."
            ),
            width=480,
        )
    )


def _destino_boton(
    dest: DestinoLauncher,
    *,
    on_select: Callable[[str], None],
    disabled: bool,
) -> ft.Control:
    icon = _DESTINO_ICONS.get(dest.id, ft.Icons.ARROW_FORWARD)
    return ft.Container(
        width=400,
        bgcolor=ui_theme.SURFACE,
        border=ft.Border.all(1, ui_theme.BORDER),
        border_radius=ui_theme.RADIUS_MD,
        padding=ui_theme.SPACE_MD,
        content=ft.Row(
            spacing=ui_theme.SPACE_MD,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=44,
                    height=44,
                    bgcolor=ui_theme.NAVY,
                    border_radius=ui_theme.RADIUS_SM,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(icon, color=ui_theme.WHITE, size=22),
                ),
                ft.Column(
                    spacing=2,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Text(
                            dest.etiqueta,
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color=ui_theme.DARK_TEXT,
                        ),
                        ft.Text(
                            dest.descripcion,
                            size=12,
                            color=ui_theme.MID_GRAY,
                        ),
                    ],
                ),
                ui.primary_button(
                    "Abrir",
                    lambda did=dest.id: on_select(did),
                    disabled=disabled,
                ),
            ],
        ),
    )
