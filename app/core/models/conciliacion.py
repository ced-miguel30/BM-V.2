"""Conciliación línea factura ↔ línea albarán (A7 / Plan v3 D60)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class EstadoConciliacion(str, Enum):
    ACTIVA = "activa"
    ANULADA = "anulada"


@dataclass
class ConciliacionLineaDocumento:
    id: str
    linea_factura_id: str
    linea_albaran_id: str
    cantidad_conciliada: Decimal  # unidad inventario del albarán
    fecha: date
    estado: EstadoConciliacion | str = EstadoConciliacion.ACTIVA
    importe_conciliado: Decimal | None = None
    creado_en: datetime | None = None
    anulada_en: datetime | None = None
    motivo_anulacion: str | None = None
    usuario_id: str | None = None
    confirmacion_id: str | None = None  # de la factura que la creó
