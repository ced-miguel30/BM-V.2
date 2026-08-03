"""Cálculo de saldo desde el ledger — modo sombra (Fase 7B.2).

En modo ``shadow`` / ``legacy`` la UI y los servicios operativos siguen
leyendo ``cantidad_restante``. El ledger se calcula en paralelo y se
registran diferencias; no cambia resultados operativos.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.models import AppData, LoteStock
from app.core.services.ledger_config import (
    ledger_balance_mode,
    tolerancia_cantidad,
)
from app.core.services.ledger_reconciliacion_service import (
    EstadoCoberturaLedger,
    clasificar_cobertura_lote,
    saldo_teorico_ledger,
    total_entradas_ledger,
    total_reversos_ledger,
    total_salidas_ledger,
)


@dataclass
class SaldoLedgerLote:
    lote_id: str
    producto_id: str
    entradas: float
    salidas: float
    reversos: float
    saldo_ledger: float
    cantidad_restante: float
    diferencia: float
    cobertura: EstadoCoberturaLedger
    dentro_tolerancia: bool


@dataclass
class SaldoLedgerProducto:
    producto_id: str
    saldo_ledger: float
    cantidad_restante: float
    diferencia: float
    dentro_tolerancia: bool
    lotes: list[SaldoLedgerLote] = field(default_factory=list)


@dataclass
class DiagnosticoSombra:
    modo: str
    tolerancia: float
    diferencias_lote: list[SaldoLedgerLote]
    diferencias_post_activacion: list[SaldoLedgerLote]
    num_lotes_comparados: int
    ok_post_activacion: bool


def saldo_ledger_por_lote(data: AppData, lote_id: str) -> float:
    """Función pura: entradas − salidas (traslados excluidos en reconciliación)."""
    return saldo_teorico_ledger(data, lote_id)


def saldo_ledger_por_producto(data: AppData, producto_id: str) -> float:
    total = 0.0
    for lote in data.lotes:
        if lote.producto_id != producto_id:
            continue
        if getattr(lote, "anulado", False):
            continue
        total += saldo_ledger_por_lote(data, lote.id)
    return round(total, 6)


def entradas_ledger_lote(data: AppData, lote_id: str) -> float:
    return total_entradas_ledger(data, lote_id)


def salidas_ledger_lote(data: AppData, lote_id: str) -> float:
    return total_salidas_ledger(data, lote_id)


def reversos_ledger_lote(data: AppData, lote_id: str) -> float:
    return total_reversos_ledger(data, lote_id)


def comparar_lote_vs_restante(
    data: AppData, lote: LoteStock
) -> SaldoLedgerLote:
    rec = clasificar_cobertura_lote(data, lote)
    tol = tolerancia_cantidad(data)
    diff = rec.diferencia
    return SaldoLedgerLote(
        lote_id=lote.id,
        producto_id=lote.producto_id,
        entradas=rec.entradas_ledger,
        salidas=rec.salidas_ledger,
        reversos=rec.reversos_ledger,
        saldo_ledger=rec.saldo_teorico,
        cantidad_restante=rec.cantidad_restante,
        diferencia=diff,
        cobertura=rec.cobertura,
        dentro_tolerancia=abs(diff) <= tol + 1e-12,
    )


def comparar_producto_vs_restante(
    data: AppData, producto_id: str
) -> SaldoLedgerProducto:
    lotes = [
        comparar_lote_vs_restante(data, l)
        for l in data.lotes
        if l.producto_id == producto_id and not getattr(l, "anulado", False)
    ]
    saldo_l = sum(x.saldo_ledger for x in lotes)
    restante = sum(x.cantidad_restante for x in lotes)
    diff = saldo_l - restante
    tol = tolerancia_cantidad(data)
    return SaldoLedgerProducto(
        producto_id=producto_id,
        saldo_ledger=round(saldo_l, 6),
        cantidad_restante=round(restante, 6),
        diferencia=round(diff, 6),
        dentro_tolerancia=abs(diff) <= tol + 1e-12,
        lotes=lotes,
    )


def diagnostico_modo_sombra(data: AppData) -> DiagnosticoSombra:
    """Compara ledger vs cantidad_restante sin mutar ni influir en ops."""
    modo = ledger_balance_mode(data)
    tol = tolerancia_cantidad(data)
    diffs: list[SaldoLedgerLote] = []
    post: list[SaldoLedgerLote] = []
    for lote in data.lotes:
        cmp = comparar_lote_vs_restante(data, lote)
        if not cmp.dentro_tolerancia:
            diffs.append(cmp)
        if (
            cmp.cobertura
            == EstadoCoberturaLedger.INCONSISTENCIA_POSTERIOR_ACTIVACION
        ):
            post.append(cmp)
    return DiagnosticoSombra(
        modo=modo,
        tolerancia=tol,
        diferencias_lote=diffs,
        diferencias_post_activacion=post,
        num_lotes_comparados=len(data.lotes),
        ok_post_activacion=len(post) == 0,
    )


def stock_operativo_lote(data: AppData, lote: LoteStock) -> float:
    """En 7B.2 (shadow/legacy) el operativo es siempre ``cantidad_restante``.

    La lectura operativa en modo ``ledger`` se resuelve en
    ``inventory_balance.cantidad_disponible_lote`` (7B.5).
    """
    _ = ledger_balance_mode(data)  # documenta dependencia del modo
    return float(lote.cantidad_restante)
