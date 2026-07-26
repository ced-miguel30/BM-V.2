"""Descuento de inventario por lotes.

Extraído sin cambios de comportamiento FIFO desde `desayuno_service`:
los lotes se consumen en orden `(fecha_compra, id)` ascendente
(el más antiguo primero). No alterar este orden.

Fase 9: planificación sin mutar + aplicación atómica (todo o nada).
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


def snapshot_cantidades_restantes(data: AppData) -> dict[str, float]:
    return {lote.id: lote.cantidad_restante for lote in data.lotes}


def restaurar_cantidades_restantes(data: AppData, snapshot: dict[str, float]) -> None:
    for lote in data.lotes:
        if lote.id in snapshot:
            lote.cantidad_restante = snapshot[lote.id]


@dataclass
class LineaPreviewStock:
    producto_id: str
    nombre: str
    unidad: str
    actual: float
    salida: float
    resultante: float
    coste_estimado: float
    ok: bool


@dataclass
class PlanDescuentoStock:
    lineas: list[LineaPreviewStock] = field(default_factory=list)
    ok: bool = True
    deficits: list[str] = field(default_factory=list)


def planificar_descuento(
    data: AppData,
    demandas: dict[str, float],
    *,
    nombres: dict[str, str] | None = None,
    unidades: dict[str, str] | None = None,
) -> PlanDescuentoStock:
    """Vista previa no mutante: actual / salida / resultante por producto."""
    nombres = nombres or {}
    unidades = unidades or {}
    lineas: list[LineaPreviewStock] = []
    deficits: list[str] = []

    for producto_id, cantidad in demandas.items():
        if cantidad <= 0:
            continue
        actual = round(stock_disponible(data, producto_id), 4)
        salida = round(float(cantidad), 4)
        resultante = round(actual - salida, 4)
        ok = resultante >= -1e-9
        if ok and resultante < 0:
            resultante = 0.0
        nombre = nombres.get(producto_id, producto_id)
        unidad = unidades.get(producto_id, "")
        coste = calcular_coste_linea(data, producto_id, salida) if ok else 0.0
        lineas.append(LineaPreviewStock(
            producto_id=producto_id,
            nombre=nombre,
            unidad=unidad,
            actual=actual,
            salida=salida,
            resultante=max(resultante, 0.0) if ok else resultante,
            coste_estimado=coste,
            ok=ok,
        ))
        if not ok:
            deficits.append(
                f"{nombre}: necesita {salida:g} {unidad}, disponible {actual:g} {unidad}"
                f" → quedaría {resultante:g} {unidad}".rstrip(),
            )

    return PlanDescuentoStock(lineas=lineas, ok=not deficits, deficits=deficits)


def descontar_lotes(
    data: AppData,
    producto_id: str,
    cantidad: float,
    *,
    permitir_negativo: bool = False,
) -> float:
    """Descuenta `cantidad` de los lotes FIFO y devuelve el coste.

    Si no hay stock suficiente y `permitir_negativo` es False, no muta nada
    de este producto y lanza ValueError (Fase 9).
    """
    if cantidad <= 0:
        return 0.0

    if not permitir_negativo:
        disponible = stock_disponible(data, producto_id)
        if cantidad > disponible + 1e-9:
            raise ValueError(
                f"Stock insuficiente para descontar {cantidad:g} "
                f"(disponible {disponible:g}) del producto {producto_id}."
            )

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
            lote_destino.cantidad_restante = round(
                lote_destino.cantidad_restante - restante, 4,
            )

    return round(coste, 2)


def aplicar_descuento_atomico(
    data: AppData,
    demandas: dict[str, float],
) -> dict[str, float]:
    """Descuenta todos los productos o ninguno. Devuelve costes por producto_id.

    Requiere stock suficiente (sin negativos). Si falla a mitad, restaura lotes.
    """
    plan = planificar_descuento(data, demandas)
    if not plan.ok:
        raise ValueError("Stock insuficiente; no se aplica ningún descuento.")

    snap = snapshot_cantidades_restantes(data)
    costes: dict[str, float] = {}
    try:
        for producto_id, cantidad in demandas.items():
            if cantidad <= 0:
                continue
            costes[producto_id] = descontar_lotes(
                data, producto_id, cantidad, permitir_negativo=False,
            )
    except Exception:
        restaurar_cantidades_restantes(data, snap)
        raise
    return costes
