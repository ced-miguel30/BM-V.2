"""Modelo de lote de stock."""

from dataclasses import dataclass
from datetime import date


@dataclass
class LoteStock:
    id: str
    producto_id: str
    precio_total: float
    cantidad: float
    cantidad_restante: float
    fecha_compra: date | None = None
    fecha_expiracion: date | None = None
    marca_proveedor: str | None = None
    alerta_expiracion_dias: int | None = None
