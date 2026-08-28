"""Componentes UI reutilizables Flet (solo presentación)."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.presentation.flet import theme as t


def page_header(
    titulo: str,
    subtitulo: str = "",
    *,
    actions: list[ft.Control] | None = None,
) -> ft.Control:
    row_actions = actions or []
    left = [
        t.text_page_title(titulo),
    ]
    if subtitulo:
        left.append(t.text_help(subtitulo))
    return ft.Container(
        padding=ft.Padding.only(bottom=t.SPACE_SM),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Column(spacing=2, tight=True, controls=left, expand=True),
                ft.Row(spacing=t.SPACE_SM, tight=True, controls=row_actions),
            ],
        ),
    )


def section_header(titulo: str, ayuda: str = "") -> ft.Control:
    controls: list[ft.Control] = [t.text_section(titulo)]
    if ayuda:
        controls.append(t.text_help(ayuda))
    return ft.Column(spacing=2, tight=True, controls=controls)


def metric_card(
    etiqueta: str,
    valor: str,
    detalle: str = "",
    *,
    accent: str | None = None,
    on_click: Callable[[], None] | None = None,
    width: float = 190,
) -> ft.Control:
    color = accent or t.NAVY
    body = ft.Column(
        spacing=t.SPACE_XS,
        tight=True,
        controls=[
            t.text_label(etiqueta),
            ft.Text(
                valor,
                size=t.TYPE_KPI,
                weight=ft.FontWeight.BOLD,
                color=color,
            ),
            ft.Text(detalle or " ", size=t.TYPE_HELP, color=t.MID_GRAY, max_lines=2),
        ],
    )
    return ft.Container(
        width=width,
        padding=t.SPACE_MD,
        bgcolor=t.SURFACE_CARD,
        border_radius=t.RADIUS_MD,
        border=ft.Border.all(1, t.BORDER),
        ink=on_click is not None,
        on_click=(lambda _e: on_click()) if on_click else None,
        content=body,
        shadow=ft.BoxShadow(
            blur_radius=8,
            color="#0B1F3A14",
            offset=ft.Offset(0, 2),
        ),
    )


def alert_banner(
    mensaje: str,
    *,
    severity: str = "info",
    icon: str | None = None,
) -> ft.Control:
    cfg = {
        "info": (t.INFO_BG, t.INFO, ft.Icons.INFO_OUTLINE),
        "success": (t.SUCCESS_BG, t.SUCCESS, ft.Icons.CHECK_CIRCLE_OUTLINE),
        "warning": (t.WARNING_BG, t.WARNING, ft.Icons.WARNING_AMBER_OUTLINED),
        "error": (t.DANGER_BG, t.DANGER, ft.Icons.ERROR_OUTLINE),
    }
    bg, fg, default_icon = cfg.get(severity, cfg["info"])
    return ft.Container(
        bgcolor=bg,
        padding=t.SPACE_MD,
        border_radius=t.RADIUS_MD,
        border=ft.Border.all(1, fg),
        content=ft.Row(
            spacing=t.SPACE_SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(icon or default_icon, color=fg, size=t.ICON_MD),
                ft.Text(
                    mensaje,
                    color=fg,
                    size=t.TYPE_BODY,
                    weight=ft.FontWeight.W_600,
                    expand=True,
                ),
            ],
        ),
    )


def empty_state(titulo: str, detalle: str = "") -> ft.Control:
    return ft.Container(
        padding=t.SPACE_XL,
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=t.SPACE_SM,
            tight=True,
            controls=[
                ft.Icon(ft.Icons.INBOX_OUTLINED, size=36, color=t.MID_GRAY),
                ft.Text(titulo, size=t.TYPE_SECTION, color=t.DARK_TEXT),
                ft.Text(detalle or " ", size=t.TYPE_HELP, color=t.MID_GRAY),
            ],
        ),
    )


def card_surface(
    *controls: ft.Control,
    padding: int = t.SPACE_MD,
    title: str = "",
) -> ft.Control:
    inner: list[ft.Control] = []
    if title:
        inner.append(t.text_section(title))
    inner.extend(controls)
    return ft.Container(
        bgcolor=t.SURFACE_CARD,
        padding=padding,
        border_radius=t.RADIUS_MD,
        border=ft.Border.all(1, t.BORDER),
        content=ft.Column(spacing=t.SPACE_SM, tight=True, controls=inner),
    )


def status_chip(texto: str, *, tone: str = "neutral") -> ft.Control:
    tones = {
        "neutral": (t.LIGHT_GRAY, t.DARK_TEXT),
        "ok": (t.SUCCESS_BG, t.SUCCESS),
        "warn": (t.WARNING_BG, t.WARNING),
        "danger": (t.DANGER_BG, t.DANGER),
        "info": (t.INFO_BG, t.INFO),
    }
    bg, fg = tones.get(tone, tones["neutral"])
    return ft.Container(
        bgcolor=bg,
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        border_radius=20,
        content=ft.Text(texto, size=11, color=fg, weight=ft.FontWeight.W_600),
    )


def primary_button(
    label: str,
    on_click: Callable[[], None],
    *,
    icon=None,
    disabled: bool = False,
) -> ft.Control:
    return ft.FilledButton(
        label,
        icon=icon,
        disabled=disabled,
        style=ft.ButtonStyle(
            bgcolor=t.NAVY,
            color=t.WHITE,
            shape=ft.RoundedRectangleBorder(radius=t.RADIUS_SM),
        ),
        on_click=lambda _e: on_click(),
    )


def secondary_button(
    label: str,
    on_click: Callable[[], None],
    *,
    icon=None,
    disabled: bool = False,
) -> ft.Control:
    return ft.OutlinedButton(
        label,
        icon=icon,
        disabled=disabled,
        style=ft.ButtonStyle(
            color=t.NAVY,
            shape=ft.RoundedRectangleBorder(radius=t.RADIUS_SM),
        ),
        on_click=lambda _e: on_click(),
    )


def table_header_row(*labels: tuple[str, float | None]) -> ft.Control:
    """Cabecera de tabla: cada ítem es (texto, width|None=expand)."""
    cols: list[ft.Control] = []
    for texto, width in labels:
        cols.append(
            ft.Text(
                texto,
                size=11,
                weight=ft.FontWeight.W_600,
                color=t.MID_GRAY,
                width=width,
                expand=width is None,
            )
        )
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        bgcolor=t.LIGHT_GRAY,
        content=ft.Row(controls=cols),
    )


def auth_card(
    *controls: ft.Control,
    titulo: str,
    subtitulo: str = "",
    width: float = 440,
) -> ft.Control:
    """Tarjeta de acceso centrada (login / bootstrap / launcher)."""
    body: list[ft.Control] = [
        ft.Text(
            t.APP_NAME,
            size=28,
            weight=ft.FontWeight.BOLD,
            color=t.NAVY,
        ),
        ft.Text(
            t.HOTEL_DEFAULT,
            size=12,
            weight=ft.FontWeight.W_600,
            color=t.GOLD,
        ),
        ft.Text(
            titulo,
            size=18,
            weight=ft.FontWeight.W_600,
            color=t.DARK_TEXT,
        ),
    ]
    if subtitulo:
        body.append(
            ft.Text(
                subtitulo,
                size=t.TYPE_BODY,
                color=t.MID_GRAY,
                text_align=ft.TextAlign.CENTER,
            )
        )
    body.extend(controls)
    return ft.Container(
        width=width,
        bgcolor=t.SURFACE_CARD,
        border_radius=t.RADIUS_LG,
        border=ft.Border.all(1, t.BORDER),
        padding=t.SPACE_XL,
        shadow=ft.BoxShadow(
            blur_radius=24,
            color="#0B1F3A18",
            offset=ft.Offset(0, 8),
        ),
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=t.SPACE_MD,
            tight=True,
            controls=body,
        ),
    )


def branded_page(*controls: ft.Control) -> ft.Control:
    """Fondo de superficie para pantallas de entrada."""
    return ft.Container(
        expand=True,
        bgcolor=t.SURFACE,
        alignment=ft.Alignment.CENTER,
        padding=t.SPACE_XL,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=t.SPACE_LG,
            tight=True,
            scroll=ft.ScrollMode.AUTO,
            controls=list(controls),
        ),
    )


def coincide_campos_busqueda(termino: str, *campos: str) -> bool:
    """True si el término coincide con alguno de los campos (contiene_texto)."""
    from app.core.services.text_search import contiene_texto

    q = (termino or "").strip()
    if not q:
        return True
    return any(contiene_texto(str(c or ""), q) for c in campos)
