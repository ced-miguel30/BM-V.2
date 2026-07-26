"""Modelo de ajuste de inventario (trazabilidad mínima, Fase 10)."""

from dataclasses import dataclass, field
from datetime import date, time

from app.core.models.enums import MotivoAjuste


@dataclass
class LineaAjuste:
    producto_id: str
    lote_id: str
    cantidad_antes: float
    cantidad_despues: float
    motivo: MotivoAjuste
    comentario: str | None = None
    producto_nombre_snapshot: str | None = None
    unidad_snapshot: str | None = None

    @property
    def delta(self) -> float:
        return round(self.cantidad_despues - self.cantidad_antes, 4)


@dataclass
class RegistroAjuste:
    id: str
    fecha: date
    lineas: list[LineaAjuste] = field(default_factory=list)
    registrado_por: str = ""
    hora: time | None = None
