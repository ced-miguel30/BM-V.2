"""Anulación soft de registros de servicio (Fase 11A).

Usa `consumos_lote` ya persistido (Fase 10.5). No inventa FIFO ni lotes.
No toca merma, compras ni ajustes.

Fase 4G: operaciones vía AppContext (reloj, actor, auditoría, UoW).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time

from app.core.application.context import AppContext
from app.core.models import AppData, RegistroDesayuno, RegistroServicio
from app.core.repositories.data_repository import DataRepository
from app.core.services.inventory_batch_service import (
    restaurar_cantidades_restantes,
    snapshot_cantidades_restantes,
)
from app.core.storage.session_store import get_data, persist_data

TIPO_DESAYUNO = "desayuno"
TIPO_SERVICIO = "servicio"


@dataclass
class ResultadoPuedeAnular:
    ok: bool
    motivos_bloqueo: list[str] = field(default_factory=list)


@dataclass
class PreviewLineaAnulacion:
    producto_id: str
    nombre: str
    lote_id: str
    cantidad_consumida: float
    cantidad_restante_actual: float
    cantidad_a_devolver: float
    cantidad_resultante: float
    unidad: str


@dataclass
class PreviewAnulacion:
    registro_id: str
    tipo_registro: str
    estado_actual: str
    lineas: list[PreviewLineaAnulacion] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    bloqueado: bool = False
    motivos_bloqueo: list[str] = field(default_factory=list)


@dataclass
class ResultadoAnulacion:
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
    """Resuelve contexto. Si hay `data` explícito, el commit persiste ese objeto."""
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


def registro_esta_anulado(registro) -> bool:
    return bool(getattr(registro, "anulado", False))


def _buscar_registro(
    data: AppData,
    registro_id: str,
    tipo_registro: str,
) -> RegistroDesayuno | RegistroServicio | None:
    if tipo_registro == TIPO_DESAYUNO:
        return next((d for d in data.desayunos if d.id == registro_id), None)
    if tipo_registro == TIPO_SERVICIO:
        return next((r for r in data.registros_servicio if r.id == registro_id), None)
    return None


def _inferir_tipo(registro) -> str:
    if isinstance(registro, RegistroDesayuno):
        return TIPO_DESAYUNO
    return TIPO_SERVICIO


def _motivos_bloqueo_trazabilidad(data: AppData, registro) -> list[str]:
    motivos: list[str] = []
    if registro_esta_anulado(registro):
        motivos.append("Registro ya anulado.")
        return motivos

    detalle = list(getattr(registro, "lineas_detalle", None) or [])
    if not detalle:
        motivos.append(
            "Sin líneas de detalle: no hay trazabilidad histórica por lote."
        )
        return motivos

    lotes = {l.id: l for l in data.lotes}
    hay_consumible = False
    for det in detalle:
        if det.cantidad <= 0:
            continue
        hay_consumible = True
        consumos = list(getattr(det, "consumos_lote", None) or [])
        if not consumos:
            motivos.append(
                f"Producto {det.producto_id}: sin trazabilidad histórica por lote."
            )
            continue
        suma_cant = round(sum(c.cantidad for c in consumos), 4)
        suma_coste = round(sum(c.coste for c in consumos), 2)
        if abs(suma_cant - round(det.cantidad, 4)) > 1e-9:
            motivos.append(
                f"Producto {det.producto_id}: cantidades de lote "
                f"({suma_cant:g}) ≠ línea ({det.cantidad:g})."
            )
        if suma_coste != round(det.coste, 2):
            motivos.append(
                f"Producto {det.producto_id}: costes de lote "
                f"({suma_coste:.2f}) ≠ línea ({det.coste:.2f})."
            )
        for c in consumos:
            if not c.lote_id:
                motivos.append(f"Producto {det.producto_id}: lote_id vacío.")
                continue
            if c.cantidad <= 0:
                motivos.append(
                    f"Producto {det.producto_id}: fragmento con cantidad no positiva."
                )
            if c.producto_id != det.producto_id:
                motivos.append(
                    f"Fragmento producto {c.producto_id} ≠ línea {det.producto_id}."
                )
            lote = lotes.get(c.lote_id)
            if lote is None:
                motivos.append(f"Lote inexistente: {c.lote_id}.")
            elif lote.producto_id != c.producto_id:
                motivos.append(
                    f"Lote {c.lote_id} pertenece a {lote.producto_id}, "
                    f"no a {c.producto_id}."
                )

    if not hay_consumible and not motivos:
        motivos.append("El registro no tiene cantidades consumibles que reponer.")

    # Deduplicar preservando orden
    vistos: set[str] = set()
    unicos: list[str] = []
    for m in motivos:
        if m not in vistos:
            vistos.add(m)
            unicos.append(m)
    return unicos


def puede_anular_registro(
    data: AppData,
    registro,
    *,
    tipo: str | None = None,
) -> ResultadoPuedeAnular:
    _ = tipo  # reservado; el registro ya tipa el stack
    if registro is None:
        return ResultadoPuedeAnular(False, ["Registro no encontrado."])
    motivos = _motivos_bloqueo_trazabilidad(data, registro)
    return ResultadoPuedeAnular(ok=not motivos, motivos_bloqueo=motivos)


def _aggregar_devoluciones(registro) -> dict[str, float]:
    """lote_id → cantidad a devolver (suma de fragmentos)."""
    por_lote: dict[str, float] = {}
    for det in getattr(registro, "lineas_detalle", None) or []:
        if det.cantidad <= 0:
            continue
        for c in getattr(det, "consumos_lote", None) or []:
            if c.cantidad <= 0 or not c.lote_id:
                continue
            por_lote[c.lote_id] = round(por_lote.get(c.lote_id, 0.0) + c.cantidad, 4)
    return por_lote


def previsualizar_anulacion(
    data: AppData,
    registro,
    *,
    tipo: str | None = None,
) -> PreviewAnulacion:
    tipo_reg = tipo or _inferir_tipo(registro)
    puede = puede_anular_registro(data, registro, tipo=tipo_reg)
    repo = DataRepository(data)
    lotes = {l.id: l for l in data.lotes}
    por_lote = _aggregar_devoluciones(registro) if registro is not None else {}

    lineas_prev: list[PreviewLineaAnulacion] = []
    for lote_id, qty in sorted(por_lote.items()):
        lote = lotes.get(lote_id)
        producto_id = lote.producto_id if lote else ""
        # Preferir producto_id del fragmento si el lote falta
        if not producto_id and registro is not None:
            for det in registro.lineas_detalle:
                for c in det.consumos_lote:
                    if c.lote_id == lote_id:
                        producto_id = c.producto_id
                        break
        producto = repo.get_producto(producto_id) if producto_id else None
        restante = float(lote.cantidad_restante) if lote else 0.0
        lineas_prev.append(PreviewLineaAnulacion(
            producto_id=producto_id,
            nombre=producto.nombre if producto else producto_id or "—",
            lote_id=lote_id,
            cantidad_consumida=qty,
            cantidad_restante_actual=restante,
            cantidad_a_devolver=qty,
            cantidad_resultante=round(restante + qty, 4),
            unidad=producto.unidad.value if producto else "",
        ))

    estado = "Anulado" if registro is not None and registro_esta_anulado(registro) else "Activo"
    return PreviewAnulacion(
        registro_id=getattr(registro, "id", "") if registro else "",
        tipo_registro=tipo_reg,
        estado_actual=estado,
        lineas=lineas_prev,
        advertencias=[],
        bloqueado=not puede.ok,
        motivos_bloqueo=puede.motivos_bloqueo,
    )


def anular_registro(
    data: AppData | None,
    registro_id: str,
    tipo_registro: str,
    motivo: str,
    referencia: str = "",
    *,
    ctx: AppContext | None = None,
) -> ResultadoAnulacion:
    """Anula y repone stock. Todo o nada. Idempotente si ya anulado."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_REGISTRO, deny_terminal=True)
    if denied:
        return ResultadoAnulacion(False, denied)

    context, data = _context(data, ctx)
    motivo_limpio = (motivo or "").strip()
    if not motivo_limpio:
        return ResultadoAnulacion(False, "El motivo de anulación es obligatorio.")

    registro = _buscar_registro(data, registro_id, tipo_registro)
    if registro is None:
        return ResultadoAnulacion(False, f"Registro «{registro_id}» no encontrado.")

    if registro_esta_anulado(registro):
        return ResultadoAnulacion(False, "Registro ya anulado.")

    puede = puede_anular_registro(data, registro, tipo=tipo_registro)
    if not puede.ok:
        return ResultadoAnulacion(
            False,
            "No se puede anular: " + " ".join(puede.motivos_bloqueo),
        )

    # Re-check inmediato antes de mutar
    if registro_esta_anulado(registro):
        return ResultadoAnulacion(False, "Registro ya anulado.")

    snap_lotes = snapshot_cantidades_restantes(data)
    snap_anulado = (
        registro.anulado,
        registro.fecha_anulacion,
        registro.hora_anulacion,
        registro.motivo_anulacion,
        registro.referencia_anulacion,
        registro.anulado_por,
    )
    n_actividades = len(data.actividades)
    if not hasattr(data, "movimientos") or data.movimientos is None:
        data.movimientos = []
    n_movimientos = len(data.movimientos)
    por_lote = _aggregar_devoluciones(registro)
    lotes = {l.id: l for l in data.lotes}

    try:
        for lote_id, qty in por_lote.items():
            lote = lotes.get(lote_id)
            if lote is None:
                raise ValueError(f"Lote desapareció durante la anulación: {lote_id}.")
            lote.cantidad_restante = round(lote.cantidad_restante + qty, 4)

        ahora = context.clock.now()
        registro.anulado = True
        registro.fecha_anulacion = ahora.date()
        registro.hora_anulacion = ahora.time().replace(microsecond=0)
        registro.motivo_anulacion = motivo_limpio
        registro.referencia_anulacion = (referencia or "").strip()
        registro.anulado_por = context.actor.nombre

        from app.core.services import movimiento_service as mov_svc

        mov_svc.escribir_espejos_reversion_consumo_registro(
            registro_id=registro_id,
            lineas_detalle=list(getattr(registro, "lineas_detalle", None) or []),
            fecha=registro.fecha_anulacion or ahora.date(),
            hora=registro.hora_anulacion,
            usuario_id=context.actor.id or None,
            ctx=context,
        )

        etiqueta = (
            "Desayuno"
            if tipo_registro == TIPO_DESAYUNO
            else getattr(registro, "tipo_servicio", "servicio")
        )
        _registrar_actividad(
            context,
            "Anulación registro",
            (
                f"Anulado {etiqueta} {registro_id} — motivo: {motivo_limpio}"
                + (f" — ref: {referencia}" if referencia else "")
            ),
        )
        context.uow.commit(data)
    except Exception as exc:
        restaurar_cantidades_restantes(data, snap_lotes)
        (
            registro.anulado,
            registro.fecha_anulacion,
            registro.hora_anulacion,
            registro.motivo_anulacion,
            registro.referencia_anulacion,
            registro.anulado_por,
        ) = snap_anulado
        del data.movimientos[n_movimientos:]
        if len(data.actividades) > n_actividades:
            del data.actividades[n_actividades:]
        return ResultadoAnulacion(False, f"Anulación fallida; estado restaurado. ({exc})")

    from app.core.services.alert_service import sincronizar_alertas
    sincronizar_alertas(context)

    return ResultadoAnulacion(
        True,
        f"Registro {registro_id} anulado. Stock repuesto en {len(por_lote)} lote(s).",
    )


def anular_desayuno(
    registro_id: str,
    motivo: str,
    referencia: str = "",
    *,
    ctx: AppContext | None = None,
) -> ResultadoAnulacion:
    return anular_registro(
        None, registro_id, TIPO_DESAYUNO, motivo, referencia, ctx=ctx,
    )


def anular_servicio(
    registro_id: str,
    motivo: str,
    referencia: str = "",
    *,
    ctx: AppContext | None = None,
) -> ResultadoAnulacion:
    return anular_registro(
        None, registro_id, TIPO_SERVICIO, motivo, referencia, ctx=ctx,
    )
