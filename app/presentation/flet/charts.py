"""Gráficos simples con controles Flet (sin Altair / BarChart nativo)."""

from __future__ import annotations

import flet as ft

from app.presentation.flet.analisis_viewmodels import BarItemVM, ChartSeriesVM

_COLORS = (
    ft.Colors.BLUE_700,
    ft.Colors.AMBER_700,
    ft.Colors.RED_700,
    ft.Colors.TEAL_700,
    ft.Colors.PURPLE_700,
    ft.Colors.GREEN_700,
    ft.Colors.ORANGE_700,
    ft.Colors.INDIGO_700,
)

_BAR_MAX_WIDTH = 320.0


def build_barras_horizontales(
    items: tuple[BarItemVM, ...] | list[BarItemVM],
    *,
    titulo: str = "",
    empty_msg: str = "Sin datos en el periodo.",
) -> ft.Control:
    rows: list[ft.Control] = []
    if titulo:
        rows.append(ft.Text(titulo, size=15, weight=ft.FontWeight.BOLD))
    datos = [i for i in items if (i.importe or 0) > 0]
    if not datos:
        rows.append(ft.Text(empty_msg, italic=True, color=ft.Colors.OUTLINE, size=13))
        return ft.Column(spacing=6, tight=True, controls=rows)

    max_v = max(float(i.importe) for i in datos) or 1.0
    for idx, item in enumerate(datos):
        width = max(4.0, (_BAR_MAX_WIDTH * float(item.importe)) / max_v)
        label = item.importe_fmt or f"{item.importe:.2f}"
        pct = f" ({item.porcentaje:.1f}%)" if item.porcentaje else ""
        rows.append(
            ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    ft.Text(
                        f"{item.categoria}: {label}{pct}",
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Container(
                        width=width,
                        height=14,
                        bgcolor=_COLORS[idx % len(_COLORS)],
                        border_radius=4,
                    ),
                ],
            )
        )
    return ft.Column(spacing=8, tight=True, controls=rows)


def build_barras_agrupadas(
    items: tuple[BarItemVM, ...] | list[BarItemVM],
    *,
    titulo: str = "Comparación",
    empty_msg: str = "Sin datos.",
) -> ft.Control:
    """Barras simples por categoría (importe ya tipificado en BarItemVM)."""
    return build_barras_horizontales(items, titulo=titulo, empty_msg=empty_msg)


def build_lineas_series(
    chart: ChartSeriesVM,
    *,
    empty_msg: str = "Sin evolución en el periodo.",
) -> ft.Control:
    rows: list[ft.Control] = [
        ft.Text(chart.titulo, size=15, weight=ft.FontWeight.BOLD),
    ]
    if not chart.puntos or not chart.series:
        rows.append(ft.Text(empty_msg, italic=True, color=ft.Colors.OUTLINE, size=13))
        return ft.Column(spacing=6, tight=True, controls=rows)

    # Escala global
    max_v = 0.0
    for p in chart.puntos:
        for s in chart.series:
            try:
                max_v = max(max_v, float(p.get(s, 0) or 0))
            except (TypeError, ValueError):
                pass
    if max_v <= 0:
        rows.append(ft.Text(empty_msg, italic=True, color=ft.Colors.OUTLINE, size=13))
        return ft.Column(spacing=6, tight=True, controls=rows)

    # Leyenda
    legend = ft.Row(
        spacing=12,
        wrap=True,
        controls=[
            ft.Row(
                spacing=4,
                tight=True,
                controls=[
                    ft.Container(
                        width=12,
                        height=12,
                        bgcolor=_COLORS[i % len(_COLORS)],
                        border_radius=2,
                    ),
                    ft.Text(s, size=11),
                ],
            )
            for i, s in enumerate(chart.series)
        ],
    )
    rows.append(legend)

    # Por cada punto temporal: mini barras apiladas horizontales por serie
    for p in chart.puntos:
        fecha = str(p.get("fecha", ""))
        segs: list[ft.Control] = []
        for i, s in enumerate(chart.series):
            try:
                val = float(p.get(s, 0) or 0)
            except (TypeError, ValueError):
                val = 0.0
            if val <= 0:
                continue
            w = max(3.0, (_BAR_MAX_WIDTH * 0.55 * val) / max_v)
            segs.append(
                ft.Container(
                    width=w,
                    height=10,
                    bgcolor=_COLORS[i % len(_COLORS)],
                    border_radius=2,
                    tooltip=f"{s}: {val:.2f}",
                )
            )
        if not segs:
            continue
        rows.append(
            ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(fecha, size=11, width=48, color=ft.Colors.OUTLINE),
                    ft.Row(spacing=2, tight=True, controls=segs),
                ],
            )
        )
    return ft.Column(spacing=6, tight=True, controls=rows)
