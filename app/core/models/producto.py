"""Modelo de producto."""

from dataclasses import dataclass, field

from app.core.models.enums import TipoArticulo, UnidadProducto


@dataclass
class Producto:
    id: str
    nombre: str
    unidad: UnidadProducto
    stock_minimo: float | None = None
    es_bebida: bool = False
    # En qué registros puede usarse (desayuno|comida|cena|bebidas).
    # Lista vacía = «No configurado» (no significa «todos»).
    servicios_disponibles: list[str] = field(default_factory=list)
    # Organización de catálogo (ej. Verduras). No filtra registros por sí sola.
    # Campo histórico/libre conservado por compatibilidad; no sustituye categoria_id.
    categoria_inventario: str | None = None
    # Fase 6A — catálogo estructurado (opcional, aditivo).
    categoria_id: str | None = None
    subcategoria_id: str | None = None
    # Departamentos donde el producto puede utilizarse.
    # No representa ubicación física, cantidad, propiedad ni stock por departamento.
    departamento_ids: list[str] = field(default_factory=list)
    # Fase 6B — ubicaciones permitidas/habituales donde puede almacenarse.
    # No representa cantidades ni la ubicación real de cada lote.
    ubicacion_ids: list[str] = field(default_factory=list)
    # Fase 6C — clasificación fija (consumible / reutilizable).
    # None = histórico sin clasificar (sin backfill). str = valor desconocido conservado.
    # No equivale a es_bebida. Cambiar el tipo no altera stock/FIFO/lotes.
    tipo_articulo: TipoArticulo | str | None = None
