"""Traslados de inventario entre ubicaciones (Fase 7B.4).

No cambian stock total del hotel ni coste ni FIFO global.
Un movimiento lógico ``traslado`` con origen + destino.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.core.application.context import AppContext
from app.core.application.id_generator import next_id
from app.core.models import Actividad, AppData, MovimientoInventario
from app.core.models.enums import DireccionMovimiento, TipoMovimiento
from app.core.services import movimiento_service as mov
from app.core.services.inventory_batch_service import coste_unidad_lote
from app.core.services.ubicacion_stock_service import (
    saldo_en_ubicacion,
    validar_ubicacion_catalogo,
)
from app.core.storage.session_store import get_data, persist_data

ORIGEN_TIPO_TRASLADO = "traslado"
ORIGEN_TIPO_ANULACION_TRASLADO = "anulacion_traslado"


@dataclass
class PreviewTraslado:
    producto_id: str
    producto_nombre: str
    lote_id: str
    ubicacion_origen_id: str
    ubicacion_destino_id: str
    cantidad: float
    disponible_origen: float
    stock_hotel_antes: float
    stock_hotel_despues: float
    coste_unitario: float
    coste_total_invariante: float
    ok: bool
    mensaje: str
    advertencia_destino: str | None = None


@dataclass
class ResultadoTraslado:
    ok: bool
    mensaje: str
    movimiento: MovimientoInventario | None = None
    traslado_id: str | None = None


def _ctx_session() -> AppContext:
    from app.core.application.context import build_app_context
    from app.core.application.unit_of_work import InMemoryUnitOfWork

    return build_app_context(uow=InMemoryUnitOfWork(get_data()))


def _stock_hotel_lote(data: AppData, lote_id: str) -> float:
    lote = next((l for l in data.lotes if l.id == lote_id), None)
    return float(lote.cantidad_restante) if lote else 0.0


def previsualizar_traslado(
    data: AppData,
    *,
    lote_id: str,
    ubicacion_origen_id: str,
    ubicacion_destino_id: str,
    cantidad: float,
    permitir_destino_no_catalogado: bool = False,
) -> PreviewTraslado:
    lote = next((l for l in data.lotes if l.id == lote_id), None)
    if lote is None:
        return PreviewTraslado(
            "", "", lote_id, ubicacion_origen_id, ubicacion_destino_id,
            cantidad, 0, 0, 0, 0, 0, False, "Lote no encontrado.",
        )
    if getattr(lote, "anulado", False):
        return PreviewTraslado(
            lote.producto_id, "", lote_id, ubicacion_origen_id,
            ubicacion_destino_id, cantidad, 0, 0, 0, 0, 0, False,
            "Lote anulado.",
        )
    prod = next((p for p in data.productos if p.id == lote.producto_id), None)
    nombre = prod.nombre if prod else lote.producto_id
    try:
        qty = float(cantidad)
    except (TypeError, ValueError):
        qty = 0.0

    err_o = validar_ubicacion_catalogo(data, ubicacion_origen_id)
    err_d = validar_ubicacion_catalogo(data, ubicacion_destino_id)
    if err_o:
        return PreviewTraslado(
            lote.producto_id, nombre, lote_id, ubicacion_origen_id,
            ubicacion_destino_id, qty, 0, 0, 0, 0, 0, False, err_o,
        )
    if err_d:
        return PreviewTraslado(
            lote.producto_id, nombre, lote_id, ubicacion_origen_id,
            ubicacion_destino_id, qty, 0, 0, 0, 0, 0, False, err_d,
        )
    if ubicacion_origen_id == ubicacion_destino_id:
        return PreviewTraslado(
            lote.producto_id, nombre, lote_id, ubicacion_origen_id,
            ubicacion_destino_id, qty, 0, 0, 0, 0, 0, False,
            "Origen y destino deben ser distintos.",
        )
    if qty <= 0:
        return PreviewTraslado(
            lote.producto_id, nombre, lote_id, ubicacion_origen_id,
            ubicacion_destino_id, qty, 0, 0, 0, 0, 0, False,
            "La cantidad debe ser mayor que cero.",
        )

    disp = saldo_en_ubicacion(data, lote_id, ubicacion_origen_id)
    stock = _stock_hotel_lote(data, lote_id)
    coste_u = coste_unidad_lote(lote)
    advertencia = None
    if prod and ubicacion_destino_id not in (prod.ubicacion_ids or []):
        advertencia = (
            f"La ubicación destino no está en las permitidas del producto "
            f"«{nombre}». Confirme si procede."
        )
        if not permitir_destino_no_catalogado:
            # Preview sigue ok con advertencia; confirmación puede exigir flag.
            pass

    if qty > disp + 1e-9:
        return PreviewTraslado(
            lote.producto_id, nombre, lote_id, ubicacion_origen_id,
            ubicacion_destino_id, qty, disp, stock, stock, coste_u,
            round(coste_u * stock, 2), False,
            f"Saldo insuficiente en origen ({disp:g} disponible).",
            advertencia,
        )

    return PreviewTraslado(
        lote.producto_id,
        nombre,
        lote_id,
        ubicacion_origen_id,
        ubicacion_destino_id,
        qty,
        disp,
        stock,
        stock,  # invariante
        coste_u,
        round(coste_u * stock, 2),
        True,
        "Traslado válido.",
        advertencia,
    )


def confirmar_traslado(
    *,
    lote_id: str,
    ubicacion_origen_id: str,
    ubicacion_destino_id: str,
    cantidad: float,
    fecha: date | None = None,
    permitir_destino_no_catalogado: bool = False,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoTraslado:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
    if denied:
        return ResultadoTraslado(False, denied)

    c = ctx or _ctx_session()
    data = c.uow.get_data()
    if not hasattr(data, "movimientos") or data.movimientos is None:
        data.movimientos = []

    preview = previsualizar_traslado(
        data,
        lote_id=lote_id,
        ubicacion_origen_id=ubicacion_origen_id,
        ubicacion_destino_id=ubicacion_destino_id,
        cantidad=cantidad,
        permitir_destino_no_catalogado=permitir_destino_no_catalogado,
    )
    if not preview.ok:
        return ResultadoTraslado(False, preview.mensaje)
    if preview.advertencia_destino and not permitir_destino_no_catalogado:
        return ResultadoTraslado(
            False,
            preview.advertencia_destino
            or "Destino no permitido; confirme explícitamente.",
        )

    lote = next(l for l in data.lotes if l.id == lote_id)
    stock_antes = float(lote.cantidad_restante)
    n_mov = len(data.movimientos)
    n_act = len(data.actividades)
    traslado_id = next_id("tr", [
        m.origen_id for m in data.movimientos
        if m.origen_tipo == ORIGEN_TIPO_TRASLADO
    ] + [a.id for a in data.actividades if a.id.startswith("tr")])

    try:
        r = mov.crear_movimiento(
            producto_id=lote.producto_id,
            lote_id=lote_id,
            tipo=TipoMovimiento.TRASLADO,
            direccion=DireccionMovimiento.ENTRADA,
            cantidad=float(cantidad),
            fecha=fecha or (
                c.clock.today() if getattr(c, "clock", None) else date.today()
            ),
            origen_tipo=ORIGEN_TIPO_TRASLADO,
            origen_id=traslado_id,
            usuario_id=getattr(getattr(c, "actor", None), "id", None),
            ubicacion_origen_id=ubicacion_origen_id,
            ubicacion_destino_id=ubicacion_destino_id,
            coste_unitario_snapshot=round(coste_unidad_lote(lote), 6),
            coste_total_snapshot=round(
                coste_unidad_lote(lote) * float(cantidad), 2
            ),
            ctx=c,
            commit=False,
        )
        if not r.ok and not r.duplicado:
            raise RuntimeError(r.mensaje)
        if abs(float(lote.cantidad_restante) - stock_antes) > 1e-9:
            raise RuntimeError("El traslado no debe alterar cantidad_restante.")

        usuario = "Sistema"
        if getattr(c, "actor", None) and getattr(c.actor, "nombre", None):
            usuario = c.actor.nombre
        data.actividades.insert(
            0,
            Actividad(
                next_id("act", [a.id for a in data.actividades]),
                datetime.now(),
                usuario,
                "Traslado inventario",
                (
                    f"{preview.producto_nombre} lote {lote_id}: "
                    f"{cantidad:g} {ubicacion_origen_id} → {ubicacion_destino_id}"
                ),
            ),
        )
        if commit:
            c.uow.commit(data)
            if ctx is None:
                persist_data(data)
        return ResultadoTraslado(
            True,
            f"Traslado {traslado_id} registrado.",
            movimiento=r.movimiento,
            traslado_id=traslado_id,
        )
    except Exception as exc:  # noqa: BLE001
        del data.movimientos[n_mov:]
        del data.actividades[n_act:]
        return ResultadoTraslado(False, f"Traslado abortado: {exc}")


def anular_traslado(
    *,
    traslado_id: str,
    fecha: date | None = None,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoTraslado:
    """Crea traslado reverso (destino→origen). No borra el original."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
    if denied:
        return ResultadoTraslado(False, denied)

    c = ctx or _ctx_session()
    data = c.uow.get_data()
    originales = [
        m
        for m in data.movimientos
        if m.origen_tipo == ORIGEN_TIPO_TRASLADO
        and m.origen_id == traslado_id
        and (
            m.tipo.value if hasattr(m.tipo, "value") else str(m.tipo)
        ) == TipoMovimiento.TRASLADO.value
    ]
    if not originales:
        return ResultadoTraslado(False, f"Traslado {traslado_id} no encontrado.")
    original = originales[0]
    ya = [
        m
        for m in data.movimientos
        if m.movimiento_revertido_id == original.id
    ]
    if ya:
        return ResultadoTraslado(
            False,
            f"Traslado {traslado_id} ya anulado.",
            movimiento=ya[0],
        )

    n_mov = len(data.movimientos)
    n_act = len(data.actividades)
    try:
        r = mov.crear_movimiento(
            producto_id=original.producto_id,
            lote_id=original.lote_id,
            tipo=TipoMovimiento.TRASLADO,
            direccion=DireccionMovimiento.ENTRADA,
            cantidad=float(original.cantidad),
            fecha=fecha or (
                c.clock.today() if getattr(c, "clock", None) else date.today()
            ),
            origen_tipo=ORIGEN_TIPO_ANULACION_TRASLADO,
            origen_id=traslado_id,
            movimiento_revertido_id=original.id,
            usuario_id=getattr(getattr(c, "actor", None), "id", None),
            ubicacion_origen_id=original.ubicacion_destino_id,
            ubicacion_destino_id=original.ubicacion_origen_id,
            coste_unitario_snapshot=original.coste_unitario_snapshot,
            coste_total_snapshot=original.coste_total_snapshot,
            ctx=c,
            commit=False,
        )
        if not r.ok and not r.duplicado:
            raise RuntimeError(r.mensaje)
        data.actividades.insert(
            0,
            Actividad(
                next_id("act", [a.id for a in data.actividades]),
                datetime.now(),
                getattr(getattr(c, "actor", None), "nombre", None) or "Sistema",
                "Anulación traslado",
                f"Reverso de traslado {traslado_id}",
            ),
        )
        if commit:
            c.uow.commit(data)
            if ctx is None:
                persist_data(data)
        return ResultadoTraslado(
            True,
            f"Traslado {traslado_id} anulado (reverso).",
            movimiento=r.movimiento,
            traslado_id=traslado_id,
        )
    except Exception as exc:  # noqa: BLE001
        del data.movimientos[n_mov:]
        del data.actividades[n_act:]
        return ResultadoTraslado(False, f"Anulación abortada: {exc}")


def listar_traslados(data: AppData) -> list[MovimientoInventario]:
    return [
        m
        for m in data.movimientos
        if (
            m.tipo.value if hasattr(m.tipo, "value") else str(m.tipo)
        ) == TipoMovimiento.TRASLADO.value
        and m.origen_tipo == ORIGEN_TIPO_TRASLADO
    ]
