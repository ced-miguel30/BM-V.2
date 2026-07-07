"""Modelo de registro de desayuno."""

from dataclasses import dataclass, field
from datetime import date


@dataclass
class LineaDesayuno:
    producto_id: str
    cantidad: float
    coste: float


@dataclass
class RegistroDesayuno:
    id: str
    fecha: date
    lineas: list[LineaDesayuno] = field(default_factory=list)
    coste_total: float = 0.0
    registrado_por: str = ""
