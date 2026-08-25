"""Gráficos simples con controles Flet (sin Altair / BarChart nativo)."""

from __future__ import annotations

import math

import flet as ft
import flet.canvas as cv

from app.presentation.flet.analisis_viewmodels import BarItemVM, ChartSeriesVM
from app.presentation.flet import theme as t

_COLORS = t.CHART_COLORS
_BAR_MAX_WIDTH = 320.0


def normalize_donut_slices(
    items: tuple[BarItemVM, ...] | list[BarItemVM],
    *,
    min_pct: float = 3.0,
    max_slices: int = 6,
) -> list[BarItemVM]:
    """Agrupa cola < min_pct (y exceso de sectores) en «Otros»."""
    datos = [i for i in items if (i.importe or 0) > 0]
    if not datos:
        return []
    total = sum(float(i.importe) for i in datos) or 1.0
    enriched: list[tuple[BarItemVM, float]] = []
    for i in datos:
        pct = float(i.porcentaje) if i.porcentaje else round(100.0 * float(i.importe) / total, 1)
        enriched.append(
            (
                BarItemVM(
                    categoria=i.categoria,
                    importe=float(i.importe),
                    porcentaje=pct,
                    importe_fmt=i.importe_fmt or f"{i.importe:.2f}",
                ),
                pct,
            )
        )
    enriched.sort(key=lambda x: x[1], reverse=True)
    keep: list[BarItemVM] = []
    otros_imp = 0.0
    for idx, (item, pct) in enumerate(enriched):
        if idx < max_slices - 1 and pct >= min_pct:
            keep.append(item)
        else:
            otros_imp += float(item.importe)
    if otros_imp > 0:
        keep.append(
            BarItemVM(
                categoria="Otros",
                importe=otros_imp,
                porcentaje=round(100.0 * otros_imp / total, 1),
                importe_fmt=f"{otros_imp:.2f}",
            )
        )
    # Recalcular % por si redondeos
    tot2 = sum(float(i.importe) for i in keep) or 1.0
    return [
        BarItemVM(
            categoria=i.categoria,
            importe=float(i.importe),
            porcentaje=round(100.0 * float(i.importe) / tot2, 1),
            importe_fmt=i.importe_fmt,
        )
        for i in keep
    ]


def _fmt_centro_total(total: float, slices: list[BarItemVM]) -> str:
    """Centro del donut: preferir € legible."""
    sample = next((s.importe_fmt for s in slices if s.importe_fmt), "")
    if "€" in sample or "EUR" in sample.upper():
        return f"{total:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    if total >= 100:
        return f"{total:,.0f}".replace(",", ".")
    return f"{total:.2f}"


def _annulus_slice_path(
    cx: float,
    cy: float,
    r_out: float,
    r_in: float,
    start: float,
    sweep: float,
    color: str,
) -> cv.Path:
    """Sector anular aproximado con segmentos (círculo suave en Flet Canvas)."""
    sweep = max(0.0, min(sweep, 2 * math.pi))
    steps = max(12, int(abs(sweep) / (math.pi / 48)) + 1)  # ~3.75°
    elems: list = []
    for i in range(steps + 1):
        a = start + sweep * (i / steps)
        x = cx + r_out * math.cos(a)
        y = cy + r_out * math.sin(a)
        elems.append(cv.Path.MoveTo(x, y) if i == 0 else cv.Path.LineTo(x, y))
    for i in range(steps, -1, -1):
        a = start + sweep * (i / steps)
        x = cx + r_in * math.cos(a)
        y = cy + r_in * math.sin(a)
        elems.append(cv.Path.LineTo(x, y))
    elems.append(cv.Path.Close())
    return cv.Path(
        elems,
        paint=ft.Paint(color=color, style=ft.PaintingStyle.FILL, anti_alias=True),
    )


def build_donut(
    items: tuple[BarItemVM, ...] | list[BarItemVM],
    *,
    titulo: str = "",
    size: float = 168,
    empty_msg: str = "Sin datos en el periodo.",
    centro_fmt: str = "",
) -> ft.Control:
    """Donut (Canvas) + leyenda debajo. Sin expand (evita bloques grises vacíos)."""
    rows: list[ft.Control] = []
    if titulo:
        rows.append(ft.Text(titulo, size=14, weight=ft.FontWeight.BOLD, color=t.DARK_TEXT))
    slices = normalize_donut_slices(items)
    if not slices:
        rows.append(ft.Text(empty_msg, italic=True, color=ft.Colors.OUTLINE, size=13))
        return ft.Column(spacing=6, tight=True, controls=rows)

    pad = 6.0
    ring = max(22.0, size * 0.22)
    r_out = size / 2.0
    r_in = max(8.0, r_out - ring)
    canvas_size = size + pad * 2
    cx = pad + r_out
    cy = pad + r_out
    total = sum(float(s.importe) for s in slices) or 1.0
    angle = -math.pi / 2
    shapes: list[cv.Shape] = []

    if len(slices) == 1:
        color = _COLORS[0]
        shapes.append(
            cv.Circle(
                x=cx,
                y=cy,
                radius=r_out,
                paint=ft.Paint(color=color, style=ft.PaintingStyle.FILL, anti_alias=True),
            )
        )
        shapes.append(
            cv.Circle(
                x=cx,
                y=cy,
                radius=r_in,
                paint=ft.Paint(
                    color=t.SURFACE_CARD,
                    style=ft.PaintingStyle.FILL,
                    anti_alias=True,
                ),
            )
        )
    else:
        for idx, sl in enumerate(slices):
            sweep = (float(sl.importe) / total) * 2 * math.pi
            if sweep <= 1e-6:
                continue
            color = _COLORS[idx % len(_COLORS)]
            shapes.append(
                _annulus_slice_path(cx, cy, r_out, r_in, angle, sweep, color)
            )
            angle += sweep

    centro = centro_fmt or _fmt_centro_total(total, slices)

    donut = ft.Container(
        width=canvas_size,
        height=canvas_size,
        content=ft.Stack(
            width=canvas_size,
            height=canvas_size,
            controls=[
                cv.Canvas(
                    shapes=shapes,
                    width=canvas_size,
                    height=canvas_size,
                ),
                ft.Container(
                    width=canvas_size,
                    height=canvas_size,
                    alignment=ft.Alignment(0, 0),
                    content=ft.Text(
                        centro,
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color=t.DARK_TEXT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ),
            ],
        ),
    )

    legend = ft.Column(
        spacing=5,
        tight=True,
        controls=[
            ft.Row(
                spacing=8,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=10,
                        height=10,
                        bgcolor=_COLORS[i % len(_COLORS)],
                        border_radius=2,
                    ),
                    ft.Text(
                        f"{sl.categoria}: {sl.importe_fmt or f'{sl.importe:.2f}'} "
                        f"({sl.porcentaje:.1f}%)",
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
            )
            for i, sl in enumerate(slices)
        ],
    )

    rows.append(
        ft.Column(
            spacing=10,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[donut, legend],
        )
    )
    return ft.Column(spacing=8, tight=True, controls=rows)


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
