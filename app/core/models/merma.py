"""Modelo de registro de merma."""

from dataclasses import dataclass, field
from datetime import date, time

from app.core.models.enums import MotivoMerma


@dataclass
class ResponsableMerma:
    """Catálogo de responsables de merma (soft-delete vía activo)."""

    id: str
    nombre: str
    activo: bool = True


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
    # Aditivos Fase 5 — ausentes en histórico → None.
    turno_snapshot: str | None = None
    responsable_id: str | None = None
    responsable_nombre: str | None = None
    producto_nombre_snapshot: str | None = None
    unidad_snapshot: str | None = None


@dataclass
class RegistroMerma:
    id: str
    fecha: date
    lineas: list[LineaMerma] = field(default_factory=list)
    coste_total: float = 0.0
    registrado_por: str = ""
    hora: time | None = None
    # Fase 11B — soft-delete (aditivo; históricos → False / vacíos).
    anulado: bool = False
    fecha_anulacion: date | None = None
    hora_anulacion: time | None = None
    motivo_anulacion: str = ""
    referencia_anulacion: str = ""
    anulado_por: str = ""
