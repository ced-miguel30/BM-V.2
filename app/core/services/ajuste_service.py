"""Ajustes de inventario — extensión mínima (Fase 10).

Solo muta `lote.cantidad_restante`. No altera compras históricas
(`precio_total`, `cantidad` original, fechas, proveedor).
Atomicidad: snapshot → aplicar → persistir; fallo restaura.

Fase 4C: operaciones vía AppContext (UoW, reloj, actor, auditoría).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from app.core.application.context import AppContext, build_app_context
from app.core.application.id_generator import next_id
from app.core.models import (
    AppData,
    LineaAjuste,
    LoteStock,
    MotivoAjuste,
    RegistroAjuste,
)
from app.core.repositories.data_repository import DataRepository
from app.core.services.formatting import formato_fecha
from app.core.services.inventory_batch_service import (
    restaurar_cantidades_restantes,
    snapshot_cantidades_restantes,
)

MOTIVOS_AJUSTE = [m.value for m in MotivoAjuste]


@dataclass
class ResultadoOperacion:
    ok: bool
    mensaje: str


@dataclass
class PreviewLineaAjuste:
    lote_id: str
    producto_id: str
    nombre: str
    unidad: str
    cantidad_antes: float
    cantidad_despues: float
    delta: float
    motivo: str
    comentario: str | None
    # Campos de compra (solo lectura en preview; no se tocan).
    cantidad_compra: float
    precio_total: float
    fecha_compra_txt: str


def _ctx(ctx: AppContext | None = None) -> AppContext:
    return ctx if ctx is not None else build_app_context()


def _registrar_actividad(ctx: AppContext, accion: str, detalle: str) -> None:
    from app.core.application.auditoria import registrar_actividad

    registrar_actividad(ctx, accion, detalle, commit=False)


def _get_lote(data: AppData, lote_id: str) -> LoteStock | None:
    return next((l for l in data.lotes if l.id == lote_id), None)


def lotes_ajustables(
    producto_id: str | None = None,
    *,
    ctx: AppContext | None = None,
) -> list[dict]:
    """Lotes existentes para selector de ajuste (incluye restante 0)."""
    data = _ctx(ctx).data()
    repo = DataRepository(data)
    out: list[dict] = []
    for lote in sorted(
        data.lotes,
        key=lambda l: (l.fecha_compra or date.min, l.id),
        reverse=True,
    ):
        if getattr(lote, "anulado", False):
            continue
        if producto_id and lote.producto_id != producto_id:
            continue
        producto = repo.get_producto(lote.producto_id)
        if not producto:
            continue
        out.append({
            "id": lote.id,
            "producto_id": lote.producto_id,
            "label": (
                f"{producto.nombre} · {lote.id} · "
                f"restante {lote.cantidad_restante:g} {producto.unidad.value} · "
                f"compra {formato_fecha(lote.fecha_compra)}"
            ),
            "restante": lote.cantidad_restante,
            "unidad": producto.unidad.value,
            "nombre": producto.nombre,
        })
    return out


def previsualizar_ajuste(
    lote_id: str,
    cantidad_despues: float,
    motivo: str,
    comentario: str | None = None,
    *,
    ctx: AppContext | None = None,
) -> tuple[PreviewLineaAjuste | None, str | None]:
    """Devuelve preview o (None, error). No muta datos."""
    data = _ctx(ctx).data()
    repo = DataRepository(data)
    lote = _get_lote(data, lote_id)
    if not lote:
        return None, "Lote no encontrado."
    producto = repo.get_producto(lote.producto_id)
    if not producto:
        return None, "El producto del lote ya no existe en el catálogo."
    try:
        nueva = float(cantidad_despues)
    except (TypeError, ValueError):
        return None, "Indique una cantidad válida."
    if nueva < 0:
        return None, "La cantidad resultante no puede ser negativa."
    if motivo not in MOTIVOS_AJUSTE:
        return None, "Seleccione un motivo de ajuste válido."
    antes = round(float(lote.cantidad_restante), 4)
    despues = round(nueva, 4)
    if abs(despues - antes) < 1e-9:
        return None, "La cantidad nueva es igual a la actual; no hay ajuste."
    comentario_limpio = (comentario or "").strip() or None
    preview = PreviewLineaAjuste(
        lote_id=lote.id,
        producto_id=lote.producto_id,
        nombre=producto.nombre,
        unidad=producto.unidad.value,
        cantidad_antes=antes,
        cantidad_despues=despues,
        delta=round(despues - antes, 4),
        motivo=motivo,
        comentario=comentario_limpio,
        cantidad_compra=lote.cantidad,
        precio_total=lote.precio_total,
        fecha_compra_txt=formato_fecha(lote.fecha_compra),
    )
    return preview, None


def aplicar_ajuste(
    fecha: date,
    lote_id: str,
    cantidad_despues: float,
    motivo: str,
    comentario: str | None = None,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    """Aplica un ajuste de una línea con atomicidad (todo o nada)."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
    if denied:
        return ResultadoOperacion(False, denied)

    context = _ctx(ctx)
    if fecha > context.clock.today():
        return ResultadoOperacion(False, "No puede registrar ajustes en fechas futuras.")

    preview, error = previsualizar_ajuste(
        lote_id, cantidad_despues, motivo, comentario, ctx=context,
    )
    if error or preview is None:
        return ResultadoOperacion(False, error or "No se pudo preparar el ajuste.")

    data = context.data()
    lote = _get_lote(data, lote_id)
    if not lote:
        return ResultadoOperacion(False, "Lote no encontrado.")

    # Guardar campos de compra para comprobar que no se tocan.
    compra_snap = (lote.cantidad, lote.precio_total, lote.fecha_compra, lote.marca_proveedor)

    linea = LineaAjuste(
        producto_id=preview.producto_id,
        lote_id=preview.lote_id,
        cantidad_antes=preview.cantidad_antes,
        cantidad_despues=preview.cantidad_despues,
        motivo=MotivoAjuste(preview.motivo),
        comentario=preview.comentario,
        producto_nombre_snapshot=preview.nombre,
        unidad_snapshot=preview.unidad,
    )

    snap = snapshot_cantidades_restantes(data)
    n_ajustes = len(data.ajustes)
    n_actividades = len(data.actividades)
    if not hasattr(data, "movimientos") or data.movimientos is None:
        data.movimientos = []
    n_movimientos = len(data.movimientos)
    try:
        lote.cantidad_restante = preview.cantidad_despues
        if (
            lote.cantidad,
            lote.precio_total,
            lote.fecha_compra,
            lote.marca_proveedor,
        ) != compra_snap:
            raise RuntimeError("Intento de alterar datos de compra; abortado.")

        registro = RegistroAjuste(
            next_id("aj", [a.id for a in data.ajustes]),
            fecha,
            [linea],
            context.actor.nombre,
            hora=context.clock.now().time(),
        )
        data.ajustes.append(registro)

        from app.core.services import movimiento_service as mov_svc
        from app.core.services.ubicacion_stock_service import ubicacion_preferida_lote

        ubi = ubicacion_preferida_lote(data, preview.lote_id)
        espejo = mov_svc.espejo_ajuste_linea(
            producto_id=preview.producto_id,
            lote_id=preview.lote_id,
            delta=linea.delta,
            fecha=fecha,
            ajuste_id=registro.id,
            origen_linea_id=preview.lote_id,
            hora=registro.hora,
            usuario_id=context.actor.id or None,
            ubicacion_origen_id=ubi if linea.delta < 0 else None,
            ubicacion_destino_id=ubi if linea.delta > 0 else None,
            ctx=context,
            commit=False,
        )
        if not espejo.ok and not espejo.duplicado:
            raise RuntimeError(
                f"No se pudo registrar el espejo de ledger: {espejo.mensaje}"
            )

        signo = "+" if linea.delta >= 0 else ""
        _registrar_actividad(
            context,
            "Ajuste inventario",
            (
                f"{preview.nombre} lote {lote_id}: "
                f"{preview.cantidad_antes:g} → {preview.cantidad_despues:g} "
                f"{preview.unidad} ({signo}{linea.delta:g}) — {preview.motivo}"
            ),
        )
        context.uow.commit(data)
    except Exception:
        restaurar_cantidades_restantes(data, snap)
        del data.ajustes[n_ajustes:]
        del data.movimientos[n_movimientos:]
        if len(data.actividades) > n_actividades:
            del data.actividades[n_actividades:]
        raise

    from app.core.services.alert_service import sincronizar_alertas
    sincronizar_alertas(context)

    return ResultadoOperacion(
        True,
        (
            f"Ajuste registrado: «{preview.nombre}» "
            f"{preview.cantidad_antes:g} → {preview.cantidad_despues:g} {preview.unidad}."
        ),
    )


def historial_ordenado(*, ctx: AppContext | None = None) -> list[RegistroAjuste]:
    data = _ctx(ctx).data()
    return sorted(
        data.ajustes,
        key=lambda a: (a.fecha, a.hora or time.min),
        reverse=True,
    )
