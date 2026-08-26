"""Operaciones de inventario FIFO vía AppContext (Fase 4F).

Delega en `inventory_batch_service` sin cambiar el algoritmo FIFO.
No hace commit: el caller persiste con `ctx.uow.commit` si aplica.
"""

from __future__ import annotations

from app.core.application.context import AppContext
from app.core.services.inventory_batch_service import (
    PlanDescuentoStock,
    ResultadoDescuentoAtomico,
    ResultadoDescuentoLotes,
    aplicar_descuento_atomico as _aplicar,
    descontar_lotes as _descontar,
    planificar_descuento as _planificar,
    stock_disponible as _stock,
)


def stock_disponible(ctx: AppContext, producto_id: str) -> float:
    return _stock(ctx.data(), producto_id)


def planificar_descuento(
    ctx: AppContext,
    demandas: dict[str, float],
    *,
    nombres: dict[str, str] | None = None,
    unidades: dict[str, str] | None = None,
) -> PlanDescuentoStock:
    return _planificar(
        ctx.data(), demandas, nombres=nombres, unidades=unidades,
    )


def descontar_lotes(
    ctx: AppContext,
    producto_id: str,
    cantidad: float,
    *,
    permitir_negativo: bool = False,
) -> ResultadoDescuentoLotes:
    return _descontar(
        ctx.data(),
        producto_id,
        cantidad,
        permitir_negativo=permitir_negativo,
    )


def aplicar_descuento_atomico(
    ctx: AppContext,
    demandas: dict[str, float],
    *,
    permitir_negativo: bool = False,
) -> ResultadoDescuentoAtomico:
    """Mutará `ctx.data()`; no persiste solo."""
    return _aplicar(ctx.data(), demandas, permitir_negativo=permitir_negativo)
