"""Vista mínima del launcher Flet (sin economía ni datos operativos)."""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.presentation.flet.launcher_routing import (
    STREAMLIT_ADMIN_HINT,
    DestinoLauncher,
    listar_destinos,
)


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
                    ft.ProgressRing(width=28, height=28),
                    ft.Text("Abriendo destino…", size=14),
                ],
            )
        )
    if error:
        feedback.append(
            ft.Container(
                bgcolor=ft.Colors.RED_100,
                padding=12,
                border_radius=8,
                content=ft.Text(error, color=ft.Colors.RED_900, size=14),
            )
        )
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        padding=24,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=16,
            tight=True,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Text("BM — Launcher Flet", size=32, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Elija una vertical operativa. La selección no inicia sesión ni concede permisos.",
                    size=14,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
                *feedback,
                *cards,
                ft.Container(height=8),
                ft.Text(
                    STREAMLIT_ADMIN_HINT,
                    size=12,
                    color=ft.Colors.OUTLINE,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Comando Streamlit documentado: streamlit run app/main.py",
                    size=11,
                    color=ft.Colors.OUTLINE,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
        ),
    )


def _destino_boton(
    dest: DestinoLauncher,
    *,
    on_select: Callable[[str], None],
    disabled: bool,
) -> ft.Control:
    return ft.Container(
        width=420,
        bgcolor=ft.Colors.SURFACE,
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_300),
        border_radius=10,
        padding=16,
        content=ft.Column(
            spacing=8,
            tight=True,
            controls=[
                ft.Text(dest.etiqueta, size=18, weight=ft.FontWeight.BOLD),
                ft.Text(dest.descripcion, size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.FilledButton(
                    f"Abrir {dest.etiqueta}",
                    disabled=disabled,
                    on_click=lambda _e, did=dest.id: on_select(did),
                ),
            ],
        ),
    )
