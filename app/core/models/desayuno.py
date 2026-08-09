"""Modelo de registro de desayuno."""

from dataclasses import dataclass, field
from datetime import date, time

from app.core.models.registro_servicio import LineaDetalleOrigen


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
    categoria_receta_snapshot: str | None = None
    # Snapshots Fase 8 (aditivos; históricos → None).
    porciones_estandar_snapshot: float | None = None
    factor_aplicado: float | None = None


@dataclass
class RegistroDesayuno:
    id: str
    fecha: date
    lineas: list[LineaDesayuno] = field(default_factory=list)
    coste_total: float = 0.0
    registrado_por: str = ""
    num_huespedes: int = 30
    registros_recetas: list[RegistroRecetaDesayuno] = field(default_factory=list)
    hora: time | None = None
    # Detalle de origen por línea (aditivo; registros antiguos → lista vacía).
    lineas_detalle: list[LineaDetalleOrigen] = field(default_factory=list)
    # Fase 11A — soft-delete (aditivo; históricos → False / vacíos).
    anulado: bool = False
    fecha_anulacion: date | None = None
    hora_anulacion: time | None = None
    motivo_anulacion: str = ""
    referencia_anulacion: str = ""
    anulado_por: str = ""
    # Token de confirmación UI (aditivo; históricos → None). Evita doble registro.
    clave_idempotencia: str | None = None
    # Observaciones operativas del registro (aditivo; históricos → "").
    observaciones: str = ""
