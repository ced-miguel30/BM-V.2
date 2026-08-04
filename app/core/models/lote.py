"""Modelo de lote de stock."""

from dataclasses import dataclass
from datetime import date, time


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
    # Fase 11C — soft-delete de compra (aditivo; históricos → False).
    anulado: bool = False
    fecha_anulacion: date | None = None
    hora_anulacion: time | None = None
    motivo_anulacion: str = ""
    referencia_anulacion: str = ""
    anulado_por: str = ""
    # A7/B3 — trazabilidad documental (aditivo; legacy None).
    documento_origen_id: str | None = None
    linea_documento_origen_id: str | None = None
