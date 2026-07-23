"""Modelo de registro de merma."""

from dataclasses import dataclass, field
from datetime import date, time

from app.core.models.enums import MotivoMerma


@dataclass
class LineaMerma:
    producto_id: str
    cantidad: float
    coste: float
    motivo: MotivoMerma
    comentario: str | None = None
    lote_id: str | None = None
    # Snapshot histórico: desayuno|comida|cena|bebidas|general.
    # None = registro antiguo sin desglose (no reinterpretar).
    tipo_servicio_snapshot: str | None = None


@dataclass
class RegistroMerma:
    id: str
    fecha: date
    lineas: list[LineaMerma] = field(default_factory=list)
    coste_total: float = 0.0
    registrado_por: str = ""
    hora: time | None = None
