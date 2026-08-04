"""Proveedores, impuestos y relación comercial (Fase 8).

Sin facturas ni albaranes. ``marca_proveedor`` en lotes permanece como
snapshot histórico textual y no se reescribe al crear el maestro.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass
class Proveedor:
    """Maestro de proveedor (independiente del producto)."""

    id: str
    nombre_fiscal: str
    nombre_comercial: str | None = None
    nif_cif: str | None = None
    direccion: str | None = None
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None
    condiciones_pago: str | None = None
    activo: bool = True
    observaciones: str | None = None  # A5
    codigo: str | None = None  # A9; obligatorio en altas nuevas; legacy None OK


@dataclass
class Impuesto:
    """Impuesto versionado. El porcentaje no reescribe históricos (snapshot en líneas futuras)."""

    id: str
    nombre: str
    porcentaje: Decimal
    vigencia_desde: date | None = None
    vigencia_hasta: date | None = None
    activo: bool = True
    descripcion: str | None = None


@dataclass
class RelacionProductoProveedor:
    """Relación comercial producto ↔ proveedor.

    ``proveedor_nombre_snapshot`` congela el nombre visto al crear/actualizar
    el vínculo (histórico); el catálogo vivo no reescribe ese texto.
    """

    id: str
    producto_id: str
    proveedor_id: str
    codigo_proveedor: str | None = None
    preferente: bool = False
    proveedor_nombre_snapshot: str | None = None
    nif_cif_snapshot: str | None = None
    activo: bool = True
