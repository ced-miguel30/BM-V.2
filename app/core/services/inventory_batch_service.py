"""Descuento de inventario por lotes.

Extraído sin cambios de comportamiento desde `desayuno_service`:
los lotes se consumen en orden FIFO por `(fecha_compra, id)` ascendente
(el más antiguo primero). No alterar este orden.
"""

from __future__ import annotations

from datetime import date

from app.core.models import AppData, LoteStock


def lotes_ordenados_consumo(data: AppData, producto_id: str) -> list[LoteStock]:
    """Lotes con stock > 0, del más antiguo al más reciente (FIFO)."""
    lotes = [
        l for l in data.lotes
        if l.producto_id == producto_id and l.cantidad_restante > 0
    ]
    return sorted(
        lotes,
        key=lambda l: (l.fecha_compra or date.min, l.id),
    )


def _ultimo_lote_producto(data: AppData, producto_id: str) -> LoteStock | None:
    lotes = [l for l in data.lotes if l.producto_id == producto_id]
    if not lotes:
        return None
    return sorted(lotes, key=lambda l: (l.fecha_compra or date.min, l.id))[-1]


def coste_unidad_lote(lote: LoteStock) -> float:
    if lote.cantidad <= 0:
        return 0.0
    return lote.precio_total / lote.cantidad


def stock_disponible(data: AppData, producto_id: str) -> float:
    return sum(l.cantidad_restante for l in data.lotes if l.producto_id == producto_id)


def calcular_coste_linea(data: AppData, producto_id: str, cantidad: float) -> float:
    if cantidad <= 0:
        return 0.0
    restante = cantidad
    coste = 0.0
    for lote in lotes_ordenados_consumo(data, producto_id):
        if restante <= 0:
            break
        tomar = min(restante, lote.cantidad_restante)
        coste += tomar * coste_unidad_lote(lote)
        restante -= tomar
    return round(coste, 2)


def descontar_lotes(
    data: AppData,
    producto_id: str,
    cantidad: float,
    *,
    permitir_negativo: bool = False,
) -> float:
    """Descuenta `cantidad` de los lotes FIFO y devuelve el coste."""
    if cantidad <= 0:
        return 0.0
    restante = cantidad
    coste = 0.0
    ultimo_lote_tocado: LoteStock | None = None
    for lote in lotes_ordenados_consumo(data, producto_id):
        if restante <= 0:
            break
        tomar = min(restante, lote.cantidad_restante)
        coste += tomar * coste_unidad_lote(lote)
        lote.cantidad_restante = round(lote.cantidad_restante - tomar, 4)
        restante -= tomar
        ultimo_lote_tocado = lote

    if restante > 0 and permitir_negativo:
        lote_destino = ultimo_lote_tocado or _ultimo_lote_producto(data, producto_id)
        if lote_destino:
            lote_destino.cantidad_restante = round(lote_destino.cantidad_restante - restante, 4)

    return round(coste, 2)
