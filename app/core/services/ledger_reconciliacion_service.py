"""Reconciliación reforzada del ledger (Fase 7B.1).

No destructiva, repetible, auditable. No corrige saldos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any

from app.core.models import AppData, LoteStock, MovimientoInventario
from app.core.models.enums import DireccionMovimiento, TipoMovimiento
from app.core.services import movimiento_service as mov
from app.core.services.ledger_config import (
    asegurar_frontera_activacion,
    frontera_activacion,
    ledger_balance_mode,
    ledger_schema_version,
    movimiento_es_posterior_activacion,
    tolerancia_cantidad,
)


class EstadoCoberturaLedger(str, Enum):
    HISTORICO_SIN_LEDGER = "historico_sin_ledger"
    COBERTURA_PARCIAL = "cobertura_parcial"
    COBERTURA_COMPLETA = "cobertura_completa"
    INCONSISTENCIA_POSTERIOR_ACTIVACION = "inconsistencia_posterior_activacion"
    SIN_MOVIMIENTOS = "sin_movimientos"


def _enum_value(val: Any) -> str:
    return val.value if hasattr(val, "value") else str(val)


def _es_traslado(m: MovimientoInventario) -> bool:
    return _enum_value(m.tipo) == "traslado"


def _movimientos_lote(data: AppData, lote_id: str) -> list[MovimientoInventario]:
    return [m for m in mov.buscar_por_lote(data, lote_id) if not _es_traslado(m)]


def total_entradas_ledger(data: AppData, lote_id: str) -> float:
    return sum(
        float(m.cantidad)
        for m in _movimientos_lote(data, lote_id)
        if _enum_value(m.direccion) == DireccionMovimiento.ENTRADA.value
    )


def total_salidas_ledger(data: AppData, lote_id: str) -> float:
    return sum(
        float(m.cantidad)
        for m in _movimientos_lote(data, lote_id)
        if _enum_value(m.direccion) == DireccionMovimiento.SALIDA.value
    )


def total_reversos_ledger(data: AppData, lote_id: str) -> float:
    """Suma de cantidades de tipos de reversión (informativo)."""
    tipos_reverso = {
        TipoMovimiento.REVERSION_CONSUMO.value,
        TipoMovimiento.REVERSION_MERMA.value,
        TipoMovimiento.REVERSION_ENTRADA.value,
    }
    return sum(
        float(m.cantidad)
        for m in _movimientos_lote(data, lote_id)
        if _enum_value(m.tipo) in tipos_reverso
    )


def saldo_teorico_ledger(data: AppData, lote_id: str) -> float:
    return round(total_entradas_ledger(data, lote_id) - total_salidas_ledger(data, lote_id), 6)


def primera_operacion_ledger(
    data: AppData, lote_id: str
) -> datetime | date | None:
    movs = _movimientos_lote(data, lote_id)
    if not movs:
        return None
    creados = [m.creado_en for m in movs if m.creado_en is not None]
    if creados:
        return min(creados)
    fechas = [m.fecha for m in movs if m.fecha is not None]
    return min(fechas) if fechas else None


@dataclass
class ReconciliacionLote:
    lote_id: str
    producto_id: str
    cantidad_original: float
    entradas_ledger: float
    salidas_ledger: float
    reversos_ledger: float
    saldo_teorico: float
    cantidad_restante: float
    diferencia: float
    cobertura: EstadoCoberturaLedger
    primera_operacion_ledger: datetime | date | None
    incidencias: list[str] = field(default_factory=list)
    anulado: bool = False


@dataclass
class ResumenReconciliacion:
    frontera_activacion_iso: str | None
    frontera_fuente: str
    schema_version: int
    modo_saldo: str
    tolerancia: float
    por_lote: list[ReconciliacionLote]
    por_producto: dict[str, list[str]]  # producto_id → lote_ids
    inconsistencias_posteriores: list[str]
    conteo_cobertura: dict[str, int]


def _casi_igual(a: float, b: float, tol: float) -> bool:
    return abs(float(a) - float(b)) <= tol + 1e-12


def clasificar_cobertura_lote(
    data: AppData,
    lote: LoteStock,
    *,
    tol: float | None = None,
) -> ReconciliacionLote:
    """Clasifica un lote. No modifica datos."""
    eps = tolerancia_cantidad(data) if tol is None else tol
    movs = _movimientos_lote(data, lote.id)
    entradas = total_entradas_ledger(data, lote.id)
    salidas = total_salidas_ledger(data, lote.id)
    reversos = total_reversos_ledger(data, lote.id)
    teorico = entradas - salidas
    restante = float(lote.cantidad_restante)
    diff = teorico - restante
    primera = primera_operacion_ledger(data, lote.id)
    incidencias: list[str] = []
    anulado = bool(getattr(lote, "anulado", False))

    if not movs:
        if _casi_igual(restante, 0.0, eps) and _casi_igual(
            float(lote.cantidad), 0.0, eps
        ):
            cob = EstadoCoberturaLedger.SIN_MOVIMIENTOS
        elif _casi_igual(restante, 0.0, eps) and anulado:
            cob = EstadoCoberturaLedger.SIN_MOVIMIENTOS
            incidencias.append(
                "Lote anulado sin movimientos de ledger (histórico o pre-activación)."
            )
        else:
            cob = EstadoCoberturaLedger.HISTORICO_SIN_LEDGER
            incidencias.append(
                "Lote sin movimientos de ledger: histórico pre-ledger "
                "(no es error automático)."
            )
        return ReconciliacionLote(
            lote_id=lote.id,
            producto_id=lote.producto_id,
            cantidad_original=float(lote.cantidad),
            entradas_ledger=entradas,
            salidas_ledger=salidas,
            reversos_ledger=reversos,
            saldo_teorico=teorico,
            cantidad_restante=restante,
            diferencia=diff,
            cobertura=cob,
            primera_operacion_ledger=primera,
            incidencias=incidencias,
            anulado=anulado,
        )

    coincide = _casi_igual(teorico, restante, eps)
    # ¿Hay evidencia de operaciones posteriores a la frontera?
    post = False
    for m in movs:
        flag = movimiento_es_posterior_activacion(
            data, m.creado_en, fecha_fallback=m.fecha
        )
        if flag is True:
            post = True
            break

    frontera = frontera_activacion(data)
    if not coincide and post:
        cob = EstadoCoberturaLedger.INCONSISTENCIA_POSTERIOR_ACTIVACION
        incidencias.append(
            f"Diferencia {diff:g} entre saldo ledger ({teorico:g}) y "
            f"cantidad_restante ({restante:g}) con movimientos posteriores "
            f"a la activación"
            + (f" ({frontera.isoformat()})" if frontera else "")
            + "."
        )
    elif coincide and _casi_igual(entradas, float(lote.cantidad), eps * 10 + 1e-6):
        # Entradas explican la cantidad original (cobertura completa típica).
        cob = EstadoCoberturaLedger.COBERTURA_COMPLETA
    elif coincide:
        # Saldo cuadra pero el lote puede tener historia previa no reflejada
        # en cantidad original vs entradas (p.ej. entrada parcial).
        if entradas + 1e-9 < float(lote.cantidad) and not _casi_igual(
            entradas, 0.0, eps
        ):
            cob = EstadoCoberturaLedger.COBERTURA_PARCIAL
            incidencias.append(
                "Saldo cuadra, pero las entradas ledger no cubren la "
                "cantidad original del lote (cobertura parcial)."
            )
        else:
            cob = EstadoCoberturaLedger.COBERTURA_COMPLETA
    else:
        # Diferencia sin (o sin poder demostrar) operaciones post-activación.
        cob = EstadoCoberturaLedger.COBERTURA_PARCIAL
        incidencias.append(
            f"Diferencia {diff:g} interpretada como cobertura parcial "
            f"/ histórico pre-ledger (no inconsistencia post-activación)."
        )

    return ReconciliacionLote(
        lote_id=lote.id,
        producto_id=lote.producto_id,
        cantidad_original=float(lote.cantidad),
        entradas_ledger=entradas,
        salidas_ledger=salidas,
        reversos_ledger=reversos,
        saldo_teorico=round(teorico, 6),
        cantidad_restante=restante,
        diferencia=round(diff, 6),
        cobertura=cob,
        primera_operacion_ledger=primera,
        incidencias=incidencias,
        anulado=anulado,
    )


def reconciliar_lote(data: AppData, lote_id: str) -> ReconciliacionLote | None:
    lote = next((l for l in data.lotes if l.id == lote_id), None)
    if lote is None:
        return None
    return clasificar_cobertura_lote(data, lote)


def reconciliar_producto(data: AppData, producto_id: str) -> list[ReconciliacionLote]:
    return [
        clasificar_cobertura_lote(data, lote)
        for lote in data.lotes
        if lote.producto_id == producto_id
    ]


def reconciliacion_reforzada(
    data: AppData,
    *,
    fijar_frontera_si_falta: bool = True,
) -> ResumenReconciliacion:
    """Ejecuta reconciliación completa. Opcionalmente fija frontera una vez."""
    if fijar_frontera_si_falta:
        frontera, fuente = asegurar_frontera_activacion(data, persist_mutate=True)
    else:
        frontera = frontera_activacion(data)
        fuente = "explicit" if frontera else "unset"

    por_lote = [clasificar_cobertura_lote(data, lote) for lote in data.lotes]
    por_producto: dict[str, list[str]] = {}
    for r in por_lote:
        por_producto.setdefault(r.producto_id, []).append(r.lote_id)

    inconsistencias = [
        f"{r.lote_id}: {';'.join(r.incidencias) or r.cobertura.value}"
        for r in por_lote
        if r.cobertura == EstadoCoberturaLedger.INCONSISTENCIA_POSTERIOR_ACTIVACION
    ]
    conteo: dict[str, int] = {e.value: 0 for e in EstadoCoberturaLedger}
    for r in por_lote:
        conteo[r.cobertura.value] = conteo.get(r.cobertura.value, 0) + 1

    cfg = data.configuracion
    frontera_iso = (
        getattr(cfg, "ledger_activation_iso", None)
        if cfg is not None
        else (frontera.isoformat() if frontera else None)
    )

    return ResumenReconciliacion(
        frontera_activacion_iso=frontera_iso,
        frontera_fuente=fuente,
        schema_version=ledger_schema_version(data),
        modo_saldo=ledger_balance_mode(data),
        tolerancia=tolerancia_cantidad(data),
        por_lote=por_lote,
        por_producto=por_producto,
        inconsistencias_posteriores=inconsistencias,
        conteo_cobertura=conteo,
    )


def hay_inconsistencias_posteriores_criticas(data: AppData) -> bool:
    resumen = reconciliacion_reforzada(data, fijar_frontera_si_falta=False)
    return bool(resumen.inconsistencias_posteriores)
