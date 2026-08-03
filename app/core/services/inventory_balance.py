"""Abstracción de cantidad disponible por lote (Fase 7B.2 / 7B.5).

- ``legacy`` / ``shadow``: ``cantidad_restante`` (operativo).
- ``ledger``: saldo ledger si cobertura completa; si no, híbrido legacy.
"""

from __future__ import annotations

from app.core.models import AppData, LoteStock
from app.core.services.ledger_config import ledger_balance_mode, tolerancia_cantidad
from app.core.services.ledger_reconciliacion_service import (
    EstadoCoberturaLedger,
    clasificar_cobertura_lote,
    saldo_teorico_ledger,
)


def cantidad_disponible_lote(data: AppData, lote: LoteStock) -> float:
    if getattr(lote, "anulado", False):
        return 0.0
    modo = ledger_balance_mode(data)
    if modo != "ledger":
        return float(lote.cantidad_restante)

    rec = clasificar_cobertura_lote(data, lote)
    if rec.cobertura == EstadoCoberturaLedger.COBERTURA_COMPLETA:
        return max(0.0, float(rec.saldo_teorico))
    # Histórico / parcial: no mezclar sin regla — mantener legacy.
    return float(lote.cantidad_restante)


def stock_disponible_producto(data: AppData, producto_id: str) -> float:
    return sum(
        cantidad_disponible_lote(data, l)
        for l in data.lotes
        if l.producto_id == producto_id and not getattr(l, "anulado", False)
    )


def sincronizar_espejo_restante_desde_ledger(
    data: AppData, lote: LoteStock
) -> None:
    """Actualiza cantidad_restante como espejo tras operación en modo ledger.

    Autoridad: ledger. El restante es compatibilidad, no segunda escritura
    independiente de negocio.
    """
    if ledger_balance_mode(data) != "ledger":
        return
    rec = clasificar_cobertura_lote(data, lote)
    if rec.cobertura != EstadoCoberturaLedger.COBERTURA_COMPLETA:
        return
    lote.cantidad_restante = round(float(rec.saldo_teorico), 4)


def diferencias_shadow_criticas(data: AppData) -> list[str]:
    """Diferencias posteriores a activación fuera de tolerancia."""
    from app.core.services.ledger_balance_service import diagnostico_modo_sombra

    diag = diagnostico_modo_sombra(data)
    return [
        f"{d.lote_id}: diff={d.diferencia:g} cob={d.cobertura.value}"
        for d in diag.diferencias_post_activacion
    ]


def cuadra_dentro_tolerancia(a: float, b: float, data: AppData) -> bool:
    return abs(float(a) - float(b)) <= tolerancia_cantidad(data) + 1e-12


def saldo_ledger_raw(data: AppData, lote_id: str) -> float:
    return saldo_teorico_ledger(data, lote_id)
