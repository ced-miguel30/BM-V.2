"""Modelo de recetas con ingredientes de producto."""

from dataclasses import dataclass, field


@dataclass
class IngredienteReceta:
    producto_id: str
    cantidad: float


@dataclass
class Receta:
    id: str
    nombre: str
    ingredientes: list[IngredienteReceta] = field(default_factory=list)
