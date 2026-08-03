"""Stock derivado por ubicación desde el ledger (Fase 7B.3).

No inventa ubicaciones históricas. ``Producto.ubicacion_ids`` = permitidas,
no cantidades. Estado ``sin_ubicacion_historica`` = ausencia controlada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.models import AppData, MovimientoInventario
from app.core.models.enums import DireccionMovimiento
from app.core.services.ledger_config import tolerancia_cantidad
from app.core.services.ledger_reconciliacion_service import saldo_teorico_ledger

# Marcador lógico (no es ID de catálogo).
SIN_UBICACION_HISTORICA = "sin_ubicacion_historica"


class CoberturaUbicacion(str, Enum):
    SIN_UBICACION_HISTORICA = "sin_ubicacion_historica"
    COBERTURA_PARCIAL = "cobertura_parcial"
    COBERTURA_COMPLETA = "cobertura_completa"
    SIN_MOVIMIENTOS = "sin_movimientos"


def _enum_value(val: Any) -> str:
    return val.value if hasattr(val, "value") else str(val)


def _es_traslado(m: MovimientoInventario) -> bool:
    return _enum_value(m.tipo) == "traslado"


@dataclass
class SaldoUbicacion:
    ubicacion_id: str  # catálogo o SIN_UBICACION_HISTORICA
    entradas: float
    salidas: float
    saldo: float


@dataclass
class SaldoUbicacionLote:
    lote_id: str
    producto_id: str
    por_ubicacion: dict[str, SaldoUbicacion]
    saldo_total_ubicaciones: float
    saldo_ledger_lote: float
    cobertura: CoberturaUbicacion
    suma_cuadra_con_ledger: bool
    incidencias: list[str] = field(default_factory=list)


def _delta_ubicaciones(m: MovimientoInventario) -> list[tuple[str, float]]:
    """Lista (ubicacion_key, delta_firmado) para un movimiento."""
    qty = float(m.cantidad)
    tipo = _enum_value(m.tipo)
    origen = m.ubicacion_origen_id
    destino = m.ubicacion_destino_id

    if tipo == "traslado":
        out: list[tuple[str, float]] = []
        if origen:
            out.append((origen, -qty))
        else:
            out.append((SIN_UBICACION_HISTORICA, -qty))
        if destino:
            out.append((destino, qty))
        else:
            out.append((SIN_UBICACION_HISTORICA, qty))
        return out

    dir_v = _enum_value(m.direccion)
    if dir_v == DireccionMovimiento.ENTRADA.value:
        key = destino or SIN_UBICACION_HISTORICA
        return [(key, qty)]
    if dir_v == DireccionMovimiento.SALIDA.value:
        key = origen or SIN_UBICACION_HISTORICA
        return [(key, -qty)]
    return []


def saldos_por_ubicacion_lote(
    data: AppData, lote_id: str
) -> SaldoUbicacionLote:
    lote = next((l for l in data.lotes if l.id == lote_id), None)
    producto_id = lote.producto_id if lote else ""
    movs = [
        m
        for m in (getattr(data, "movimientos", None) or [])
        if m.lote_id == lote_id
    ]

    acc: dict[str, list[float]] = {}  # id → [entradas, salidas]
    if not movs:
        ledger = saldo_teorico_ledger(data, lote_id) if lote else 0.0
        return SaldoUbicacionLote(
            lote_id=lote_id,
            producto_id=producto_id,
            por_ubicacion={},
            saldo_total_ubicaciones=0.0,
            saldo_ledger_lote=ledger,
            cobertura=CoberturaUbicacion.SIN_MOVIMIENTOS,
            suma_cuadra_con_ledger=_casi(0.0, ledger, data),
            incidencias=[],
        )

    tiene_ubicacion = False
    tiene_sin = False
    for m in movs:
        for key, delta in _delta_ubicaciones(m):
            if key == SIN_UBICACION_HISTORICA:
                tiene_sin = True
            else:
                tiene_ubicacion = True
            bucket = acc.setdefault(key, [0.0, 0.0])
            if delta >= 0:
                bucket[0] += delta
            else:
                bucket[1] += -delta

    por_ubi: dict[str, SaldoUbicacion] = {}
    total = 0.0
    for key, (ent, sal) in acc.items():
        saldo = ent - sal
        por_ubi[key] = SaldoUbicacion(
            ubicacion_id=key, entradas=ent, salidas=sal, saldo=saldo
        )
        total += saldo

    ledger = saldo_teorico_ledger(data, lote_id)
    # Traslados no afectan ledger total; la suma de ubicaciones debe = ledger
    # incluyendo el cubo sin_ubicacion_historica.
    cuadra = _casi(total, ledger, data)
    incidencias: list[str] = []
    if not cuadra:
        incidencias.append(
            f"Suma ubicaciones ({total:g}) ≠ saldo ledger lote ({ledger:g})"
        )

    if not tiene_ubicacion and tiene_sin:
        cob = CoberturaUbicacion.SIN_UBICACION_HISTORICA
    elif tiene_ubicacion and tiene_sin:
        cob = CoberturaUbicacion.COBERTURA_PARCIAL
    elif tiene_ubicacion and cuadra:
        cob = CoberturaUbicacion.COBERTURA_COMPLETA
    elif tiene_ubicacion:
        cob = CoberturaUbicacion.COBERTURA_PARCIAL
    else:
        cob = CoberturaUbicacion.SIN_UBICACION_HISTORICA

    return SaldoUbicacionLote(
        lote_id=lote_id,
        producto_id=producto_id,
        por_ubicacion=por_ubi,
        saldo_total_ubicaciones=round(total, 6),
        saldo_ledger_lote=ledger,
        cobertura=cob,
        suma_cuadra_con_ledger=cuadra,
        incidencias=incidencias,
    )


def _casi(a: float, b: float, data: AppData) -> bool:
    return abs(float(a) - float(b)) <= tolerancia_cantidad(data) + 1e-12


def saldo_en_ubicacion(
    data: AppData, lote_id: str, ubicacion_id: str
) -> float:
    info = saldos_por_ubicacion_lote(data, lote_id)
    u = info.por_ubicacion.get(ubicacion_id)
    return float(u.saldo) if u else 0.0


def ubicacion_preferida_lote(data: AppData, lote_id: str) -> str | None:
    """Ubicación de catálogo con mayor saldo (>0); None si solo histórico."""
    info = saldos_por_ubicacion_lote(data, lote_id)
    candidatas = [
        (uid, s.saldo)
        for uid, s in info.por_ubicacion.items()
        if uid != SIN_UBICACION_HISTORICA and s.saldo > 1e-9
    ]
    if not candidatas:
        return None
    candidatas.sort(key=lambda x: (-x[1], x[0]))
    return candidatas[0][0]


def lote_tiene_cobertura_ubicacion(data: AppData, lote_id: str) -> bool:
    info = saldos_por_ubicacion_lote(data, lote_id)
    return info.cobertura in (
        CoberturaUbicacion.COBERTURA_COMPLETA,
        CoberturaUbicacion.COBERTURA_PARCIAL,
    ) and any(
        uid != SIN_UBICACION_HISTORICA and s.saldo > 1e-9
        for uid, s in info.por_ubicacion.items()
    )


def saldos_por_ubicacion_producto(
    data: AppData, producto_id: str
) -> dict[str, float]:
    """Agrega saldos de ubicación de todos los lotes no anulados del producto."""
    totales: dict[str, float] = {}
    for lote in data.lotes:
        if lote.producto_id != producto_id:
            continue
        if getattr(lote, "anulado", False):
            continue
        info = saldos_por_ubicacion_lote(data, lote.id)
        for uid, s in info.por_ubicacion.items():
            totales[uid] = totales.get(uid, 0.0) + s.saldo
    return {k: round(v, 6) for k, v in totales.items()}


def validar_ubicacion_catalogo(data: AppData, ubicacion_id: str | None) -> str | None:
    if not ubicacion_id:
        return None
    if ubicacion_id == SIN_UBICACION_HISTORICA:
        return "sin_ubicacion_historica no es una ubicación de catálogo"
    ids = {u.id for u in getattr(data, "ubicaciones", []) or []}
    if ubicacion_id not in ids:
        return f"ubicación inexistente: {ubicacion_id}"
    return None
