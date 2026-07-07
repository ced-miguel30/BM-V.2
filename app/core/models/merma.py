"""Modelo de registro de merma."""

from dataclasses import dataclass, field
from datetime import date

from app.core.models.enums import MotivoMerma


@dataclass
class LineaMerma:
    producto_id: str
    cantidad: float
    coste: float
    motivo: MotivoMerma
    comentario: str | None = None


@dataclass
class RegistroMerma:
    id: str
    fecha: date
    lineas: list[LineaMerma] = field(default_factory=list)
    coste_total: float = 0.0
    registrado_por: str = ""
