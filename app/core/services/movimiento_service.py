"""Ledger de movimientos de inventario — Fase 7A.1 (modo espejo).

Fuente de verdad del stock: ``LoteStock.cantidad_restante``.
Este módulo no altera lotes, FIFO ni operaciones productivas.
Creación: API interna explícita (tests / preparación). Dual-write = 7A.2+.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    ubicacion_origen_id: str | None = None,
    ubicacion_destino_id: str | None = None,
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
        ubicacion_origen_id=ubicacion_origen_id,
        ubicacion_destino_id=ubicacion_destino_id,
    )
    data.movimientos.append(mov)
    if commit:
        c.uow.commit(data)
    return ResultadoMovimiento(
        ok=True,
        mensaje=f"Movimiento {mov_id} creado (ledger espejo; stock no alterado)",
        movimiento=mov,
    )


# --- Dual-write 7A.2 (espejo; no muta cantidad_restante por sí mismo) ---

ORIGEN_TIPO_LOTE = "lote"
ORIGEN_TIPO_AJUSTE = "ajuste"
ORIGEN_TIPO_MERMA = "merma"
ORIGEN_TIPO_ANULACION_MERMA = "anulacion_merma"
ORIGEN_TIPO_ANULACION_MERMA_HISTORICA = "anulacion_merma_historica"
ORIGEN_TIPO_DESAYUNO = "desayuno"
ORIGEN_TIPO_REGISTRO_SERVICIO = "registro_servicio"
ORIGEN_TIPO_ANULACION_REGISTRO = "anulacion_registro"
ORIGEN_TIPO_ANULACION_REGISTRO_HISTORICA = "anulacion_registro_historica"
ORIGEN_TIPO_ANULACION_COMPRA = "anulacion_compra"
ORIGEN_TIPO_ANULACION_COMPRA_HISTORICA = "anulacion_compra_historica"

ORIGENES_CONSUMO_REGISTRO = frozenset(
    {ORIGEN_TIPO_DESAYUNO, ORIGEN_TIPO_REGISTRO_SERVICIO}
)


def origen_linea_id_merma(indice: int) -> str:
    """Identificador estable de línea sin campo ``id`` en ``LineaMerma``.

    Índice 0-based en ``RegistroMerma.lineas``. Las líneas no se reordenan
    tras persistir (modelo append-only). No se añade ID nuevo al modelo.
    """
    return f"ln{int(indice):02d}"


def espejo_entrada_lote(
    *,
    producto_id: str,
    lote_id: str,
    cantidad: float,
    fecha: date,
    precio_total: float | None = None,
    hora: time | None = None,
    usuario_id: str | None = None,
    ubicacion_destino_id: str | None = None,
    ctx: AppContext | None = None,
    commit: bool = False,
) -> ResultadoMovimiento:
    """Escribe ``entrada_compra`` al registrar un lote. No altera stock."""
    coste_total = round(float(precio_total), 2) if precio_total is not None else None
    coste_unitario = None
    if coste_total is not None and float(cantidad) > 0:
        coste_unitario = round(coste_total / float(cantidad), 6)
    return crear_movimiento(
        producto_id=producto_id,
        lote_id=lote_id,
        tipo=TipoMovimiento.ENTRADA_COMPRA,
        direccion=DireccionMovimiento.ENTRADA,
        cantidad=cantidad,
        fecha=fecha,
        hora=hora,
        origen_tipo=ORIGEN_TIPO_LOTE,
        origen_id=lote_id,
        origen_linea_id=None,
        usuario_id=usuario_id,
        coste_unitario_snapshot=coste_unitario,
        coste_total_snapshot=coste_total,
        ubicacion_destino_id=ubicacion_destino_id,
        ctx=ctx,
        commit=commit,
    )


def espejo_ajuste_linea(
    *,
    producto_id: str,
    lote_id: str,
    delta: float,
    fecha: date,
    ajuste_id: str,
    origen_linea_id: str | None = None,
    hora: time | None = None,
    usuario_id: str | None = None,
    ubicacion_origen_id: str | None = None,
    ubicacion_destino_id: str | None = None,
    ctx: AppContext | None = None,
    commit: bool = False,
) -> ResultadoMovimiento:
    """Escribe ``ajuste_entrada`` o ``ajuste_salida`` según el signo del delta."""
    try:
        d = float(delta)
    except (TypeError, ValueError):
        return ResultadoMovimiento(ok=False, mensaje="delta de ajuste no numérico")
    if abs(d) < 1e-9:
        return ResultadoMovimiento(ok=False, mensaje="delta de ajuste nulo")
    if d > 0:
        tipo = TipoMovimiento.AJUSTE_ENTRADA
        direccion = DireccionMovimiento.ENTRADA
        u_orig, u_dest = None, ubicacion_destino_id
    else:
        tipo = TipoMovimiento.AJUSTE_SALIDA
        direccion = DireccionMovimiento.SALIDA
        u_orig, u_dest = ubicacion_origen_id, None
    linea = origen_linea_id if origen_linea_id is not None else lote_id
    return crear_movimiento(
        producto_id=producto_id,
        lote_id=lote_id,
        tipo=tipo,
        direccion=direccion,
        cantidad=abs(d),
        fecha=fecha,
        hora=hora,
        origen_tipo=ORIGEN_TIPO_AJUSTE,
        origen_id=ajuste_id,
        origen_linea_id=linea,
        usuario_id=usuario_id,
        ubicacion_origen_id=u_orig,
        ubicacion_destino_id=u_dest,
        ctx=ctx,
        commit=commit,
    )


def espejo_merma_linea(
    *,
    producto_id: str,
    lote_id: str,
    cantidad: float,
    fecha: date,
    merma_id: str,
    indice_linea: int,
    coste_total: float | None = None,
    hora: time | None = None,
    usuario_id: str | None = None,
    ubicacion_origen_id: str | None = None,
    ctx: AppContext | None = None,
    commit: bool = False,
) -> ResultadoMovimiento:
    """Escribe ``merma`` (salida) por línea de registro. No altera stock."""
    coste_unitario = None
    coste_tot = None
    if coste_total is not None:
        coste_tot = round(float(coste_total), 2)
        if float(cantidad) > 0:
            coste_unitario = round(coste_tot / float(cantidad), 6)
    return crear_movimiento(
        producto_id=producto_id,
        lote_id=lote_id,
        tipo=TipoMovimiento.MERMA,
        direccion=DireccionMovimiento.SALIDA,
        cantidad=cantidad,
        fecha=fecha,
        hora=hora,
        origen_tipo=ORIGEN_TIPO_MERMA,
        origen_id=merma_id,
        origen_linea_id=origen_linea_id_merma(indice_linea),
        usuario_id=usuario_id,
        coste_unitario_snapshot=coste_unitario,
        coste_total_snapshot=coste_tot,
        ubicacion_origen_id=ubicacion_origen_id,
        ctx=ctx,
        commit=commit,
    )


def buscar_movimiento_merma_linea(
    data: AppData,
    merma_id: str,
    indice_linea: int,
) -> MovimientoInventario | None:
    linea = origen_linea_id_merma(indice_linea)
    for m in buscar_por_origen(data, ORIGEN_TIPO_MERMA, merma_id, linea):
        if _enum_value(m.tipo) == TipoMovimiento.MERMA.value:
            return m
    return None


def movimientos_reverso_de(
    data: AppData, movimiento_id: str
) -> list[MovimientoInventario]:
    return [
        m
        for m in listar_movimientos(data)
        if m.movimiento_revertido_id == movimiento_id
        and _enum_value(m.tipo) == TipoMovimiento.REVERSION_MERMA.value
    ]


def espejo_reversion_merma_linea(
    *,
    producto_id: str,
    lote_id: str,
    cantidad: float,
    fecha: date,
    merma_id: str,
    indice_linea: int,
    movimiento_original: MovimientoInventario | None,
    coste_total: float | None = None,
    hora: time | None = None,
    usuario_id: str | None = None,
    ctx: AppContext | None = None,
    commit: bool = False,
) -> ResultadoMovimiento:
    """Escribe ``reversion_merma`` (entrada). No altera stock.

    Si no hay movimiento original (merma histórica pre-ledger):
    ``movimiento_revertido_id=None`` y origen ``anulacion_merma_historica``.
    """
    if movimiento_original is not None:
        if _enum_value(movimiento_original.tipo) != TipoMovimiento.MERMA.value:
            return ResultadoMovimiento(
                ok=False,
                mensaje="El movimiento a revertir no es de tipo merma",
            )
        if movimiento_original.producto_id != producto_id:
            return ResultadoMovimiento(
                ok=False, mensaje="Producto distinto del movimiento original"
            )
        if movimiento_original.lote_id != lote_id:
            return ResultadoMovimiento(
                ok=False, mensaje="Lote distinto del movimiento original"
            )
        if abs(float(movimiento_original.cantidad) - float(cantidad)) > 1e-9:
            return ResultadoMovimiento(
                ok=False, mensaje="Cantidad distinta del movimiento original"
            )
        c = _ctx(ctx)
        ya = movimientos_reverso_de(c.uow.get_data(), movimiento_original.id)
        if ya:
            return ResultadoMovimiento(
                ok=False,
                mensaje=f"Movimiento {movimiento_original.id} ya tiene reverso",
                movimiento=ya[0],
                duplicado=True,
            )
        origen_tipo = ORIGEN_TIPO_ANULACION_MERMA
        revertido_id = movimiento_original.id
    else:
        origen_tipo = ORIGEN_TIPO_ANULACION_MERMA_HISTORICA
        revertido_id = None

    coste_unitario = None
    coste_tot = None
    if coste_total is not None:
        coste_tot = round(float(coste_total), 2)
        if float(cantidad) > 0:
            coste_unitario = round(coste_tot / float(cantidad), 6)
    elif movimiento_original is not None:
        coste_tot = movimiento_original.coste_total_snapshot
        coste_unitario = movimiento_original.coste_unitario_snapshot

    return crear_movimiento(
        producto_id=producto_id,
        lote_id=lote_id,
        tipo=TipoMovimiento.REVERSION_MERMA,
        direccion=DireccionMovimiento.ENTRADA,
        cantidad=cantidad,
        fecha=fecha,
        hora=hora,
        origen_tipo=origen_tipo,
        origen_id=merma_id,
        origen_linea_id=origen_linea_id_merma(indice_linea),
        movimiento_revertido_id=revertido_id,
        usuario_id=usuario_id,
        coste_unitario_snapshot=coste_unitario,
        coste_total_snapshot=coste_tot,
        ubicacion_origen_id=(
            getattr(movimiento_original, "ubicacion_destino_id", None)
            if movimiento_original
            else None
        ),
        ubicacion_destino_id=(
            getattr(movimiento_original, "ubicacion_origen_id", None)
            if movimiento_original
            else None
        ),
        ctx=ctx,
        commit=commit,
    )


def origen_linea_id_consumo(det_idx: int, frag_idx: int) -> str:
    """Índices estables en ``lineas_detalle`` / ``consumos_lote`` (append-only)."""
    return f"det{int(det_idx):02d}:frag{int(frag_idx):02d}"


def espejo_consumo_fragmento(
    *,
    producto_id: str,
    lote_id: str,
    cantidad: float,
    fecha: date,
    origen_tipo: str,
    registro_id: str,
    det_idx: int,
    frag_idx: int,
    coste_total: float | None = None,
    hora: time | None = None,
    usuario_id: str | None = None,
    ubicacion_origen_id: str | None = None,
    ctx: AppContext | None = None,
    commit: bool = False,
) -> ResultadoMovimiento:
    """Escribe ``consumo`` (salida) por fragmento de ``consumos_lote``."""
    coste_unitario = None
    coste_tot = None
    if coste_total is not None:
        coste_tot = round(float(coste_total), 2)
        if float(cantidad) > 0:
            coste_unitario = round(coste_tot / float(cantidad), 6)
    return crear_movimiento(
        producto_id=producto_id,
        lote_id=lote_id,
        tipo=TipoMovimiento.CONSUMO,
        direccion=DireccionMovimiento.SALIDA,
        cantidad=cantidad,
        fecha=fecha,
        hora=hora,
        origen_tipo=origen_tipo,
        origen_id=registro_id,
        origen_linea_id=origen_linea_id_consumo(det_idx, frag_idx),
        usuario_id=usuario_id,
        coste_unitario_snapshot=coste_unitario,
        coste_total_snapshot=coste_tot,
        ubicacion_origen_id=ubicacion_origen_id,
        ctx=ctx,
        commit=commit,
    )


def buscar_movimiento_consumo_fragmento(
    data: AppData,
    registro_id: str,
    det_idx: int,
    frag_idx: int,
) -> MovimientoInventario | None:
    linea = origen_linea_id_consumo(det_idx, frag_idx)
    for origen in ORIGENES_CONSUMO_REGISTRO:
        for m in buscar_por_origen(data, origen, registro_id, linea):
            if _enum_value(m.tipo) == TipoMovimiento.CONSUMO.value:
                return m
    return None


def escribir_espejos_consumo_registro(
    *,
    origen_tipo: str,
    registro_id: str,
    lineas_detalle: list[Any],
    fecha: date,
    hora: time | None = None,
    usuario_id: str | None = None,
    ctx: AppContext | None = None,
) -> None:
    """Crea un movimiento ``consumo`` por fragmento. Lanza si falla."""
    from app.core.services.ubicacion_stock_service import ubicacion_preferida_lote

    data_ref = _ctx(ctx).uow.get_data()
    creados = 0
    for di, det in enumerate(lineas_detalle or []):
        for fi, frag in enumerate(getattr(det, "consumos_lote", None) or []):
            if float(getattr(frag, "cantidad", 0) or 0) <= 0:
                continue
            ubi = ubicacion_preferida_lote(data_ref, frag.lote_id)
            r = espejo_consumo_fragmento(
                producto_id=frag.producto_id,
                lote_id=frag.lote_id,
                cantidad=frag.cantidad,
                fecha=fecha,
                origen_tipo=origen_tipo,
                registro_id=registro_id,
                det_idx=di,
                frag_idx=fi,
                coste_total=frag.coste,
                hora=hora,
                usuario_id=usuario_id,
                ubicacion_origen_id=ubi,
                ctx=ctx,
                commit=False,
            )
            if not r.ok and not r.duplicado:
                raise RuntimeError(
                    f"No se pudo registrar espejo de consumo: {r.mensaje}"
                )
            creados += 1
            mov = buscar_movimiento_consumo_fragmento(
                _ctx(ctx).uow.get_data(), registro_id, di, fi
            )
            if mov is None:
                raise RuntimeError(
                    f"Falta movimiento consumo det{di:02d}:frag{fi:02d}."
                )
            if abs(float(mov.cantidad) - float(frag.cantidad)) > 1e-9:
                raise RuntimeError(
                    f"Cantidad espejo distinta en det{di:02d}:frag{fi:02d}."
                )
    if creados == 0 and any(
        float(getattr(det, "cantidad", 0) or 0) > 0 for det in (lineas_detalle or [])
    ):
        # Registro con detalle pero sin fragmentos: no cubrir aquí (histórico).
        pass


def movimientos_reverso_consumo_de(
    data: AppData, movimiento_id: str
) -> list[MovimientoInventario]:
    return [
        m
        for m in listar_movimientos(data)
        if m.movimiento_revertido_id == movimiento_id
        and _enum_value(m.tipo) == TipoMovimiento.REVERSION_CONSUMO.value
    ]


def espejo_reversion_consumo_fragmento(
    *,
    producto_id: str,
    lote_id: str,
    cantidad: float,
    fecha: date,
    registro_id: str,
    det_idx: int,
    frag_idx: int,
    movimiento_original: MovimientoInventario | None,
    coste_total: float | None = None,
    hora: time | None = None,
    usuario_id: str | None = None,
    ctx: AppContext | None = None,
    commit: bool = False,
) -> ResultadoMovimiento:
    """Escribe ``reversion_consumo``. Histórico → sin original + origen histórica."""
    c = _ctx(ctx)
    if movimiento_original is not None:
        if _enum_value(movimiento_original.tipo) != TipoMovimiento.CONSUMO.value:
            return ResultadoMovimiento(
                ok=False, mensaje="El movimiento a revertir no es consumo"
            )
        if movimiento_original.producto_id != producto_id:
            return ResultadoMovimiento(
                ok=False, mensaje="Producto distinto del movimiento original"
            )
        if movimiento_original.lote_id != lote_id:
            return ResultadoMovimiento(
                ok=False, mensaje="Lote distinto del movimiento original"
            )
        if abs(float(movimiento_original.cantidad) - float(cantidad)) > 1e-9:
            return ResultadoMovimiento(
                ok=False, mensaje="Cantidad distinta del movimiento original"
            )
        ya = movimientos_reverso_consumo_de(
            c.uow.get_data(), movimiento_original.id
        )
        if ya:
            return ResultadoMovimiento(
                ok=False,
                mensaje=f"Movimiento {movimiento_original.id} ya tiene reverso",
                movimiento=ya[0],
                duplicado=True,
            )
        origen_tipo = ORIGEN_TIPO_ANULACION_REGISTRO
        revertido_id = movimiento_original.id
    else:
        origen_tipo = ORIGEN_TIPO_ANULACION_REGISTRO_HISTORICA
        revertido_id = None

    coste_unitario = None
    coste_tot = None
    if coste_total is not None:
        coste_tot = round(float(coste_total), 2)
        if float(cantidad) > 0:
            coste_unitario = round(coste_tot / float(cantidad), 6)
    elif movimiento_original is not None:
        coste_tot = movimiento_original.coste_total_snapshot
        coste_unitario = movimiento_original.coste_unitario_snapshot

    return crear_movimiento(
        producto_id=producto_id,
        lote_id=lote_id,
        tipo=TipoMovimiento.REVERSION_CONSUMO,
        direccion=DireccionMovimiento.ENTRADA,
        cantidad=cantidad,
        fecha=fecha,
        hora=hora,
        origen_tipo=origen_tipo,
        origen_id=registro_id,
        origen_linea_id=origen_linea_id_consumo(det_idx, frag_idx),
        movimiento_revertido_id=revertido_id,
        usuario_id=usuario_id,
        coste_unitario_snapshot=coste_unitario,
        coste_total_snapshot=coste_tot,
        ubicacion_origen_id=(
            getattr(movimiento_original, "ubicacion_destino_id", None)
            if movimiento_original
            else None
        ),
        ubicacion_destino_id=(
            getattr(movimiento_original, "ubicacion_origen_id", None)
            if movimiento_original
            else None
        ),
        ctx=ctx,
        commit=commit,
    )


def escribir_espejos_reversion_consumo_registro(
    *,
    registro_id: str,
    lineas_detalle: list[Any],
    fecha: date,
    hora: time | None = None,
    usuario_id: str | None = None,
    ctx: AppContext | None = None,
) -> None:
    """Un ``reversion_consumo`` por fragmento de ``consumos_lote``. Lanza si falla."""
    data = _ctx(ctx).uow.get_data()
    for di, det in enumerate(lineas_detalle or []):
        for fi, frag in enumerate(getattr(det, "consumos_lote", None) or []):
            if float(getattr(frag, "cantidad", 0) or 0) <= 0:
                continue
            original = buscar_movimiento_consumo_fragmento(
                data, registro_id, di, fi
            )
            r = espejo_reversion_consumo_fragmento(
                producto_id=frag.producto_id,
                lote_id=frag.lote_id,
                cantidad=frag.cantidad,
                fecha=fecha,
                registro_id=registro_id,
                det_idx=di,
                frag_idx=fi,
                movimiento_original=original,
                coste_total=frag.coste,
                hora=hora,
                usuario_id=usuario_id,
                ctx=ctx,
                commit=False,
            )
            if not r.ok and not r.duplicado:
                raise RuntimeError(
                    f"No se pudo registrar reverso de consumo: {r.mensaje}"
                )


def buscar_movimiento_entrada_lote(
    data: AppData, lote_id: str
) -> MovimientoInventario | None:
    for m in buscar_por_origen(data, ORIGEN_TIPO_LOTE, lote_id, None):
        if _enum_value(m.tipo) == TipoMovimiento.ENTRADA_COMPRA.value:
            return m
    # También buscar sin filtrar linea
    for m in listar_movimientos(data):
        if (
            m.origen_tipo == ORIGEN_TIPO_LOTE
            and m.origen_id == lote_id
            and _enum_value(m.tipo) == TipoMovimiento.ENTRADA_COMPRA.value
        ):
            return m
    return None


def espejo_reversion_entrada_lote(
    *,
    producto_id: str,
    lote_id: str,
    cantidad: float,
    fecha: date,
    movimiento_original: MovimientoInventario | None,
    hora: time | None = None,
    usuario_id: str | None = None,
    ctx: AppContext | None = None,
    commit: bool = False,
) -> ResultadoMovimiento:
    """Escribe ``reversion_entrada`` (salida) al anular compra/lote.

    La cantidad es el restante que se pone a 0 (no necesariamente la entrada
    completa si ya hubo consumos).
    """
    if float(cantidad) <= 0:
        return ResultadoMovimiento(
            ok=True, mensaje="Sin restante que revertir en ledger"
        )
    c = _ctx(ctx)
    if movimiento_original is not None:
        tipo_orig = _enum_value(movimiento_original.tipo)
        if tipo_orig not in (
            TipoMovimiento.ENTRADA_COMPRA.value,
            TipoMovimiento.ENTRADA_ALBARAN.value,
        ):
            return ResultadoMovimiento(
                ok=False, mensaje="El movimiento a revertir no es una entrada"
            )
        if movimiento_original.producto_id != producto_id:
            return ResultadoMovimiento(
                ok=False, mensaje="Producto distinto del movimiento original"
            )
        if movimiento_original.lote_id != lote_id:
            return ResultadoMovimiento(
                ok=False, mensaje="Lote distinto del movimiento original"
            )
        ya = [
            m
            for m in listar_movimientos(c.uow.get_data())
            if m.movimiento_revertido_id == movimiento_original.id
            and _enum_value(m.tipo) == TipoMovimiento.REVERSION_ENTRADA.value
        ]
        if ya:
            return ResultadoMovimiento(
                ok=False,
                mensaje=f"Entrada {movimiento_original.id} ya tiene reverso",
                movimiento=ya[0],
                duplicado=True,
            )
        origen_tipo = ORIGEN_TIPO_ANULACION_COMPRA
        revertido_id = movimiento_original.id
    else:
        origen_tipo = ORIGEN_TIPO_ANULACION_COMPRA_HISTORICA
        revertido_id = None

    return crear_movimiento(
        producto_id=producto_id,
        lote_id=lote_id,
        tipo=TipoMovimiento.REVERSION_ENTRADA,
        direccion=DireccionMovimiento.SALIDA,
        cantidad=cantidad,
        fecha=fecha,
        hora=hora,
        origen_tipo=origen_tipo,
        origen_id=lote_id,
        origen_linea_id=None,
        movimiento_revertido_id=revertido_id,
        usuario_id=usuario_id,
        ubicacion_origen_id=(
            getattr(movimiento_original, "ubicacion_destino_id", None)
            if movimiento_original
            else None
        ),
        ubicacion_destino_id=(
            getattr(movimiento_original, "ubicacion_origen_id", None)
            if movimiento_original
            else None
        ),
        ctx=ctx,
        commit=commit,
    )


# --- Consultas de reconciliación (solo lectura; no corrigen stock) ---


def total_entradas_por_lote(data: AppData, lote_id: str) -> float:
    return sum(
        float(m.cantidad)
        for m in buscar_por_lote(data, lote_id)
        if _enum_value(m.direccion) == DireccionMovimiento.ENTRADA.value
        and _enum_value(m.tipo) != TipoMovimiento.TRASLADO.value
    )


def total_salidas_por_lote(data: AppData, lote_id: str) -> float:
    return sum(
        float(m.cantidad)
        for m in buscar_por_lote(data, lote_id)
        if _enum_value(m.direccion) == DireccionMovimiento.SALIDA.value
        and _enum_value(m.tipo) != TipoMovimiento.TRASLADO.value
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

    incidencias.extend(_incidencias_merma_ledger(data))
    incidencias.extend(_incidencias_consumo_ledger(data))

    if movimientos:
        incidencias.append(
            f"Informativo: ledger en modo espejo ({len(movimientos)} movimiento(s)). "
            "Stock operativo desde lotes. "
            + NOTA_SIN_BACKFILL
        )

    return incidencias


@dataclass
class CoberturaMermaLedger:
    merma_id: str
    lineas: int
    movimientos_merma: int
    movimientos_reversion: int
    cobertura: str  # completa | parcial_historica | inconsistente | sin_lineas_lote
    detalle: list[str] = field(default_factory=list)


def cobertura_merma_informativa(data: AppData) -> list[CoberturaMermaLedger]:
    """Informe de cobertura ledger↔merma. No modifica datos."""
    out: list[CoberturaMermaLedger] = []
    for reg in getattr(data, "mermas", []) or []:
        lineas_con_lote = [
            (i, ln)
            for i, ln in enumerate(reg.lineas)
            if ln.lote_id and float(ln.cantidad) > 0
        ]
        n_merma = 0
        n_rev = 0
        detalle: list[str] = []
        faltan = 0
        for i, ln in lineas_con_lote:
            mov = buscar_movimiento_merma_linea(data, reg.id, i)
            if mov is None:
                faltan += 1
                detalle.append(f"línea {origen_linea_id_merma(i)} sin movimiento merma")
            else:
                n_merma += 1
                if abs(float(mov.cantidad) - float(ln.cantidad)) > 1e-9:
                    detalle.append(
                        f"línea {origen_linea_id_merma(i)} cantidad distinta"
                    )
            revs = buscar_por_origen(
                data,
                ORIGEN_TIPO_ANULACION_MERMA,
                reg.id,
                origen_linea_id_merma(i),
            ) + buscar_por_origen(
                data,
                ORIGEN_TIPO_ANULACION_MERMA_HISTORICA,
                reg.id,
                origen_linea_id_merma(i),
            )
            revs = [
                r
                for r in revs
                if _enum_value(r.tipo) == TipoMovimiento.REVERSION_MERMA.value
            ]
            n_rev += len(revs)

        if not lineas_con_lote:
            cob = "sin_lineas_lote"
        elif faltan == 0 and not any("cantidad distinta" in d for d in detalle):
            cob = "completa"
        elif faltan == len(lineas_con_lote):
            cob = "parcial_historica"
            detalle.append(
                "cobertura parcial histórica: sin movimientos espejo originales"
            )
        else:
            cob = "inconsistente"

        if getattr(reg, "anulado", False) and lineas_con_lote:
            if n_rev < len(lineas_con_lote) and cob != "parcial_historica":
                # Anulación con cobertura ledger parcial de salidas
                if n_merma > 0 and n_rev < n_merma:
                    detalle.append("anulación sin reverso completo")
                    cob = "inconsistente"
            elif n_rev == 0 and cob == "parcial_historica":
                detalle.append(
                    "anulación histórica: reversión sin movimiento espejo original "
                    "por cobertura histórica parcial"
                )

        out.append(
            CoberturaMermaLedger(
                merma_id=reg.id,
                lineas=len(lineas_con_lote),
                movimientos_merma=n_merma,
                movimientos_reversion=n_rev,
                cobertura=cob,
                detalle=detalle,
            )
        )
    return out


def _incidencias_merma_ledger(data: AppData) -> list[str]:
    """Incidencias de dual-write merma / reversion (7A.3). Solo lectura."""
    incidencias: list[str] = []
    mermas_map = {m.id: m for m in getattr(data, "mermas", []) or []}
    movs_merma = [
        m
        for m in listar_movimientos(data)
        if _enum_value(m.tipo) == TipoMovimiento.MERMA.value
    ]
    movs_rev = [
        m
        for m in listar_movimientos(data)
        if _enum_value(m.tipo) == TipoMovimiento.REVERSION_MERMA.value
    ]

    # Índice: (merma_id, linea_id) -> list[mov merma]
    por_linea: dict[tuple[str, str], list] = {}
    for m in movs_merma:
        if m.origen_tipo != ORIGEN_TIPO_MERMA:
            incidencias.append(
                f"Movimiento {m.id}: merma con origen_tipo inesperado "
                f"{m.origen_tipo!r}"
            )
        key = (m.origen_id, m.origen_linea_id or "")
        por_linea.setdefault(key, []).append(m)
        reg = mermas_map.get(m.origen_id)
        if reg is None:
            incidencias.append(
                f"Movimiento {m.id}: merma de origen inexistente {m.origen_id}"
            )
            continue
        # Resolver línea por origen_linea_id
        idx = None
        if (m.origen_linea_id or "").startswith("ln"):
            try:
                idx = int((m.origen_linea_id or "")[2:])
            except ValueError:
                idx = None
        if idx is None or idx < 0 or idx >= len(reg.lineas):
            incidencias.append(
                f"Movimiento {m.id}: línea de merma no localizada "
                f"({m.origen_linea_id})"
            )
            continue
        ln = reg.lineas[idx]
        if ln.producto_id != m.producto_id:
            incidencias.append(
                f"Movimiento {m.id}: producto distinto de la línea de merma"
            )
        if (ln.lote_id or "") != m.lote_id:
            incidencias.append(
                f"Movimiento {m.id}: lote distinto de la línea de merma"
            )
        if abs(float(ln.cantidad) - float(m.cantidad)) > 1e-9:
            incidencias.append(
                f"Movimiento {m.id}: cantidad distinta de la línea de merma "
                f"({m.cantidad:g} ≠ {ln.cantidad:g})"
            )
        if (
            m.coste_total_snapshot is not None
            and abs(float(m.coste_total_snapshot) - float(ln.coste)) > 1e-6
        ):
            incidencias.append(
                f"Movimiento {m.id}: coste incoherente con la línea de merma"
            )

    for key, lista in por_linea.items():
        if len(lista) > 1:
            incidencias.append(
                f"Doble movimiento merma para {key[0]} / {key[1]}: "
                + ", ".join(x.id for x in lista)
            )

    # Líneas de merma sin movimiento / cobertura
    for reg in mermas_map.values():
        lineas_lote = [
            (i, ln)
            for i, ln in enumerate(reg.lineas)
            if ln.lote_id and float(ln.cantidad) > 0
        ]
        con_mov = 0
        for i, ln in lineas_lote:
            mov = buscar_movimiento_merma_linea(data, reg.id, i)
            if mov is None:
                if any(
                    buscar_movimiento_merma_linea(data, reg.id, j) is not None
                    for j, _ in lineas_lote
                ):
                    incidencias.append(
                        f"Merma {reg.id} línea {origen_linea_id_merma(i)}: "
                        "sin movimiento espejo (inconsistencia)"
                    )
                else:
                    incidencias.append(
                        f"Informativo: cobertura parcial histórica — merma "
                        f"{reg.id} línea {origen_linea_id_merma(i)} sin movimiento "
                        "espejo"
                    )
            else:
                con_mov += 1

        if getattr(reg, "anulado", False):
            for i, ln in lineas_lote:
                revs = [
                    r
                    for r in (
                        buscar_por_origen(
                            data,
                            ORIGEN_TIPO_ANULACION_MERMA,
                            reg.id,
                            origen_linea_id_merma(i),
                        )
                        + buscar_por_origen(
                            data,
                            ORIGEN_TIPO_ANULACION_MERMA_HISTORICA,
                            reg.id,
                            origen_linea_id_merma(i),
                        )
                    )
                    if _enum_value(r.tipo) == TipoMovimiento.REVERSION_MERMA.value
                ]
                orig = buscar_movimiento_merma_linea(data, reg.id, i)
                if not revs:
                    if orig is not None:
                        incidencias.append(
                            f"Merma {reg.id} anulada línea "
                            f"{origen_linea_id_merma(i)}: sin reversion_merma"
                        )
                    else:
                        incidencias.append(
                            f"Informativo: reversión histórica sin movimiento "
                            f"espejo original — merma {reg.id} línea "
                            f"{origen_linea_id_merma(i)} (cobertura parcial)"
                        )
                elif len(revs) > 1:
                    incidencias.append(
                        f"Doble reverso merma {reg.id} línea "
                        f"{origen_linea_id_merma(i)}: "
                        + ", ".join(r.id for r in revs)
                    )
                else:
                    rev = revs[0]
                    if abs(float(rev.cantidad) - float(ln.cantidad)) > 1e-9:
                        incidencias.append(
                            f"Reverso {rev.id}: cantidad distinta de la línea"
                        )
                    if orig is not None:
                        if rev.movimiento_revertido_id != orig.id:
                            incidencias.append(
                                f"Reverso {rev.id}: no apunta al movimiento "
                                f"original {orig.id}"
                            )
                    elif rev.movimiento_revertido_id:
                        incidencias.append(
                            f"Reverso {rev.id}: apunta a movimiento no "
                            "relacionado (histórico sin original)"
                        )
                    if (
                        rev.origen_tipo
                        == ORIGEN_TIPO_ANULACION_MERMA_HISTORICA
                    ):
                        incidencias.append(
                            f"Informativo: reversión sin movimiento espejo "
                            f"original por cobertura histórica parcial "
                            f"({rev.id})"
                        )

    # Original revertido más de una vez
    rev_por_orig: dict[str, list[str]] = {}
    for r in movs_rev:
        if r.movimiento_revertido_id:
            rev_por_orig.setdefault(r.movimiento_revertido_id, []).append(r.id)
    for orig_id, ids in rev_por_orig.items():
        if len(ids) > 1:
            incidencias.append(
                f"Movimiento original {orig_id} revertido más de una vez: "
                + ", ".join(ids)
            )
        orig = buscar_por_id(data, orig_id)
        if orig is not None and _enum_value(orig.tipo) != TipoMovimiento.MERMA.value:
            incidencias.append(
                f"Reverso apunta a movimiento no relacionado (no es merma): "
                f"{orig_id}"
            )

    return incidencias


def _incidencias_consumo_ledger(data: AppData) -> list[str]:
    """Incidencias dual-write consumo / reversion_consumo / reversion_entrada."""
    incidencias: list[str] = []
    registros: list[tuple[str, Any]] = []
    for d in getattr(data, "desayunos", []) or []:
        registros.append((d.id, d))
    for r in getattr(data, "registros_servicio", []) or []:
        registros.append((r.id, r))

    movs_cons = [
        m
        for m in listar_movimientos(data)
        if _enum_value(m.tipo) == TipoMovimiento.CONSUMO.value
    ]
    por_frag: dict[tuple[str, str], list] = {}
    for m in movs_cons:
        key = (m.origen_id, m.origen_linea_id or "")
        por_frag.setdefault(key, []).append(m)
        # Origen registro
        if not any(rid == m.origen_id for rid, _ in registros):
            incidencias.append(
                f"Movimiento {m.id}: registro de consumo inexistente {m.origen_id}"
            )

    for key, lista in por_frag.items():
        if len(lista) > 1:
            incidencias.append(
                f"Doble movimiento consumo para {key[0]} / {key[1]}"
            )

    for rid, reg in registros:
        detalle = list(getattr(reg, "lineas_detalle", None) or [])
        frags = 0
        con_mov = 0
        for di, det in enumerate(detalle):
            for fi, frag in enumerate(getattr(det, "consumos_lote", None) or []):
                if float(frag.cantidad) <= 0:
                    continue
                frags += 1
                mov = buscar_movimiento_consumo_fragmento(data, rid, di, fi)
                if mov is None:
                    continue
                con_mov += 1
                if mov.producto_id != frag.producto_id:
                    incidencias.append(
                        f"Movimiento {mov.id}: producto distinto del fragmento"
                    )
                if mov.lote_id != frag.lote_id:
                    incidencias.append(
                        f"Movimiento {mov.id}: lote distinto del fragmento"
                    )
                if abs(float(mov.cantidad) - float(frag.cantidad)) > 1e-9:
                    incidencias.append(
                        f"Movimiento {mov.id}: cantidad distinta del fragmento"
                    )
                if (
                    mov.coste_total_snapshot is not None
                    and abs(float(mov.coste_total_snapshot) - float(frag.coste)) > 1e-6
                ):
                    incidencias.append(
                        f"Movimiento {mov.id}: coste incoherente con fragmento"
                    )

        if frags > 0 and con_mov == 0:
            incidencias.append(
                f"Informativo: cobertura parcial histórica — registro {rid} "
                "sin movimientos consumo espejo"
            )
        elif frags > 0 and con_mov < frags:
            incidencias.append(
                f"Registro {rid}: fragmentos sin movimiento espejo "
                f"({con_mov}/{frags}) — inconsistencia"
            )

        if getattr(reg, "anulado", False) and frags > 0:
            n_rev = sum(
                1
                for m in listar_movimientos(data)
                if m.origen_id == rid
                and _enum_value(m.tipo) == TipoMovimiento.REVERSION_CONSUMO.value
            )
            if n_rev == 0 and con_mov == 0:
                incidencias.append(
                    f"Informativo: reversión histórica sin movimiento espejo "
                    f"original — registro {rid} (cobertura parcial)"
                )
            elif n_rev < frags and con_mov > 0:
                incidencias.append(
                    f"Registro {rid} anulado: reversion_consumo incompleta "
                    f"({n_rev}/{frags})"
                )

    # Reversos consumo duplicados por original
    rev_por_orig: dict[str, list[str]] = {}
    for m in listar_movimientos(data):
        if (
            _enum_value(m.tipo) == TipoMovimiento.REVERSION_CONSUMO.value
            and m.movimiento_revertido_id
        ):
            rev_por_orig.setdefault(m.movimiento_revertido_id, []).append(m.id)
    for oid, ids in rev_por_orig.items():
        if len(ids) > 1:
            incidencias.append(
                f"Consumo original {oid} revertido más de una vez: "
                + ", ".join(ids)
            )

    # Compras anuladas sin reversion_entrada
    for lote in getattr(data, "lotes", []) or []:
        if not getattr(lote, "anulado", False):
            continue
        revs = [
            m
            for m in listar_movimientos(data)
            if m.origen_id == lote.id
            and _enum_value(m.tipo) == TipoMovimiento.REVERSION_ENTRADA.value
        ]
        entrada = buscar_movimiento_entrada_lote(data, lote.id)
        if not revs and entrada is not None:
            incidencias.append(
                f"Compra/lote {lote.id} anulado: sin reversion_entrada"
            )
        elif not revs and entrada is None:
            incidencias.append(
                f"Informativo: anulación de compra histórica sin entrada espejo "
                f"— lote {lote.id}"
            )
        elif len(revs) > 1:
            incidencias.append(
                f"Doble reversion_entrada para lote {lote.id}"
            )

    return incidencias


@dataclass
class ResumenTiposLedger:
    entradas: float
    consumos: float
    mermas: float
    ajustes_entrada: float
    ajustes_salida: float
    reversos_entrada: float
    reversos_consumo: float
    reversos_merma: float
    saldo_teorico: float
    nota: str = NOTA_LEDGER_PARCIAL


def resumen_tipos_ledger(data: AppData) -> ResumenTiposLedger:
    """Totales firmados por familia de tipo. Solo lectura."""
    acc = {
        TipoMovimiento.ENTRADA_COMPRA.value: 0.0,
        TipoMovimiento.CONSUMO.value: 0.0,
        TipoMovimiento.MERMA.value: 0.0,
        TipoMovimiento.AJUSTE_ENTRADA.value: 0.0,
        TipoMovimiento.AJUSTE_SALIDA.value: 0.0,
        TipoMovimiento.REVERSION_ENTRADA.value: 0.0,
        TipoMovimiento.REVERSION_CONSUMO.value: 0.0,
        TipoMovimiento.REVERSION_MERMA.value: 0.0,
    }
    for m in listar_movimientos(data):
        t = _enum_value(m.tipo)
        if t in acc:
            acc[t] += float(m.cantidad)
    teorico = (
        acc[TipoMovimiento.ENTRADA_COMPRA.value]
        + acc[TipoMovimiento.AJUSTE_ENTRADA.value]
        + acc[TipoMovimiento.REVERSION_CONSUMO.value]
        + acc[TipoMovimiento.REVERSION_MERMA.value]
        - acc[TipoMovimiento.CONSUMO.value]
        - acc[TipoMovimiento.MERMA.value]
        - acc[TipoMovimiento.AJUSTE_SALIDA.value]
        - acc[TipoMovimiento.REVERSION_ENTRADA.value]
    )
    return ResumenTiposLedger(
        entradas=acc[TipoMovimiento.ENTRADA_COMPRA.value],
        consumos=acc[TipoMovimiento.CONSUMO.value],
        mermas=acc[TipoMovimiento.MERMA.value],
        ajustes_entrada=acc[TipoMovimiento.AJUSTE_ENTRADA.value],
        ajustes_salida=acc[TipoMovimiento.AJUSTE_SALIDA.value],
        reversos_entrada=acc[TipoMovimiento.REVERSION_ENTRADA.value],
        reversos_consumo=acc[TipoMovimiento.REVERSION_CONSUMO.value],
        reversos_merma=acc[TipoMovimiento.REVERSION_MERMA.value],
        saldo_teorico=teorico,
    )


def contar_movimientos_por_tipo(data: AppData, tipo: TipoMovimiento | str) -> int:
    t = _enum_value(tipo)
    return sum(1 for m in listar_movimientos(data) if _enum_value(m.tipo) == t)


# API pública del servicio: sin edición ni borrado.
__all__ = [
    "CoberturaMermaLedger",
    "ComparacionLoteLedger",
    "NOTA_LEDGER_PARCIAL",
    "NOTA_SIN_BACKFILL",
    "ORIGENES_CONSUMO_REGISTRO",
    "ORIGEN_TIPO_AJUSTE",
    "ORIGEN_TIPO_ANULACION_COMPRA",
    "ORIGEN_TIPO_ANULACION_COMPRA_HISTORICA",
    "ORIGEN_TIPO_ANULACION_MERMA",
    "ORIGEN_TIPO_ANULACION_MERMA_HISTORICA",
    "ORIGEN_TIPO_ANULACION_REGISTRO",
    "ORIGEN_TIPO_ANULACION_REGISTRO_HISTORICA",
    "ORIGEN_TIPO_DESAYUNO",
    "ORIGEN_TIPO_LOTE",
    "ORIGEN_TIPO_MERMA",
    "ORIGEN_TIPO_REGISTRO_SERVICIO",
    "ResultadoMovimiento",
    "ResumenTiposLedger",
    "buscar_movimiento_consumo_fragmento",
    "buscar_movimiento_entrada_lote",
    "buscar_movimiento_merma_linea",
    "buscar_por_id",
    "buscar_por_lote",
    "buscar_por_origen",
    "buscar_por_producto",
    "cobertura_merma_informativa",
    "comparar_ledger_vs_lote",
    "comprobar_idempotencia",
    "construir_idempotency_key",
    "contar_movimientos_por_tipo",
    "crear_movimiento",
    "direccion_esperada",
    "escribir_espejos_consumo_registro",
    "escribir_espejos_reversion_consumo_registro",
    "espejo_ajuste_linea",
    "espejo_consumo_fragmento",
    "espejo_entrada_lote",
    "espejo_merma_linea",
    "espejo_reversion_consumo_fragmento",
    "espejo_reversion_entrada_lote",
    "espejo_reversion_merma_linea",
    "incidencias_movimientos",
    "listar_movimientos",
    "movimientos_reverso_consumo_de",
    "movimientos_reverso_de",
    "origen_linea_id_consumo",
    "origen_linea_id_merma",
    "reconciliacion_informativa",
    "resumen_tipos_ledger",
    "saldo_teorico_ledger_por_lote",
    "total_entradas_por_lote",
    "total_salidas_por_lote",
    "validar_movimiento",
]
