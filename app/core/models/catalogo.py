"""Catálogos de inventario (Fases 6A–6B).

Departamentos, categorías, subcategorías y ubicaciones estructurados.
Las ubicaciones no materializan stock ni sustituyen departamentos.
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


@dataclass
class Ubicacion:
    """Lugar identificable donde puede existir físicamente inventario.

    No representa cantidad, ubicación actual de un lote, departamento ni stock
    materializado por ubicación.
    """

    id: str
    nombre: str
    activo: bool = True
    # A9 — código funcional; obligatorio en altas nuevas; legacy None admitido.
    codigo: str | None = None
