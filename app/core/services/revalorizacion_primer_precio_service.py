"""Revalorización única al primer precio de compra (D60).

La primera entrada de stock por albarán/factura de un producto reescribe
costes de consumos ya registrados y lotes provisionales (sin documento).
Las entradas posteriores solo crean lotes FIFO con su propio coste.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.core.application.id_generator import next_id
from app.core.models import Actividad, AppData, TipoDocumento
from app.core.models.enums import TipoMovimiento
from app.core.services.money import as_decimal, money_round
from app.core.services import movimiento_service as mov_svc

_TIPOS_COMPRA = frozenset(
    {
        TipoDocumento.ALBARAN.value,
        TipoDocumento.FACTURA.value,
        "albaran",
        "factura",
    }
)


@dataclass
class ResumenRevalorizacion:
    producto_id: str
    coste_unitario: float
    doc_id: str
    registros_desayuno: int = 0
    registros_servicio: int = 0
    registros_merma: int = 0
    fragmentos_actualizados: int = 0
    lineas_actualizadas: int = 0
    lotes_provisionales: int = 0
    movimientos_actualizados: int = 0


def _tipo_doc_value(doc: Any) -> str:
    t = getattr(doc, "tipo", None)
    if t is None:
        return ""
    return t.value if hasattr(t, "value") else str(t)


def _enum_val(v: Any) -> str:
    return v.value if hasattr(v, "value") else str(v)


def producto_tiene_lote_de_compra(data: AppData, producto_id: str) -> bool:
    """True si ya existe un lote de albarán/factura para el producto."""
    docs = {d.id: d for d in (getattr(data, "documentos", None) or [])}
    for lote in data.lotes:
        if lote.producto_id != producto_id:
            continue
        if getattr(lote, "anulado", False):
            continue
        doc_id = getattr(lote, "documento_origen_id", None)
        if not doc_id:
            continue
        doc = docs.get(doc_id)
        if doc is None:
            # Documento ausente pero trazabilidad de compra → cuenta como primer precio ya aplicado
            return True
        if _tipo_doc_value(doc) in _TIPOS_COMPRA:
            return True
    return False


def _coste_frag(cantidad: float, coste_unit: float) -> float:
    return float(money_round(as_decimal(cantidad) * as_decimal(coste_unit)))


def _actualizar_movimiento_consumo(
    data: AppData,
    *,
    registro_id: str,
    det_idx: int,
    frag_idx: int,
    cantidad: float,
    coste_total: float,
) -> bool:
    mov = mov_svc.buscar_movimiento_consumo_fragmento(data, registro_id, det_idx, frag_idx)
    if mov is None:
        return False
    mov.coste_total_snapshot = round(float(coste_total), 2)
    if float(cantidad) > 0:
        mov.coste_unitario_snapshot = round(float(coste_total) / float(cantidad), 6)
    else:
        mov.coste_unitario_snapshot = 0.0
    return True


def _actualizar_movimiento_merma(
    data: AppData,
    *,
    registro_id: str,
    linea_idx: int,
    cantidad: float,
    coste_total: float,
) -> bool:
    linea_id = mov_svc.origen_linea_id_merma(linea_idx)
    for m in getattr(data, "movimientos", None) or []:
        if getattr(m, "origen_id", None) != registro_id:
            continue
        if getattr(m, "origen_linea_id", None) != linea_id:
            continue
        if _enum_val(getattr(m, "tipo", "")) != TipoMovimiento.MERMA.value:
            continue
        m.coste_total_snapshot = round(float(coste_total), 2)
        if float(cantidad) > 0:
            m.coste_unitario_snapshot = round(float(coste_total) / float(cantidad), 6)
        else:
            m.coste_unitario_snapshot = 0.0
        return True
    return False


def _reagregar_lineas_producto(lineas: list[Any], producto_id: str, coste_unit: float) -> int:
    """Recalcula coste de líneas del producto: cantidad × coste_unit."""
    n = 0
    for ln in lineas or []:
        if getattr(ln, "producto_id", None) != producto_id:
            continue
        cant = float(getattr(ln, "cantidad", 0) or 0)
        ln.coste = _coste_frag(cant, coste_unit)
        n += 1
    return n


def _revalorizar_registro_con_detalle(
    data: AppData,
    reg: Any,
    producto_id: str,
    coste_unit: float,
    resumen: ResumenRevalorizacion,
) -> bool:
    """Actualiza detalle + consumos_lote + lineas + coste_total. True si tocó algo."""
    touched = False
    detalle = list(getattr(reg, "lineas_detalle", None) or [])
    for di, det in enumerate(detalle):
        if getattr(det, "producto_id", None) != producto_id:
            continue
        frags = list(getattr(det, "consumos_lote", None) or [])
        if frags:
            coste_det = 0.0
            for fi, frag in enumerate(frags):
                fid = getattr(frag, "producto_id", None)
                if fid is not None and fid != producto_id:
                    continue
                cant = float(getattr(frag, "cantidad", 0) or 0)
                nuevo = _coste_frag(cant, coste_unit)
                frag.coste = nuevo
                coste_det += nuevo
                resumen.fragmentos_actualizados += 1
                if _actualizar_movimiento_consumo(
                    data,
                    registro_id=reg.id,
                    det_idx=di,
                    frag_idx=fi,
                    cantidad=cant,
                    coste_total=nuevo,
                ):
                    resumen.movimientos_actualizados += 1
                touched = True
            det.coste = round(coste_det, 2)
        else:
            cant = float(getattr(det, "cantidad", 0) or 0)
            det.coste = _coste_frag(cant, coste_unit)
            touched = True

    n_lin = _reagregar_lineas_producto(getattr(reg, "lineas", None) or [], producto_id, coste_unit)
    if n_lin:
        resumen.lineas_actualizadas += n_lin
        touched = True

    if touched:
        lineas = getattr(reg, "lineas", None) or []
        reg.coste_total = round(sum(float(getattr(l, "coste", 0) or 0) for l in lineas), 2)
    return touched


def _revalorizar_lotes_provisionales(
    data: AppData, producto_id: str, coste_unit: float
) -> int:
    """Ajusta precio_total de lotes sin documento de compra."""
    docs = {d.id: d for d in (getattr(data, "documentos", None) or [])}
    n = 0
    for lote in data.lotes:
        if lote.producto_id != producto_id:
            continue
        if getattr(lote, "anulado", False):
            continue
        doc_id = getattr(lote, "documento_origen_id", None)
        if doc_id:
            doc = docs.get(doc_id)
            if doc is None or _tipo_doc_value(doc) in _TIPOS_COMPRA:
                continue
        qty = float(getattr(lote, "cantidad", 0) or 0)
        if qty <= 0:
            continue
        lote.precio_total = float(money_round(as_decimal(qty) * as_decimal(coste_unit)))
        n += 1
    return n


def revalorizar_producto_primer_precio(
    data: AppData,
    producto_id: str,
    coste_unitario: float | Decimal,
    *,
    doc_id: str,
    actor: str = "Sistema",
) -> ResumenRevalorizacion:
    """Reescribe costes históricos del producto con el primer coste unitario inventariable."""
    unit = float(as_decimal(coste_unitario))
    resumen = ResumenRevalorizacion(
        producto_id=producto_id,
        coste_unitario=unit,
        doc_id=doc_id,
    )
    if unit < 0:
        return resumen

    for reg in getattr(data, "desayunos", None) or []:
        if getattr(reg, "anulado", False):
            continue
        if _revalorizar_registro_con_detalle(data, reg, producto_id, unit, resumen):
            resumen.registros_desayuno += 1

    for reg in getattr(data, "registros_servicio", None) or []:
        if getattr(reg, "anulado", False):
            continue
        if _revalorizar_registro_con_detalle(data, reg, producto_id, unit, resumen):
            resumen.registros_servicio += 1

    for merma in getattr(data, "mermas", None) or []:
        if getattr(merma, "anulado", False):
            continue
        touched = False
        for idx, ln in enumerate(getattr(merma, "lineas", None) or []):
            if getattr(ln, "producto_id", None) != producto_id:
                continue
            cant = float(getattr(ln, "cantidad", 0) or 0)
            nuevo = _coste_frag(cant, unit)
            ln.coste = nuevo
            resumen.lineas_actualizadas += 1
            if _actualizar_movimiento_merma(
                data,
                registro_id=merma.id,
                linea_idx=idx,
                cantidad=cant,
                coste_total=nuevo,
            ):
                resumen.movimientos_actualizados += 1
            touched = True
        if touched:
            merma.coste_total = round(
                sum(float(getattr(l, "coste", 0) or 0) for l in merma.lineas), 2
            )
            resumen.registros_merma += 1

    resumen.lotes_provisionales = _revalorizar_lotes_provisionales(data, producto_id, unit)

    nombre = next(
        (p.nombre for p in data.productos if p.id == producto_id),
        producto_id,
    )
    data.actividades.insert(
        0,
        Actividad(
            next_id("act", [a.id for a in data.actividades]),
            datetime.now(),
            actor or "Sistema",
            "Revalorización primer precio",
            (
                f"{nombre} ({producto_id}) @ {unit:.6g} €/ud "
                f"(doc {doc_id}) — desayunos={resumen.registros_desayuno} "
                f"servicios={resumen.registros_servicio} mermas={resumen.registros_merma} "
                f"frags={resumen.fragmentos_actualizados} lotes_prov={resumen.lotes_provisionales}"
            ),
        ),
    )
    return resumen
