"""Recuentos de inventario por ubicación (Fase 7B.6).

La diferencia confirmada genera ajuste_entrada / ajuste_salida vía ledger.
No sobrescribe el saldo directamente.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.core.application.context import AppContext
from app.core.application.id_generator import next_id
from app.core.models import Actividad, AppData, LineaAjuste, RegistroAjuste
from app.core.models.enums import MotivoAjuste
from app.core.models.recuento import EstadoRecuento, LineaRecuento, SesionRecuento
from app.core.services import movimiento_service as mov
from app.core.services.inventory_batch_service import (
    restaurar_cantidades_restantes,
    snapshot_cantidades_restantes,
)
from app.core.services.ubicacion_stock_service import (
    saldo_en_ubicacion,
    validar_ubicacion_catalogo,
)
from app.core.storage.session_store import get_data, persist_data


@dataclass
class ResultadoRecuento:
    ok: bool
    mensaje: str
    sesion: SesionRecuento | None = None


def _ctx_session() -> AppContext:
    from app.core.application.context import build_app_context
    from app.core.application.unit_of_work import InMemoryUnitOfWork

    return build_app_context(uow=InMemoryUnitOfWork(get_data()))


def _estado_val(s: SesionRecuento) -> str:
    e = s.estado
    return e.value if hasattr(e, "value") else str(e)


def crear_borrador(
    *,
    ubicacion_id: str,
    lineas: list[tuple[str, str, float]],  # lote_id, producto_id, contada
    fecha: date | None = None,
    motivo: str | None = None,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoRecuento:
    c = ctx or _ctx_session()
    data = c.uow.get_data()
    if not hasattr(data, "recuentos") or data.recuentos is None:
        data.recuentos = []

    err = validar_ubicacion_catalogo(data, ubicacion_id)
    if err:
        return ResultadoRecuento(False, err)

    if not lineas:
        return ResultadoRecuento(False, "El recuento requiere al menos una línea.")

    lineas_modelo: list[LineaRecuento] = []
    snap: dict[str, float] = {}
    for lote_id, producto_id, contada in lineas:
        try:
            cont = float(contada)
        except (TypeError, ValueError):
            return ResultadoRecuento(False, f"Cantidad contada inválida en {lote_id}")
        if cont < 0:
            return ResultadoRecuento(False, "No se permiten cantidades negativas.")
        lote = next((l for l in data.lotes if l.id == lote_id), None)
        if lote is None:
            return ResultadoRecuento(False, f"Lote inexistente: {lote_id}")
        if lote.producto_id != producto_id:
            return ResultadoRecuento(False, f"Producto no coincide con lote {lote_id}")
        esperado = saldo_en_ubicacion(data, lote_id, ubicacion_id)
        prod = next((p for p in data.productos if p.id == producto_id), None)
        lineas_modelo.append(
            LineaRecuento(
                producto_id=producto_id,
                lote_id=lote_id,
                cantidad_esperada=round(esperado, 4),
                cantidad_contada=round(cont, 4),
                producto_nombre_snapshot=prod.nombre if prod else None,
                unidad_snapshot=(
                    prod.unidad.value if prod and hasattr(prod.unidad, "value") else None
                ),
            )
        )
        snap[lote_id] = round(esperado, 4)

    sesion = SesionRecuento(
        id=next_id("rc", [r.id for r in data.recuentos]),
        ubicacion_id=ubicacion_id,
        fecha=fecha or (
            c.clock.today() if getattr(c, "clock", None) else date.today()
        ),
        usuario_id=getattr(getattr(c, "actor", None), "id", None),
        estado=EstadoRecuento.BORRADOR,
        motivo=motivo,
        lineas=lineas_modelo,
        hora=c.clock.now().time() if getattr(c, "clock", None) else None,
        creado_en=datetime.now(),
        snapshot_esperado=snap,
    )
    data.recuentos.append(sesion)
    if commit:
        c.uow.commit(data)
        if ctx is None:
            persist_data(data)
    return ResultadoRecuento(True, f"Recuento borrador {sesion.id} creado.", sesion)


def preview_confirmacion(sesion: SesionRecuento) -> list[str]:
    lineas = []
    for ln in sesion.lineas:
        diff = ln.diferencia
        if abs(diff) < 1e-9:
            continue
        tipo = "ajuste_entrada" if diff > 0 else "ajuste_salida"
        lineas.append(
            f"{ln.lote_id}: esperado {ln.cantidad_esperada:g} → "
            f"contado {ln.cantidad_contada:g} (Δ {diff:+g}) → {tipo}"
        )
    if not lineas:
        lineas.append("Sin diferencias: no se generarán ajustes.")
    return lineas


def confirmar_recuento(
    *,
    recuento_id: str,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoRecuento:
    c = ctx or _ctx_session()
    data = c.uow.get_data()
    sesion = next((r for r in data.recuentos if r.id == recuento_id), None)
    if sesion is None:
        return ResultadoRecuento(False, "Recuento no encontrado.")
    if _estado_val(sesion) != EstadoRecuento.BORRADOR.value:
        return ResultadoRecuento(False, "Solo se confirman borradores.")

    preview = preview_confirmacion(sesion)
    snap = snapshot_cantidades_restantes(data)
    n_aj = len(data.ajustes)
    n_mov = len(getattr(data, "movimientos", []) or [])
    n_act = len(data.actividades)
    try:
        for ln in sesion.lineas:
            diff = ln.diferencia
            if abs(diff) < 1e-9:
                continue
            lote = next(l for l in data.lotes if l.id == ln.lote_id)
            antes = float(lote.cantidad_restante)
            despues = round(antes + diff, 4)
            if despues < -1e-9:
                raise RuntimeError(
                    f"El ajuste dejaría stock hotel negativo en {ln.lote_id}."
                )
            lote.cantidad_restante = max(despues, 0.0)
            linea_aj = LineaAjuste(
                producto_id=ln.producto_id,
                lote_id=ln.lote_id,
                cantidad_antes=antes,
                cantidad_despues=lote.cantidad_restante,
                motivo=MotivoAjuste.RECONTEO_FISICO,
                comentario=sesion.motivo or f"Recuento {sesion.id}",
                producto_nombre_snapshot=ln.producto_nombre_snapshot,
                unidad_snapshot=ln.unidad_snapshot,
            )
            registro = RegistroAjuste(
                next_id("aj", [a.id for a in data.ajustes]),
                sesion.fecha,
                [linea_aj],
                getattr(getattr(c, "actor", None), "nombre", None) or "Sistema",
                hora=sesion.hora,
            )
            data.ajustes.append(registro)
            ln.ajuste_id = registro.id

            espejo = mov.espejo_ajuste_linea(
                producto_id=ln.producto_id,
                lote_id=ln.lote_id,
                delta=diff,
                fecha=sesion.fecha,
                ajuste_id=registro.id,
                origen_linea_id=ln.lote_id,
                hora=sesion.hora,
                usuario_id=sesion.usuario_id,
                ubicacion_origen_id=sesion.ubicacion_id if diff < 0 else None,
                ubicacion_destino_id=sesion.ubicacion_id if diff > 0 else None,
                ctx=c,
                commit=False,
            )
            if not espejo.ok and not espejo.duplicado:
                raise RuntimeError(espejo.mensaje)

        sesion.estado = EstadoRecuento.CONFIRMADO
        sesion.confirmado_en = datetime.now()
        data.actividades.insert(
            0,
            Actividad(
                next_id("act", [a.id for a in data.actividades]),
                datetime.now(),
                getattr(getattr(c, "actor", None), "nombre", None) or "Sistema",
                "Confirmación recuento",
                f"{sesion.id} en {sesion.ubicacion_id}: " + "; ".join(preview[:3]),
            ),
        )
        if commit:
            c.uow.commit(data)
            if ctx is None:
                persist_data(data)
        return ResultadoRecuento(True, f"Recuento {sesion.id} confirmado.", sesion)
    except Exception as exc:  # noqa: BLE001
        restaurar_cantidades_restantes(data, snap)
        del data.ajustes[n_aj:]
        del data.movimientos[n_mov:]
        del data.actividades[n_act:]
        sesion.estado = EstadoRecuento.BORRADOR
        for ln in sesion.lineas:
            ln.ajuste_id = None
        return ResultadoRecuento(False, f"Confirmación abortada: {exc}", sesion)


def anular_recuento(
    *,
    recuento_id: str,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoRecuento:
    """Anula confirmado generando ajustes inversos (reversos). Borrador → anulado sin movimientos."""
    c = ctx or _ctx_session()
    data = c.uow.get_data()
    sesion = next((r for r in data.recuentos if r.id == recuento_id), None)
    if sesion is None:
        return ResultadoRecuento(False, "Recuento no encontrado.")
    estado = _estado_val(sesion)
    if estado == EstadoRecuento.ANULADO.value:
        return ResultadoRecuento(False, "Ya está anulado.")
    if estado == EstadoRecuento.BORRADOR.value:
        sesion.estado = EstadoRecuento.ANULADO
        sesion.anulado_en = datetime.now()
        if commit:
            c.uow.commit(data)
            if ctx is None:
                persist_data(data)
        return ResultadoRecuento(True, f"Borrador {sesion.id} anulado.", sesion)

    snap = snapshot_cantidades_restantes(data)
    n_aj = len(data.ajustes)
    n_mov = len(data.movimientos)
    n_act = len(data.actividades)
    try:
        for ln in sesion.lineas:
            diff = ln.diferencia
            if abs(diff) < 1e-9:
                continue
            revert = -diff
            lote = next(l for l in data.lotes if l.id == ln.lote_id)
            antes = float(lote.cantidad_restante)
            lote.cantidad_restante = round(antes + revert, 4)
            registro = RegistroAjuste(
                next_id("aj", [a.id for a in data.ajustes]),
                sesion.fecha,
                [
                    LineaAjuste(
                        producto_id=ln.producto_id,
                        lote_id=ln.lote_id,
                        cantidad_antes=antes,
                        cantidad_despues=lote.cantidad_restante,
                        motivo=MotivoAjuste.OTRO,
                        comentario=f"Anulación recuento {sesion.id}",
                        producto_nombre_snapshot=ln.producto_nombre_snapshot,
                        unidad_snapshot=ln.unidad_snapshot,
                    )
                ],
                getattr(getattr(c, "actor", None), "nombre", None) or "Sistema",
            )
            data.ajustes.append(registro)
            espejo = mov.espejo_ajuste_linea(
                producto_id=ln.producto_id,
                lote_id=ln.lote_id,
                delta=revert,
                fecha=date.today(),
                ajuste_id=registro.id,
                origen_linea_id=f"anular:{ln.lote_id}",
                usuario_id=sesion.usuario_id,
                ubicacion_origen_id=sesion.ubicacion_id if revert < 0 else None,
                ubicacion_destino_id=sesion.ubicacion_id if revert > 0 else None,
                ctx=c,
                commit=False,
            )
            if not espejo.ok and not espejo.duplicado:
                raise RuntimeError(espejo.mensaje)
        sesion.estado = EstadoRecuento.ANULADO
        sesion.anulado_en = datetime.now()
        if commit:
            c.uow.commit(data)
            if ctx is None:
                persist_data(data)
        return ResultadoRecuento(True, f"Recuento {sesion.id} anulado con reversos.", sesion)
    except Exception as exc:  # noqa: BLE001
        restaurar_cantidades_restantes(data, snap)
        del data.ajustes[n_aj:]
        del data.movimientos[n_mov:]
        del data.actividades[n_act:]
        return ResultadoRecuento(False, f"Anulación abortada: {exc}", sesion)


def listar_recuentos_pendientes(data: AppData) -> list[SesionRecuento]:
    return [
        r
        for r in getattr(data, "recuentos", []) or []
        if _estado_val(r) == EstadoRecuento.BORRADOR.value
    ]
