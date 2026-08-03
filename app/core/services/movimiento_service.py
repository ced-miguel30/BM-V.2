"""Ledger de movimientos de inventario — Fase 7A.1 (modo espejo).

Fuente de verdad del stock: ``LoteStock.cantidad_restante``.
Este módulo no altera lotes, FIFO ni operaciones productivas.
Creación: API interna explícita (tests / preparación). Dual-write = 7A.2+.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from app.core.application.context import AppContext
from app.core.application.id_generator import next_id
from app.core.models import AppData, MovimientoInventario
from app.core.models.enums import (
    DIRECCION_POR_TIPO_MOVIMIENTO,
    DIRECCION_MOVIMIENTO_VALORES,
    DireccionMovimiento,
    TIPO_MOVIMIENTO_VALORES,
    TipoMovimiento,
)
from app.core.storage.session_store import get_data, persist_data

NOTA_LEDGER_PARCIAL = (
    "Ledger parcial: reconciliación no aplicable como fuente de verdad."
)

NOTA_SIN_BACKFILL = (
    "La ausencia de movimientos históricos no es error en 7A.1. "
    "Solo las operaciones nuevas conectadas desde 7A.2 en adelante "
    "estarán obligadas a generar ledger."
)

_EPS_COSTE = 1e-6


@dataclass
class ResultadoMovimiento:
    ok: bool
    mensaje: str
    movimiento: MovimientoInventario | None = None
    duplicado: bool = False


@dataclass
class ComparacionLoteLedger:
    lote_id: str
    producto_id: str
    entradas: float
    salidas: float
    saldo_teorico_ledger: float
    cantidad_restante: float
    diferencia: float
    nota: str = NOTA_LEDGER_PARCIAL


class _CompatSessionUow:
    def get_data(self) -> AppData:
        return get_data()

    def commit(self, data: AppData | None = None) -> AppData:
        return persist_data(data if data is not None else get_data())


def _ctx(ctx: AppContext | None = None) -> AppContext:
    if ctx is not None:
        return ctx
    from app.core.application.actor import actor_desde_appdata
    from app.core.application.clock import SystemClock

    uow = _CompatSessionUow()
    return AppContext(
        uow=uow,
        actor=actor_desde_appdata(uow.get_data()),
        clock=SystemClock(),
    )


def _enum_value(val: Any) -> str:
    if hasattr(val, "value"):
        return str(val.value)
    return str(val or "")


def _parse_tipo(raw: Any) -> TipoMovimiento | str:
    if isinstance(raw, TipoMovimiento):
        return raw
    s = str(raw or "").strip()
    try:
        return TipoMovimiento(s)
    except ValueError:
        return s


def _parse_direccion(raw: Any) -> DireccionMovimiento | str:
    if isinstance(raw, DireccionMovimiento):
        return raw
    s = str(raw or "").strip()
    try:
        return DireccionMovimiento(s)
    except ValueError:
        return s


def direccion_esperada(tipo: TipoMovimiento | str) -> DireccionMovimiento | None:
    t = _parse_tipo(tipo)
    if isinstance(t, TipoMovimiento):
        return DIRECCION_POR_TIPO_MOVIMIENTO[t]
    return None


def construir_idempotency_key(
    origen_tipo: str,
    origen_id: str,
    origen_linea_id: str | None,
    lote_id: str,
    tipo: TipoMovimiento | str,
) -> str:
    """Clave estable: origen_tipo:origen_id:linea:lote:tipo."""
    linea = (origen_linea_id or "").strip()
    return (
        f"{(origen_tipo or '').strip()}:"
        f"{(origen_id or '').strip()}:"
        f"{linea}:"
        f"{(lote_id or '').strip()}:"
        f"{_enum_value(tipo)}"
    )


def listar_movimientos(data: AppData) -> list[MovimientoInventario]:
    return list(getattr(data, "movimientos", None) or [])


def buscar_por_id(data: AppData, movimiento_id: str) -> MovimientoInventario | None:
    return next((m for m in listar_movimientos(data) if m.id == movimiento_id), None)


def buscar_por_producto(data: AppData, producto_id: str) -> list[MovimientoInventario]:
    return [m for m in listar_movimientos(data) if m.producto_id == producto_id]


def buscar_por_lote(data: AppData, lote_id: str) -> list[MovimientoInventario]:
    return [m for m in listar_movimientos(data) if m.lote_id == lote_id]


def buscar_por_origen(
    data: AppData,
    origen_tipo: str,
    origen_id: str,
    origen_linea_id: str | None = None,
) -> list[MovimientoInventario]:
    out: list[MovimientoInventario] = []
    for m in listar_movimientos(data):
        if m.origen_tipo != origen_tipo or m.origen_id != origen_id:
            continue
        if origen_linea_id is not None and (m.origen_linea_id or "") != origen_linea_id:
            continue
        out.append(m)
    return out


def comprobar_idempotencia(
    data: AppData, idempotency_key: str | None
) -> MovimientoInventario | None:
    if not idempotency_key:
        return None
    return next(
        (
            m
            for m in listar_movimientos(data)
            if m.idempotency_key == idempotency_key
        ),
        None,
    )


def validar_movimiento(
    data: AppData,
    *,
    producto_id: str,
    lote_id: str,
    tipo: TipoMovimiento | str,
    direccion: DireccionMovimiento | str,
    cantidad: float,
    origen_tipo: str,
    origen_id: str,
    movimiento_id: str | None = None,
    movimiento_revertido_id: str | None = None,
    idempotency_key: str | None = None,
) -> list[str]:
    """Devuelve lista de errores; vacía si es válido."""
    errores: list[str] = []

    try:
        cant = float(cantidad)
    except (TypeError, ValueError):
        errores.append("cantidad debe ser un número positivo")
        cant = 0.0
    if cant <= 0:
        errores.append("cantidad debe ser mayor que cero")

    tipo_p = _parse_tipo(tipo)
    if not isinstance(tipo_p, TipoMovimiento):
        errores.append(f"tipo de movimiento no válido: {tipo_p!r}")

    dir_p = _parse_direccion(direccion)
    if not isinstance(dir_p, DireccionMovimiento):
        errores.append(f"dirección no válida: {dir_p!r}")

    if isinstance(tipo_p, TipoMovimiento) and isinstance(dir_p, DireccionMovimiento):
        esperada = DIRECCION_POR_TIPO_MOVIMIENTO[tipo_p]
        if dir_p != esperada:
            errores.append(
                f"tipo {tipo_p.value} exige dirección {esperada.value}, "
                f"recibido {dir_p.value}"
            )

    if not (origen_tipo or "").strip():
        errores.append("origen_tipo no puede estar vacío")
    if not (origen_id or "").strip():
        errores.append("origen_id no puede estar vacío")

    producto = next((p for p in data.productos if p.id == producto_id), None)
    if producto is None:
        errores.append(f"producto inexistente: {producto_id}")

    lote = next((l for l in data.lotes if l.id == lote_id), None)
    if lote is None:
        errores.append(f"lote inexistente: {lote_id}")
    elif producto is not None and lote.producto_id != producto_id:
        errores.append(
            f"lote {lote_id} pertenece a producto {lote.producto_id}, "
            f"no a {producto_id}"
        )

    if movimiento_revertido_id:
        if movimiento_id and movimiento_revertido_id == movimiento_id:
            errores.append("movimiento de reversión no puede autorreferenciarse")
        orig = buscar_por_id(data, movimiento_revertido_id)
        if orig is None:
            errores.append(
                f"movimiento_revertido_id inexistente: {movimiento_revertido_id}"
            )

    if idempotency_key:
        existente = comprobar_idempotencia(data, idempotency_key)
        if existente is not None and existente.id != movimiento_id:
            errores.append(f"idempotency_key duplicada: {idempotency_key}")

    if movimiento_id:
        otro = buscar_por_id(data, movimiento_id)
        if otro is not None:
            errores.append(f"id de movimiento duplicado: {movimiento_id}")

    return errores


def crear_movimiento(
    *,
    producto_id: str,
    lote_id: str,
    tipo: TipoMovimiento | str,
    direccion: DireccionMovimiento | str,
    cantidad: float,
    fecha: date,
    origen_tipo: str,
    origen_id: str,
    hora: time | None = None,
    origen_linea_id: str | None = None,
    movimiento_revertido_id: str | None = None,
    usuario_id: str | None = None,
    idempotency_key: str | None = None,
    coste_unitario_snapshot: float | None = None,
    coste_total_snapshot: float | None = None,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoMovimiento:
    """API interna explícita. No altera ``cantidad_restante`` ni FIFO."""
    c = _ctx(ctx)
    data = c.uow.get_data()
    if not hasattr(data, "movimientos") or data.movimientos is None:
        data.movimientos = []

    tipo_p = _parse_tipo(tipo)
    dir_p = _parse_direccion(direccion)

    key = idempotency_key
    if not key:
        key = construir_idempotency_key(
            origen_tipo, origen_id, origen_linea_id, lote_id, tipo_p
        )

    existente = comprobar_idempotencia(data, key)
    if existente is not None:
        return ResultadoMovimiento(
            ok=False,
            mensaje=f"Movimiento duplicado (idempotency_key={key})",
            movimiento=existente,
            duplicado=True,
        )

    errores = validar_movimiento(
        data,
        producto_id=producto_id,
        lote_id=lote_id,
        tipo=tipo_p,
        direccion=dir_p,
        cantidad=cantidad,
        origen_tipo=origen_tipo,
        origen_id=origen_id,
        movimiento_revertido_id=movimiento_revertido_id,
        idempotency_key=key,
    )
    if errores:
        return ResultadoMovimiento(ok=False, mensaje="; ".join(errores))

    mov_id = next_id("mov", [m.id for m in data.movimientos])
    actor_id = usuario_id
    if actor_id is None and getattr(c, "actor", None) is not None:
        actor_id = getattr(c.actor, "id", None) or None

    creado: datetime | None = None
    if getattr(c, "clock", None) is not None:
        try:
            creado = c.clock.now()
        except Exception:  # noqa: BLE001
            creado = datetime.now()
    else:
        creado = datetime.now()

    mov = MovimientoInventario(
        id=mov_id,
        producto_id=producto_id,
        lote_id=lote_id,
        tipo=tipo_p,
        direccion=dir_p,
        cantidad=float(cantidad),
        fecha=fecha,
        hora=hora,
        origen_tipo=(origen_tipo or "").strip(),
        origen_id=(origen_id or "").strip(),
        origen_linea_id=origen_linea_id,
        movimiento_revertido_id=movimiento_revertido_id,
        usuario_id=actor_id,
        idempotency_key=key,
        coste_unitario_snapshot=coste_unitario_snapshot,
        coste_total_snapshot=coste_total_snapshot,
        creado_en=creado,
    )
    data.movimientos.append(mov)
    if commit:
        c.uow.commit(data)
    return ResultadoMovimiento(
        ok=True,
        mensaje=f"Movimiento {mov_id} creado (ledger espejo; stock no alterado)",
        movimiento=mov,
    )


# --- Consultas de reconciliación (solo lectura; no corrigen stock) ---


def total_entradas_por_lote(data: AppData, lote_id: str) -> float:
    return sum(
        float(m.cantidad)
        for m in buscar_por_lote(data, lote_id)
        if _enum_value(m.direccion) == DireccionMovimiento.ENTRADA.value
    )


def total_salidas_por_lote(data: AppData, lote_id: str) -> float:
    return sum(
        float(m.cantidad)
        for m in buscar_por_lote(data, lote_id)
        if _enum_value(m.direccion) == DireccionMovimiento.SALIDA.value
    )


def saldo_teorico_ledger_por_lote(data: AppData, lote_id: str) -> float:
    return total_entradas_por_lote(data, lote_id) - total_salidas_por_lote(
        data, lote_id
    )


def comparar_ledger_vs_lote(
    data: AppData, lote_id: str
) -> ComparacionLoteLedger | None:
    lote = next((l for l in data.lotes if l.id == lote_id), None)
    if lote is None:
        return None
    entradas = total_entradas_por_lote(data, lote_id)
    salidas = total_salidas_por_lote(data, lote_id)
    teorico = entradas - salidas
    restante = float(lote.cantidad_restante)
    return ComparacionLoteLedger(
        lote_id=lote_id,
        producto_id=lote.producto_id,
        entradas=entradas,
        salidas=salidas,
        saldo_teorico_ledger=teorico,
        cantidad_restante=restante,
        diferencia=teorico - restante,
        nota=NOTA_LEDGER_PARCIAL,
    )


def reconciliacion_informativa(data: AppData) -> list[ComparacionLoteLedger]:
    """Comparación diagnóstica por lote. No modifica datos."""
    return [
        c
        for lote in data.lotes
        if (c := comparar_ledger_vs_lote(data, lote.id)) is not None
    ]


def incidencias_movimientos(data: AppData) -> list[str]:
    """Diagnóstico no destructivo del ledger (7A.1)."""
    incidencias: list[str] = []
    movimientos = listar_movimientos(data)
    producto_ids = {p.id for p in data.productos}
    lotes_map = {l.id: l for l in data.lotes}

    ids_vistos: set[str] = set()
    keys_vistas: dict[str, str] = {}

    for m in movimientos:
        if m.id in ids_vistos:
            incidencias.append(f"Movimiento id duplicado: {m.id}")
        else:
            ids_vistos.add(m.id)

        if m.idempotency_key:
            prev = keys_vistas.get(m.idempotency_key)
            if prev and prev != m.id:
                incidencias.append(
                    f"idempotency_key duplicada: {m.idempotency_key} "
                    f"({prev}, {m.id})"
                )
            else:
                keys_vistas[m.idempotency_key] = m.id

        if m.producto_id not in producto_ids:
            incidencias.append(
                f"Movimiento {m.id}: producto inexistente {m.producto_id}"
            )

        lote = lotes_map.get(m.lote_id)
        if lote is None:
            incidencias.append(f"Movimiento {m.id}: lote inexistente {m.lote_id}")
        elif lote.producto_id != m.producto_id:
            incidencias.append(
                f"Movimiento {m.id}: lote {m.lote_id} pertenece a "
                f"{lote.producto_id}, no a {m.producto_id}"
            )

        try:
            cant = float(m.cantidad)
        except (TypeError, ValueError):
            cant = 0.0
        if cant <= 0:
            incidencias.append(
                f"Movimiento {m.id}: cantidad no positiva ({m.cantidad})"
            )

        tipo_p = _parse_tipo(m.tipo)
        dir_p = _parse_direccion(m.direccion)
        if not isinstance(tipo_p, TipoMovimiento):
            incidencias.append(
                f"Movimiento {m.id}: tipo desconocido {m.tipo!r} "
                "(no convertido)"
            )
        if not isinstance(dir_p, DireccionMovimiento):
            incidencias.append(
                f"Movimiento {m.id}: dirección desconocida {m.direccion!r} "
                "(no convertida)"
            )
        if isinstance(tipo_p, TipoMovimiento) and isinstance(
            dir_p, DireccionMovimiento
        ):
            esperada = DIRECCION_POR_TIPO_MOVIMIENTO[tipo_p]
            if dir_p != esperada:
                incidencias.append(
                    f"Movimiento {m.id}: tipo {tipo_p.value} incompatible "
                    f"con dirección {dir_p.value}"
                )

        if not (m.origen_tipo or "").strip() or not (m.origen_id or "").strip():
            incidencias.append(f"Movimiento {m.id}: origen vacío")

        if m.movimiento_revertido_id:
            if m.movimiento_revertido_id == m.id:
                incidencias.append(f"Movimiento {m.id}: autoreferencia")
            elif buscar_por_id(data, m.movimiento_revertido_id) is None:
                incidencias.append(
                    f"Movimiento {m.id}: reverso con original inexistente "
                    f"{m.movimiento_revertido_id}"
                )

        if (
            m.coste_unitario_snapshot is not None
            and m.coste_total_snapshot is not None
            and cant > 0
        ):
            esperado = float(m.coste_unitario_snapshot) * cant
            if abs(esperado - float(m.coste_total_snapshot)) > _EPS_COSTE:
                incidencias.append(
                    f"Movimiento {m.id}: coste total incoherente "
                    f"(unitario×cant={esperado:g} ≠ total="
                    f"{m.coste_total_snapshot:g})"
                )

    if movimientos:
        incidencias.append(
            f"Informativo: {len(movimientos)} movimiento(s) presentes en ledger "
            "antes de la activación operativa completa (7A.2+). "
            + NOTA_SIN_BACKFILL
        )

    return incidencias


# API pública del servicio: sin edición ni borrado.
__all__ = [
    "ComparacionLoteLedger",
    "NOTA_LEDGER_PARCIAL",
    "NOTA_SIN_BACKFILL",
    "ResultadoMovimiento",
    "buscar_por_id",
    "buscar_por_lote",
    "buscar_por_origen",
    "buscar_por_producto",
    "comparar_ledger_vs_lote",
    "comprobar_idempotencia",
    "construir_idempotency_key",
    "crear_movimiento",
    "direccion_esperada",
    "incidencias_movimientos",
    "listar_movimientos",
    "reconciliacion_informativa",
    "saldo_teorico_ledger_por_lote",
    "total_entradas_por_lote",
    "total_salidas_por_lote",
    "validar_movimiento",
]
