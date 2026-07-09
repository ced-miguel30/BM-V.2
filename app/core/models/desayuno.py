"""Modelo de registro de desayuno."""

from dataclasses import dataclass, field
from datetime import date


@dataclass
class LineaDesayuno:
    producto_id: str
    cantidad: float
    coste: float
    es_extra: bool = False


@dataclass
class ExtraRecetaDesayuno:
    producto_id: str
    cantidad: float


@dataclass
class OmisionRecetaDesayuno:
    producto_id: str


@dataclass
class RegistroRecetaDesayuno:
    receta_id: str
    nombre_receta: str
    porciones: float
    extras: list[ExtraRecetaDesayuno] = field(default_factory=list)
    omisiones: list[OmisionRecetaDesayuno] = field(default_factory=list)


@dataclass
class RegistroDesayuno:
    id: str
    fecha: date
    lineas: list[LineaDesayuno] = field(default_factory=list)
    coste_total: float = 0.0
    registrado_por: str = ""
    num_huespedes: int = 30
    registros_recetas: list[RegistroRecetaDesayuno] = field(default_factory=list)
