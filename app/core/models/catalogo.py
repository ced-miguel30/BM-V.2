"""Catálogos de inventario (Fase 6A).

Departamentos, categorías y subcategorías estructurados.
No representan ubicación física ni stock por departamento.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Departamento:
    """Ámbito operativo donde un producto puede utilizarse (no ubicación)."""

    id: str
    nombre: str
    activo: bool = True


@dataclass
class Categoria:
    """Clasificación estructurada de producto (independiente de categoria_inventario)."""

    id: str
    nombre: str
    activo: bool = True


@dataclass
class Subcategoria:
    """Subclasificación; pertenece siempre a una categoría."""

    id: str
    nombre: str
    categoria_id: str
    activo: bool = True
