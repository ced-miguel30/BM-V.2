"""Modelo de producto."""

from dataclasses import dataclass

from app.core.models.enums import UnidadProducto


@dataclass
class Producto:
    id: str
    nombre: str
    unidad: UnidadProducto
    stock_minimo: float | None = None
    es_bebida: bool = False
