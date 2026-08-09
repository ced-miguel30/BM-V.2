"""Caducidad operativa — listados y salida via merma (motivo Expiración).

No introduce entidad Caducidad. La salida confirmada reutiliza merma_service
con MotivoMerma.EXPIRACION.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.application.context import AppContext
from app.core.models import AppData, LoteStock, MotivoMerma
from app.core.repositories.data_repository import DataRepository
from app.core.services.alert_service import DIAS_EXPIRACION_DEFECTO
from app.core.storage.session_store import get_data

MOTIVO_CADUCIDAD = MotivoMerma.EXPIRACION.value


@dataclass(frozen=True)
class LoteCaducidad:
    lote_id: str
    producto_id: str
    nombre_producto: str
    unidad: str
    cantidad_restante: float
    fecha_expiracion: date
    dias_restantes: int
    estado: str  # "vencido" | "proximo"
    umbral_alerta_dias: int


def _ctx(ctx: AppContext | None):
    if ctx is not None:
        return ctx
    from app.core.application.context import build_app_context
    from app.core.application.unit_of_work import SessionUnitOfWork

    return build_app_context(uow=SessionUnitOfWork())


def _data(ctx: AppContext | None = None) -> AppData:
    if ctx is not None:
        return ctx.data()
    return get_data()


def listar_lotes_caducidad(
    *,
    hoy: date | None = None,
    incluir_proximos: bool = True,
    incluir_vencidos: bool = True,
    ctx: AppContext | None = None,
) -> list[LoteCaducidad]:
    """Lotes con fecha de caducidad y stock > 0 (no anulados)."""
    context = _ctx(ctx) if ctx is not None else None
    data = _data(ctx)
    repo = DataRepository(data)
    ref = hoy or (context.clock.today() if context else date.today())
    resultado: list[LoteCaducidad] = []

    for lote in data.lotes:
        if getattr(lote, "anulado", False):
            continue
        if lote.cantidad_restante <= 0 or not lote.fecha_expiracion:
            continue
        producto = repo.get_producto(lote.producto_id)
        if not producto or not getattr(producto, "activo", True):
            continue
        umbral = lote.alerta_expiracion_dias or DIAS_EXPIRACION_DEFECTO
        dias = (lote.fecha_expiracion - ref).days
        if dias < 0:
            if not incluir_vencidos:
                continue
            estado = "vencido"
        elif dias <= umbral:
            if not incluir_proximos:
                continue
            estado = "proximo"
        else:
            continue
        resultado.append(LoteCaducidad(
            lote_id=lote.id,
            producto_id=producto.id,
            nombre_producto=producto.nombre,
            unidad=producto.unidad.value,
            cantidad_restante=round(float(lote.cantidad_restante), 4),
            fecha_expiracion=lote.fecha_expiracion,
            dias_restantes=dias,
            estado=estado,
            umbral_alerta_dias=int(umbral),
        ))

    resultado.sort(key=lambda x: (x.dias_restantes, x.nombre_producto, x.lote_id))
    return resultado


def registrar_salida_caducidad(
    lote_id: str,
    cantidad: float,
    *,
    tipo_servicio_snapshot: str,
    turno_snapshot: str,
    responsable_id: str,
    responsable_nombre: str | None = None,
    comentario: str | None = None,
    ctx: AppContext | None = None,
):
    """Prefill + no: añade a cesta merma con motivo Expiración.

    La confirmación atómica la hace ``registrar_merma`` (idempotencia/cesta).
    """
    from app.core.services import merma_service as merma

    return merma.anadir_a_cesta_merma(
        lote_id,
        cantidad,
        MOTIVO_CADUCIDAD,
        tipo_servicio_snapshot,
        comentario=comentario or "Salida por caducidad",
        turno_snapshot=turno_snapshot,
        responsable_id=responsable_id,
        responsable_nombre=responsable_nombre,
        ctx=ctx,
    )


def obtener_lote(data: AppData, lote_id: str) -> LoteStock | None:
    return next((l for l in data.lotes if l.id == lote_id), None)
