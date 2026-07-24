"""Modelo de producto."""

from dataclasses import dataclass, field

from app.core.models.enums import UnidadProducto


@dataclass
class Producto:
    id: str
    nombre: str
    unidad: UnidadProducto
    stock_minimo: float | None = None
    es_bebida: bool = False
    # En qué registros puede usarse (desayuno|comida|cena|bebidas).
    # Lista vacía = «No configurado» (no significa «todos»).
    servicios_disponibles: list[str] = field(default_factory=list)
    # Organización de catálogo (ej. Verduras). No filtra registros por sí sola.
    categoria_inventario: str | None = None
