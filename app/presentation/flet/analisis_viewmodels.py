"""Viewmodels Análisis (Costes / Consumo / Merma) — permiten campos económicos.

Solo para la sección Admin «analisis». No usar en Restaurante/Inventario.
"""

from __future__ import annotations

from dataclasses import dataclass


ANALISIS_HUBS: tuple[str, ...] = ("costes", "consumo", "merma")

ANALISIS_HUB_LABEL: dict[str, str] = {
    "costes": "Costes",
    "consumo": "Consumo",
    "merma": "Merma",
}

COSTES_PESTANAS: tuple[str, ...] = (
    "Resumen",
    "Desayuno",
    "Comida",
    "Cena",
    "Bebidas",
)

CONSUMO_PESTANAS: tuple[str, ...] = (
    "Resumen",
    "Desayuno",
    "Comida",
    "Cena",
    "Bebidas",
)

MERMA_PESTANAS: tuple[str, ...] = (
    "Resumen",
    "Desayuno",
    "Comida",
    "Cena",
    "Bebidas",
    "Almacén / General",
    "Sin desglose histórico",
)

CONSUMO_TIPOS: tuple[str, ...] = (
    "Todos",
    "Recetas",
    "Productos y extras",
    "Bebidas",
)


@dataclass(frozen=True)
class MetricVM:
    etiqueta: str
    valor: str
    detalle: str = ""


@dataclass(frozen=True)
class BarItemVM:
    categoria: str
    importe: float
    porcentaje: float = 0.0
    importe_fmt: str = ""


@dataclass(frozen=True)
class ChartSeriesVM:
    titulo: str
    series: tuple[str, ...]
    # filas: fecha_label -> valores por serie
    puntos: tuple[dict[str, float | str], ...]


@dataclass(frozen=True)
class RankingRowVM:
    nombre: str
    cantidad_fmt: str = ""
    usos: int | str = ""
    coste_fmt: str = ""
    tipo: str = ""
    extra: str = ""


@dataclass(frozen=True)
class RankingBlockVM:
    titulo: str
    filas: tuple[RankingRowVM, ...]


@dataclass(frozen=True)
class AnalisisPanelVM:
    hub: str = "costes"
    pestana: str = "Resumen"
    subtab: str = ""
    desde: str = ""
    hasta: str = ""
    busqueda: str = ""
    tipo_filtro: str = "Todos"
    aviso: str = ""
    metrics: tuple[MetricVM, ...] = ()
    chart_barras: tuple[tuple[str, tuple[BarItemVM, ...]], ...] = ()
    chart_lineas: tuple[ChartSeriesVM, ...] = ()
    rankings: tuple[RankingBlockVM, ...] = ()
    # Comparación costes (solo hub costes / Resumen)
    cmp_a_desde: str = ""
    cmp_a_hasta: str = ""
    cmp_b_desde: str = ""
    cmp_b_hasta: str = ""
    cmp_metrics: tuple[MetricVM, ...] = ()
    cmp_barras: tuple[BarItemVM, ...] = ()
    export_mensaje: str = ""
    puede_consultar: bool = False
