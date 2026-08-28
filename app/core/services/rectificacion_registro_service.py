"""Rectificación de registros de servicio/desayuno ya guardados.

Permite sumar, quitar o cambiar cantidades (como un albarán editable):
1) Devuelve el stock del consumo original.
2) Sustituye líneas.
3) Vuelve a descontar FIFO (permite stock negativo).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.application.context import AppContext
from app.core.models import AppData, LineaDetalleOrigen, OrigenConsumo
from app.core.models.desayuno import LineaDesayuno
from app.core.models.registro_servicio import LineaServicio
from app.core.repositories.data_repository import DataRepository
from app.core.services.data_service import get_app_context
from app.core.services.anulacion_registro_service import (
    TIPO_DESAYUNO,
    TIPO_SERVICIO,
    _aggregar_devoluciones,
    _buscar_registro,
    _registrar_actividad,
    puede_anular_registro,
    registro_esta_anulado,
)
from app.core.services.detalle_origen_service import (
    asignar_consumos_lote,
    asignar_costes_proporcionales,
    validar_consumos_lote,
)
from app.core.services.inventory_batch_service import (
    restaurar_cantidades_restantes,
    snapshot_cantidades_restantes,
)


@dataclass
class ResultadoRectificacion:
    ok: bool
    mensaje: str
    codigo: str | None = None


@dataclass
class LineaRectificacion:
    producto_id: str
    cantidad: float
    nombre: str = ""
    unidad: str = ""


def _context(ctx: AppContext | None = None) -> tuple[AppContext, AppData]:
    app_ctx = ctx or get_app_context()
    return app_ctx, app_ctx.data()


def lineas_actuales_registro(
    registro_id: str,
    *,
    tipo_registro: str = TIPO_SERVICIO,
    ctx: AppContext | None = None,
) -> list[LineaRectificacion]:
    """Agrega cantidades por producto a partir del detalle (o líneas legacy)."""
    _, data = _context(ctx=ctx)
    registro = _buscar_registro(data, registro_id, tipo_registro)
    if registro is None:
        return []
    repo = DataRepository(data)
    por_pid: dict[str, float] = {}
    for det in getattr(registro, "lineas_detalle", None) or []:
        if float(getattr(det, "cantidad", 0) or 0) <= 0:
            continue
        pid = str(det.producto_id)
        por_pid[pid] = round(por_pid.get(pid, 0.0) + float(det.cantidad), 4)
    if not por_pid:
        for lin in getattr(registro, "lineas", None) or []:
            if float(getattr(lin, "cantidad", 0) or 0) <= 0:
                continue
            pid = str(lin.producto_id)
            por_pid[pid] = round(por_pid.get(pid, 0.0) + float(lin.cantidad), 4)
    out: list[LineaRectificacion] = []
    for pid, qty in sorted(por_pid.items()):
        prod = repo.get_producto(pid)
        out.append(
            LineaRectificacion(
                producto_id=pid,
                cantidad=qty,
                nombre=prod.nombre if prod else pid,
                unidad=prod.unidad.value if prod else "",
            )
        )
    return out


def rectificar_lineas_registro(
    registro_id: str,
    lineas: list[tuple[str, float]] | list[LineaRectificacion],
    *,
    tipo_registro: str = TIPO_SERVICIO,
    ctx: AppContext | None = None,
) -> ResultadoRectificacion:
    """Sustituye el consumo del registro por las líneas indicadas."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.session import TERMINAL_ID_DEFAULT
    from app.core.auth.usecase_guard import usecase_deny_message
    from app.core.application.inventory_ops import aplicar_descuento_atomico
    from app.core.services import movimiento_service as mov_svc

    denied = usecase_deny_message(
        Permiso.ACCEDER_REGISTRO,
        deny_terminal=True,
        allowed_terminals=frozenset({TERMINAL_ID_DEFAULT}),
    )
    if denied:
        return ResultadoRectificacion(False, denied)

    context, data = _context(ctx=ctx)
    registro = _buscar_registro(data, registro_id, tipo_registro)
    if registro is None:
        return ResultadoRectificacion(False, f"Registro «{registro_id}» no encontrado.")
    if registro_esta_anulado(registro):
        return ResultadoRectificacion(False, "No se puede editar un registro anulado.")
    puede = puede_anular_registro(data, registro, tipo=tipo_registro)
    if not puede.ok:
        return ResultadoRectificacion(
            False,
            "No se puede editar: " + " ".join(puede.motivos_bloqueo),
        )

    demandas: dict[str, float] = {}
    for item in lineas:
        if isinstance(item, LineaRectificacion):
            pid, qty = item.producto_id, float(item.cantidad)
        else:
            pid, qty = str(item[0]), float(item[1])
        pid = (pid or "").strip()
        if not pid or qty <= 0:
            continue
        demandas[pid] = round(demandas.get(pid, 0.0) + qty, 4)
    if not demandas:
        return ResultadoRectificacion(False, "Debe quedar al menos una línea con cantidad > 0.")

    repo = DataRepository(data)
    for pid in demandas:
        if repo.get_producto(pid) is None:
            return ResultadoRectificacion(False, f"Producto no encontrado: {pid}.")

    snap = snapshot_cantidades_restantes(data)
    if not hasattr(data, "movimientos") or data.movimientos is None:
        data.movimientos = []
    n_movimientos = len(data.movimientos)
    n_actividades = len(data.actividades)

    old_lineas = list(getattr(registro, "lineas", None) or [])
    old_detalle = list(getattr(registro, "lineas_detalle", None) or [])
    old_coste = float(getattr(registro, "coste_total", 0) or 0)
    old_recetas = list(getattr(registro, "registros_recetas", None) or [])

    try:
        por_lote = _aggregar_devoluciones(registro)
        lotes = {l.id: l for l in data.lotes}
        for lote_id, qty in por_lote.items():
            lote = lotes.get(lote_id)
            if lote is None:
                raise ValueError(f"Lote desapareció al rectificar: {lote_id}.")
            lote.cantidad_restante = round(lote.cantidad_restante + qty, 4)

        mov_svc.escribir_espejos_reversion_consumo_registro(
            registro_id=registro_id,
            lineas_detalle=old_detalle,
            fecha=context.clock.today(),
            hora=context.clock.now().time().replace(microsecond=0),
            usuario_id=context.actor.id or None,
            ctx=context,
        )

        resultado_desc = aplicar_descuento_atomico(
            context, demandas, permitir_negativo=True,
        )
        costes = resultado_desc.costes

        if tipo_registro == TIPO_DESAYUNO:
            tipo_svc = "desayuno"
            nuevas_lineas = [
                LineaDesayuno(pid, demandas[pid], costes.get(pid, 0.0), False)
                for pid in demandas
            ]
            origen_tipo = mov_svc.ORIGEN_TIPO_DESAYUNO
        else:
            tipo_svc = str(getattr(registro, "tipo_servicio", "") or "comida")
            nuevas_lineas = [
                LineaServicio(pid, demandas[pid], costes.get(pid, 0.0), False)
                for pid in demandas
            ]
            origen_tipo = mov_svc.ORIGEN_TIPO_REGISTRO_SERVICIO

        nuevas_detalle: list[LineaDetalleOrigen] = []
        for pid, qty in demandas.items():
            prod = repo.get_producto(pid)
            nuevas_detalle.append(
                LineaDetalleOrigen(
                    origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                    producto_id=pid,
                    cantidad=qty,
                    registro_origen_id=registro_id,
                    tipo_servicio=tipo_svc,
                    categoria_receta=None,
                    es_bebida_snapshot=bool(prod.es_bebida) if prod else False,
                    categoria_receta_snapshot=None,
                )
            )
        asignar_costes_proporcionales(nuevas_detalle, costes, dict(demandas))
        asignar_consumos_lote(nuevas_detalle, resultado_desc.movimientos)
        validar_consumos_lote(
            nuevas_detalle, resultado_desc.movimientos, costes, data,
        )

        registro.lineas = nuevas_lineas
        registro.lineas_detalle = nuevas_detalle
        registro.coste_total = round(sum(l.coste for l in nuevas_lineas), 2)
        if hasattr(registro, "registros_recetas"):
            registro.registros_recetas = []

        mov_svc.escribir_espejos_consumo_registro(
            origen_tipo=origen_tipo,
            registro_id=registro_id,
            lineas_detalle=nuevas_detalle,
            fecha=getattr(registro, "fecha", None) or context.clock.today(),
            hora=getattr(registro, "hora", None)
            or context.clock.now().time().replace(microsecond=0),
            usuario_id=context.actor.id or None,
            ctx=context,
        )

        _registrar_actividad(
            context,
            "Rectificar registro",
            f"{tipo_registro}:{registro_id} — {len(demandas)} línea(s)",
        )
        context.uow.commit(data)
    except Exception as exc:  # noqa: BLE001
        restaurar_cantidades_restantes(data, snap)
        registro.lineas = old_lineas
        registro.lineas_detalle = old_detalle
        registro.coste_total = old_coste
        if hasattr(registro, "registros_recetas"):
            registro.registros_recetas = old_recetas
        del data.movimientos[n_movimientos:]
        del data.actividades[n_actividades:]
        return ResultadoRectificacion(False, f"No se pudo rectificar: {exc}")

    return ResultadoRectificacion(
        True,
        f"Registro {registro_id} actualizado ({len(demandas)} línea(s)).",
    )
