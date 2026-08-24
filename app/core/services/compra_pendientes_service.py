"""Pendientes de facturar y situaciones derivadas de documentos de compra (consulta)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from app.core.models.conciliacion import EstadoConciliacion
from app.core.models import EstadoDocumento, TipoDocumento
from app.core.models.documento import Documento, LineaDocumento
from app.core.services.factura_service import linea_albaran_ya_conciliada
from app.core.services.money import as_decimal

SituacionFacturacion = Literal["sin_facturar", "parcial", "facturado"]
SituacionInventario = Literal["sin_impacto", "con_entrada", "revertido"]


def _estado_val(doc: Documento) -> str:
    e = doc.estado
    return e.value if hasattr(e, "value") else str(e)


def _tipo_val(doc: Documento) -> str:
    t = doc.tipo
    return t.value if hasattr(t, "value") else str(t)


def _conc_activa(c: Any) -> bool:
    est = c.estado.value if hasattr(c.estado, "value") else str(c.estado)
    return est == EstadoConciliacion.ACTIVA.value


def cantidad_recibida_linea(linea: LineaDocumento) -> Decimal:
    if linea.cantidad_inventario is not None:
        return as_decimal(linea.cantidad_inventario)
    if linea.cantidad_compra is not None:
        return as_decimal(linea.cantidad_compra)
    return as_decimal(linea.cantidad or 0)


def cantidad_conciliada_activa(
    data: Any,
    linea_albaran_id: str,
) -> Decimal:
    total = Decimal("0")
    for c in getattr(data, "conciliaciones_documento", []) or []:
        if c.linea_albaran_id != linea_albaran_id:
            continue
        if not _conc_activa(c):
            continue
        total += as_decimal(c.cantidad_conciliada)
    return total


def cantidad_pendiente_facturar(
    data: Any,
    linea_albaran_id: str,
    *,
    excluir_factura_id: str | None = None,
    linea: LineaDocumento | None = None,
) -> Decimal:
    """qty recibida − Σ conciliada activa. F11 (origen en factura confirmada) ⇒ 0."""
    if linea_albaran_ya_conciliada(
        data, linea_albaran_id, excluir_factura_id=excluir_factura_id
    ):
        return Decimal("0")
    ln = linea
    if ln is None:
        for d in getattr(data, "documentos", []) or []:
            for x in d.lineas:
                if x.id == linea_albaran_id:
                    ln = x
                    break
            if ln is not None:
                break
    if ln is None:
        return Decimal("0")
    recibida = cantidad_recibida_linea(ln)
    pendiente = recibida - cantidad_conciliada_activa(data, linea_albaran_id)
    return pendiente if pendiente > 0 else Decimal("0")


def lineas_pendientes_albaran(
    data: Any,
    alb: Documento,
    *,
    excluir_factura_id: str | None = None,
) -> list[tuple[LineaDocumento, Decimal]]:
    out: list[tuple[LineaDocumento, Decimal]] = []
    for ln in alb.lineas:
        pend = cantidad_pendiente_facturar(
            data, ln.id, excluir_factura_id=excluir_factura_id, linea=ln
        )
        if pend > 0:
            out.append((ln, pend))
    return out


def albaranes_pendientes_proveedor(
    data: Any,
    *,
    proveedor_id: str,
    excluir_factura_id: str | None = None,
) -> list[Documento]:
    out: list[Documento] = []
    for d in getattr(data, "documentos", []) or []:
        if _tipo_val(d) != TipoDocumento.ALBARAN.value:
            continue
        if _estado_val(d) != EstadoDocumento.CONFIRMADO.value:
            continue
        if (d.proveedor_id or "") != proveedor_id:
            continue
        if lineas_pendientes_albaran(
            data, d, excluir_factura_id=excluir_factura_id
        ):
            out.append(d)
    return sorted(out, key=lambda x: (x.fecha_documento, x.id), reverse=True)


def situacion_facturacion_albaran(
    data: Any,
    alb: Documento,
) -> SituacionFacturacion:
    if _tipo_val(alb) != TipoDocumento.ALBARAN.value:
        return "sin_facturar"
    total = Decimal("0")
    pendiente = Decimal("0")
    for ln in alb.lineas:
        rec = cantidad_recibida_linea(ln)
        total += rec
        pendiente += cantidad_pendiente_facturar(data, ln.id, linea=ln)
    if total <= 0:
        return "sin_facturar"
    if pendiente >= total:
        return "sin_facturar"
    if pendiente <= 0:
        return "facturado"
    return "parcial"


def situacion_inventario_documento(doc: Documento) -> SituacionInventario:
    if _estado_val(doc) == EstadoDocumento.ANULADO.value:
        if getattr(doc, "impacto_stock", False):
            return "revertido"
        return "sin_impacto"
    if getattr(doc, "impacto_stock", False):
        return "con_entrada"
    return "sin_impacto"


@dataclass(frozen=True)
class DiferenciaConciliacion:
    tipo: str  # coincidente | qty | precio | fiscal | solo_alb | solo_fac
    linea_albaran_id: str | None
    linea_factura_id: str | None
    detalle: str


def clasificar_diferencias_factura_albaran(
    data: Any,
    factura: Documento,
) -> list[DiferenciaConciliacion]:
    """Compara vínculos activos factura↔albarán (consulta; no muta)."""
    diffs: list[DiferenciaConciliacion] = []
    concs = [
        c
        for c in getattr(data, "conciliaciones_documento", []) or []
        if _conc_activa(c)
        and any(ln.id == c.linea_factura_id for ln in factura.lineas)
    ]
    linked_fac = {c.linea_factura_id for c in concs}
    linked_alb = {c.linea_albaran_id for c in concs}

    def _find_ln(lid: str) -> LineaDocumento | None:
        for d in getattr(data, "documentos", []) or []:
            for ln in d.lineas:
                if ln.id == lid:
                    return ln
        return None

    for c in concs:
        ln_f = next((x for x in factura.lineas if x.id == c.linea_factura_id), None)
        ln_a = _find_ln(c.linea_albaran_id)
        if ln_f is None or ln_a is None:
            continue
        qty_f = cantidad_recibida_linea(ln_f)
        qty_a = as_decimal(c.cantidad_conciliada)
        if qty_f != qty_a:
            diffs.append(
                DiferenciaConciliacion(
                    "qty",
                    ln_a.id,
                    ln_f.id,
                    f"Cantidad factura {qty_f} ≠ conciliada {qty_a}",
                )
            )
        pf = as_decimal(ln_f.precio_unitario_compra or 0)
        pa = as_decimal(ln_a.precio_unitario_compra or 0)
        if pf != pa:
            diffs.append(
                DiferenciaConciliacion(
                    "precio",
                    ln_a.id,
                    ln_f.id,
                    f"Precio factura {pf} ≠ albarán {pa}",
                )
            )
        ig_f = as_decimal(ln_f.impuesto_porcentaje_snapshot or 0)
        ig_a = as_decimal(ln_a.impuesto_porcentaje_snapshot or 0)
        if ig_f != ig_a:
            diffs.append(
                DiferenciaConciliacion(
                    "fiscal",
                    ln_a.id,
                    ln_f.id,
                    f"IGIC factura {ig_f}% ≠ albarán {ig_a}%",
                )
            )
        if qty_f == qty_a and pf == pa and ig_f == ig_a:
            diffs.append(
                DiferenciaConciliacion(
                    "coincidente",
                    ln_a.id,
                    ln_f.id,
                    "Línea conciliada coincidente",
                )
            )

    for ln in factura.lineas:
        if ln.id not in linked_fac and not ln.linea_origen_id:
            diffs.append(
                DiferenciaConciliacion(
                    "solo_fac",
                    None,
                    ln.id,
                    "Línea de factura sin vínculo a albarán",
                )
            )
        elif ln.linea_origen_id and ln.linea_origen_id not in linked_alb:
            # origen F11 sin registro B3 — informar
            diffs.append(
                DiferenciaConciliacion(
                    "coincidente",
                    ln.linea_origen_id,
                    ln.id,
                    "Vínculo por origen de línea (legado F11)",
                )
            )
    return diffs
