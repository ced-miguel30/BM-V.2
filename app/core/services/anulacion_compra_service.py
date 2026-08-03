"""Anulación restringida de compras/lotes (Fase 11C).

Solo si el lote está intacto (cantidad_restante ≈ cantidad) y sin
dependencias activas en merma/registros/ajustes. Sin borrado físico.

Fase 4G: operaciones vía AppContext (reloj, actor, auditoría, UoW).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.core.application.context import AppContext
from app.core.models import AppData, LoteStock
from app.core.repositories.data_repository import DataRepository
from app.core.services.inventory_batch_service import (
    restaurar_cantidades_restantes,
    snapshot_cantidades_restantes,
)
from app.core.storage.session_store import get_data, persist_data


@dataclass
class ResultadoPuedeAnularCompra:
    ok: bool
    motivos_bloqueo: list[str] = field(default_factory=list)


@dataclass
class PreviewAnulacionCompra:
    lote_id: str
    producto_id: str
    nombre: str
    cantidad_compra: float
    cantidad_restante: float
    precio_total: float
    unidad: str
    estado_actual: str
    efecto: str
    bloqueado: bool = False
    motivos_bloqueo: list[str] = field(default_factory=list)


@dataclass
class ResultadoAnulacionCompra:
    ok: bool
    mensaje: str


class _CompatSessionUow:
    def get_data(self) -> AppData:
        return get_data()

    def commit(self, data: AppData | None = None) -> AppData:
        return persist_data(data if data is not None else get_data())


def _context(
    data: AppData | None = None,
    ctx: AppContext | None = None,
) -> tuple[AppContext, AppData]:
    if ctx is not None:
        return ctx, ctx.data()
    from app.core.application.actor import actor_desde_appdata
    from app.core.application.clock import SystemClock

    if data is None:
        uow = _CompatSessionUow()
        app = uow.get_data()
        return AppContext(uow=uow, actor=actor_desde_appdata(app), clock=SystemClock()), app

    class _DataUow:
        def get_data(self) -> AppData:
            return data

        def commit(self, payload: AppData | None = None) -> AppData:
            return persist_data(payload if payload is not None else data)

    return (
        AppContext(
            uow=_DataUow(),
            actor=actor_desde_appdata(data),
            clock=SystemClock(),
        ),
        data,
    )


def _registrar_actividad(ctx: AppContext, accion: str, detalle: str) -> None:
    from app.core.application.auditoria import registrar_actividad

    registrar_actividad(ctx, accion, detalle, commit=False)


def lote_esta_anulado(lote: LoteStock | None) -> bool:
    return bool(lote is not None and getattr(lote, "anulado", False))


def _buscar_lote(data: AppData, lote_id: str) -> LoteStock | None:
    return next((l for l in data.lotes if l.id == lote_id), None)


def _dependencias_activas(data: AppData, lote_id: str) -> list[str]:
    deps: list[str] = []

    for merma in data.mermas:
        if getattr(merma, "anulado", False):
            continue
        for ln in merma.lineas:
            if ln.lote_id == lote_id:
                deps.append(f"Merma activa {merma.id} referencia el lote.")
                break

    for ajuste in getattr(data, "ajustes", []) or []:
        for ln in ajuste.lineas:
            if ln.lote_id == lote_id:
                deps.append(f"Ajuste {ajuste.id} referencia el lote.")
                break

    for desayuno in data.desayunos:
        if getattr(desayuno, "anulado", False):
            continue
        for det in desayuno.lineas_detalle:
            for c in getattr(det, "consumos_lote", None) or []:
                if c.lote_id == lote_id:
                    deps.append(f"Desayuno activo {desayuno.id} consumió el lote.")
                    break
            else:
                continue
            break

    for reg in data.registros_servicio:
        if getattr(reg, "anulado", False):
            continue
        for det in reg.lineas_detalle:
            for c in getattr(det, "consumos_lote", None) or []:
                if c.lote_id == lote_id:
                    deps.append(
                        f"Registro activo {reg.id} ({reg.tipo_servicio}) consumió el lote."
                    )
                    break
            else:
                continue
            break

    vistos: set[str] = set()
    unicos: list[str] = []
    for d in deps:
        if d not in vistos:
            vistos.add(d)
            unicos.append(d)
    return unicos


def puede_anular_compra(data: AppData, lote: LoteStock | None) -> ResultadoPuedeAnularCompra:
    if lote is None:
        return ResultadoPuedeAnularCompra(False, ["Compra/lote no encontrado."])
    if lote_esta_anulado(lote):
        return ResultadoPuedeAnularCompra(False, ["Compra ya anulada."])

    motivos: list[str] = []
    if abs(round(lote.cantidad_restante, 4) - round(lote.cantidad, 4)) > 1e-9:
        motivos.append(
            f"Lote consumido o alterado: restante {lote.cantidad_restante:g} "
            f"≠ cantidad de compra {lote.cantidad:g}."
        )

    motivos.extend(_dependencias_activas(data, lote.id))
    return ResultadoPuedeAnularCompra(ok=not motivos, motivos_bloqueo=motivos)


def previsualizar_anulacion_compra(
    data: AppData,
    lote: LoteStock | None,
) -> PreviewAnulacionCompra:
    puede = puede_anular_compra(data, lote)
    repo = DataRepository(data)
    producto = repo.get_producto(lote.producto_id) if lote else None
    estado = "Anulado" if lote_esta_anulado(lote) else "Activo"
    efecto = (
        "Se pondrá cantidad_restante = 0 y se marcará la compra como anulada. "
        "No se borrará el histórico (precio, cantidad original, fechas)."
        if puede.ok
        else "Anulación no disponible."
    )
    return PreviewAnulacionCompra(
        lote_id=lote.id if lote else "",
        producto_id=lote.producto_id if lote else "",
        nombre=producto.nombre if producto else (lote.producto_id if lote else "—"),
        cantidad_compra=lote.cantidad if lote else 0.0,
        cantidad_restante=lote.cantidad_restante if lote else 0.0,
        precio_total=lote.precio_total if lote else 0.0,
        unidad=producto.unidad.value if producto else "",
        estado_actual=estado,
        efecto=efecto,
        bloqueado=not puede.ok,
        motivos_bloqueo=puede.motivos_bloqueo,
    )


def anular_compra(
    data: AppData | None,
    lote_id: str,
    motivo: str,
    referencia: str = "",
    *,
    ctx: AppContext | None = None,
) -> ResultadoAnulacionCompra:
    context, data = _context(data, ctx)
    motivo_limpio = (motivo or "").strip()
    if not motivo_limpio:
        return ResultadoAnulacionCompra(False, "El motivo de anulación es obligatorio.")

    lote = _buscar_lote(data, lote_id)
    if lote is None:
        return ResultadoAnulacionCompra(False, f"Lote «{lote_id}» no encontrado.")

    if lote_esta_anulado(lote):
        return ResultadoAnulacionCompra(False, "Compra ya anulada.")

    puede = puede_anular_compra(data, lote)
    if not puede.ok:
        return ResultadoAnulacionCompra(
            False,
            "No se puede anular: " + " ".join(puede.motivos_bloqueo),
        )

    snap_lotes = snapshot_cantidades_restantes(data)
    snap_campos = (
        lote.anulado,
        lote.fecha_anulacion,
        lote.hora_anulacion,
        lote.motivo_anulacion,
        lote.referencia_anulacion,
        lote.anulado_por,
        lote.cantidad_restante,
    )
    n_actividades = len(data.actividades)
    repo = DataRepository(data)
    producto = repo.get_producto(lote.producto_id)
    nombre = producto.nombre if producto else lote.producto_id

    try:
        lote.cantidad_restante = 0.0
        ahora = context.clock.now()
        lote.anulado = True
        lote.fecha_anulacion = ahora.date()
        lote.hora_anulacion = ahora.time().replace(microsecond=0)
        lote.motivo_anulacion = motivo_limpio
        lote.referencia_anulacion = (referencia or "").strip()
        lote.anulado_por = context.actor.nombre

        _registrar_actividad(
            context,
            "Anulación compra",
            (
                f"Anulado lote {lote_id} de «{nombre}» — motivo: {motivo_limpio}"
                + (f" — ref: {referencia}" if referencia else "")
            ),
        )
        context.uow.commit(data)
    except Exception as exc:
        restaurar_cantidades_restantes(data, snap_lotes)
        (
            lote.anulado,
            lote.fecha_anulacion,
            lote.hora_anulacion,
            lote.motivo_anulacion,
            lote.referencia_anulacion,
            lote.anulado_por,
            lote.cantidad_restante,
        ) = snap_campos
        del data.actividades[: max(0, len(data.actividades) - n_actividades)]
        return ResultadoAnulacionCompra(
            False, f"Anulación fallida; estado restaurado. ({exc})",
        )

    from app.core.services.alert_service import sincronizar_alertas
    sincronizar_alertas(context)

    return ResultadoAnulacionCompra(
        True,
        f"Compra/lote {lote_id} anulado. Stock restante puesto a 0.",
    )
