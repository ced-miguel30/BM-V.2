"""Recuento físico de inventario por ubicación (Fase 7B.6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum


class EstadoRecuento(str, Enum):
    BORRADOR = "borrador"
    CONFIRMADO = "confirmado"
    ANULADO = "anulado"


@dataclass
class LineaRecuento:
    producto_id: str
    lote_id: str
    cantidad_esperada: float
    cantidad_contada: float
    producto_nombre_snapshot: str | None = None
    unidad_snapshot: str | None = None
    ajuste_id: str | None = None  # RegistroAjuste generado al confirmar

    @property
    def diferencia(self) -> float:
        return round(float(self.cantidad_contada) - float(self.cantidad_esperada), 4)


@dataclass
class SesionRecuento:
    id: str
    ubicacion_id: str
    fecha: date
    usuario_id: str | None
    estado: EstadoRecuento | str = EstadoRecuento.BORRADOR
    motivo: str | None = None
    lineas: list[LineaRecuento] = field(default_factory=list)
    hora: time | None = None
    creado_en: datetime | None = None
    confirmado_en: datetime | None = None
    anulado_en: datetime | None = None
    snapshot_esperado: dict[str, float] = field(default_factory=dict)
