"""Sistema de diseño Flet — Royal Marina / BM‑V.2 (tokens sobrios).

Alineado con `app/ui/theme.py` (Streamlit) sin acoplar a Streamlit.
"""

from __future__ import annotations

import flet as ft

# Identidad
APP_NAME = "BM‑V.2"
APP_SUBTITLE = "Breakfast Management"
HOTEL_DEFAULT = "Royal Marina Suites"

# Paleta
NAVY = "#0B1F3A"
NAVY_LIGHT = "#152D4F"
NAVY_MUTED = "#2A3F5F"
TEAL = "#2F6F7E"
GOLD = "#C9A227"
GOLD_SOFT = "#E8D5A3"
WHITE = "#FFFFFF"
SURFACE = "#F7F8FA"
SURFACE_CARD = "#FFFFFF"
LIGHT_GRAY = "#F5F6F8"
MID_GRAY = "#8B95A5"
DARK_TEXT = "#1A2332"
BORDER = "#E2E6EC"
BORDER_STRONG = "#C5CCD6"

SUCCESS = "#2E7D5A"
SUCCESS_BG = "#E8F5EF"
WARNING = "#B8860B"
WARNING_BG = "#FFF8E7"
DANGER = "#C0392B"
DANGER_BG = "#FDECEA"
INFO = "#3A6EA5"
INFO_BG = "#EAF2FB"

# Tipografía (tamaños)
TYPE_PAGE = 22
TYPE_SECTION = 15
TYPE_KPI = 26
TYPE_KPI_SECONDARY = 18
TYPE_BODY = 13
TYPE_LABEL = 11
TYPE_HELP = 12
TYPE_TABLE = 12

# Espaciado / forma
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
RADIUS_SM = 6
RADIUS_MD = 10
RADIUS_LG = 14
SIDEBAR_WIDTH = 248
ICON_SM = 18
ICON_MD = 22

CHART_COLORS: tuple[str, ...] = (
    NAVY,
    TEAL,
    GOLD,
    WARNING,
    DANGER,
    INFO,
    SUCCESS,
    NAVY_MUTED,
)


def apply_page_theme(page: ft.Page, *, title: str = APP_NAME) -> None:
    """Aplica tema claro profesional a una página Flet."""
    page.title = title
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = SURFACE
    page.padding = 0
    page.theme = ft.Theme(
        color_scheme_seed=NAVY,
        visual_density=ft.VisualDensity.COMFORTABLE,
    )


def text_page_title(texto: str) -> ft.Text:
    return ft.Text(
        texto,
        size=TYPE_PAGE,
        weight=ft.FontWeight.BOLD,
        color=DARK_TEXT,
    )


def text_section(texto: str) -> ft.Text:
    return ft.Text(
        texto,
        size=TYPE_SECTION,
        weight=ft.FontWeight.W_600,
        color=DARK_TEXT,
    )


def text_help(texto: str) -> ft.Text:
    return ft.Text(texto, size=TYPE_HELP, color=MID_GRAY)


def text_label(texto: str) -> ft.Text:
    return ft.Text(texto, size=TYPE_LABEL, color=MID_GRAY, weight=ft.FontWeight.W_500)
