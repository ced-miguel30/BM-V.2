"""Documentos de compra (Fase 10–12).

Albaranes = F10. Facturas = F11. Rectificativas = F12.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum


class TipoDocumento(str, Enum):
    ALBARAN = "albaran"
    FACTURA = "factura"
    RECTIFICATIVA = "rectificativa"


class EstadoDocumento(str, Enum):
    BORRADOR = "borrador"
    CONFIRMADO = "confirmado"
    ANULADO = "anulado"
    RECTIFICADO = "rectificado"


@dataclass
class LineaDocumento:
    id: str
    producto_id: str
    cantidad: float
    precio_total: float
    impuesto_id: str | None = None
    impuesto_porcentaje_snapshot: Decimal | None = None
    ubicacion_destino_id: str | None = None
    lote_id: str | None = None  # asignado al confirmar (albarán o factura directa)
    producto_nombre_snapshot: str | None = None
    unidad_snapshot: str | None = None
    fecha_expiracion: date | None = None
    movimiento_id: str | None = None  # entrada ledger al confirmar (si aplica)
    # Conciliación (factura) o línea del documento rectificado (rectificativa)
    documento_origen_id: str | None = None
    linea_origen_id: str | None = None


@dataclass
class Documento:
    """Cabecera documental. ID técnico interno ≠ referencia_externa del proveedor."""

    id: str
    tipo: TipoDocumento | str
    estado: EstadoDocumento | str
    fecha_documento: date
    proveedor_id: str | None = None
    proveedor_nombre_snapshot: str | None = None
    nif_cif_snapshot: str | None = None
    referencia_externa: str | None = None  # nº documento del proveedor (no es ID)
    lineas: list[LineaDocumento] = field(default_factory=list)
    archivo_ids: list[str] = field(default_factory=list)
    registrado_por: str = ""
    hora: time | None = None
    creado_en: datetime | None = None
    confirmado_en: datetime | None = None
    anulado_en: datetime | None = None
    motivo_anulacion: str | None = None
    notas: str | None = None
    # Fase 12 — rectificativa enlazada al original confirmado
    documento_rectificado_id: str | None = None
    motivo_rectificacion: str | None = None
    rectificado_en: datetime | None = None  # en el original al pasar a RECTIFICADO
