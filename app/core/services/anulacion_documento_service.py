"""Anulación exacta y devolución física de documentos (B2 / Plan v3 §A3.2).

No borra documentos, lotes ni movimientos. Crea movimientos compensatorios.
Usa snapshots persistidos; no recalcula con catálogo vivo.

Separado de ``anulacion_compra_service`` (Fase 11C: soft-delete de lote).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from app.core.application.context import build_app_context
from app.core.application.id_generator import next_id
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.models import (
    Actividad,
    AppData,
    Documento,
    EstadoDocumento,
    LineaDocumento,
    LoteStock,
    TipoDocumento,
)
from app.core.models.conciliacion import EstadoConciliacion
from app.core.models.enums import DireccionMovimiento, TipoMovimiento
from app.core.services import movimiento_service as mov
from app.core.services.persistencia_appdata import transactional_update_appdata

ANULACION_OK = "ok"
ANULACION_IDEMPOTENTE = "idempotente"
ANULACION_RECHAZADA = "rechazada"
ANULACION_YA = "ya_anulada"


@dataclass
class ResultadoAnulacion:
    ok: bool
    mensaje: str
    codigo: str = ANULACION_OK
    documento: Documento | None = None


def _estado(doc: Documento) -> str:
    e = doc.estado
    return e.value if hasattr(e, "value") else str(e)


def _tipo(doc: Documento) -> str:
    t = doc.tipo
    return t.value if hasattr(t, "value") else str(t)


def _idem_key_anular(confirmacion_id: str | None, documento_id: str) -> str:
    base = (confirmacion_id or documento_id).strip().lower()
    return f"anular:{base}"


def lotes_de_documento(data: AppData, documento_id: str) -> list[LoteStock]:
    return [
        l
        for l in data.lotes
        if getattr(l, "documento_origen_id", None) == documento_id
        and not getattr(l, "anulado", False)
    ]


def movimientos_entrada_documento(data: AppData, documento_id: str) -> list:
    out = []
    for m in getattr(data, "movimientos", []) or []:
        if m.origen_id != documento_id:
            continue
        tipo = m.tipo.value if hasattr(m.tipo, "value") else str(m.tipo)
        if tipo.startswith("entrada"):
            out.append(m)
    return out


def conciliaciones_activas_hacia_albaran(data: AppData, documento_id: str) -> list:
    line_ids = {
        ln.id
        for d in data.documentos
        if d.id == documento_id
        for ln in d.lineas
    }
    return [
        c
        for c in getattr(data, "conciliaciones_documento", []) or []
        if c.linea_albaran_id in line_ids
        and (
            c.estado.value if hasattr(c.estado, "value") else str(c.estado)
        )
        == EstadoConciliacion.ACTIVA.value
    ]


def lote_integro(lote: LoteStock) -> bool:
    """Intact = restante == cantidad original (sin consumo)."""
    return abs(float(lote.cantidad_restante) - float(lote.cantidad)) < 1e-9


def _ya_anulada_idempotente(data: AppData, documento_id: str, key: str) -> bool:
    for m in getattr(data, "movimientos", []) or []:
        if getattr(m, "idempotency_key", None) == key:
            return True
    doc = next((d for d in data.documentos if d.id == documento_id), None)
    return doc is not None and _estado(doc) == EstadoDocumento.ANULADO.value


def _aplicar_anulacion(
    data: AppData,
    documento_id: str,
    *,
    motivo: str,
    actor: str = "Sistema",
) -> ResultadoAnulacion:
    doc = next((d for d in data.documentos if d.id == documento_id), None)
    if doc is None:
        return ResultadoAnulacion(False, "Documento no encontrado.", ANULACION_RECHAZADA)

    key = _idem_key_anular(getattr(doc, "confirmacion_id", None), doc.id)
    if _estado(doc) == EstadoDocumento.ANULADO.value:
        return ResultadoAnulacion(
            True,
            "Documento ya anulado (idempotente).",
            ANULACION_IDEMPOTENTE,
            doc,
        )
    if _estado(doc) != EstadoDocumento.CONFIRMADO.value:
        return ResultadoAnulacion(
            False,
            "Solo se anulan documentos confirmados.",
            ANULACION_RECHAZADA,
            doc,
        )

    tipo = _tipo(doc)
    motivo_txt = (motivo or "").strip()
    if not motivo_txt:
        return ResultadoAnulacion(False, "Motivo de anulación obligatorio.", ANULACION_RECHAZADA, doc)

    if tipo == TipoDocumento.ALBARAN.value:
        concs = conciliaciones_activas_hacia_albaran(data, doc.id)
        if concs:
            return ResultadoAnulacion(
                False,
                "Anulación de albarán bloqueada: existen conciliaciones activas. "
                "Anule primero esas conciliaciones.",
                ANULACION_RECHAZADA,
                doc,
            )

    impacto = getattr(doc, "impacto_stock", None)
    tiene_lotes = bool(lotes_de_documento(data, doc.id))
    solo_conciliacion = (
        tipo == TipoDocumento.FACTURA.value
        and (impacto is False or not tiene_lotes)
    )

    if solo_conciliacion:
        for c in getattr(data, "conciliaciones_documento", []) or []:
            if c.confirmacion_id == getattr(doc, "confirmacion_id", None) or any(
                ln.id == c.linea_factura_id for ln in doc.lineas
            ):
                est = c.estado.value if hasattr(c.estado, "value") else str(c.estado)
                if est == EstadoConciliacion.ACTIVA.value:
                    c.estado = EstadoConciliacion.ANULADA
                    c.anulada_en = datetime.now()
                    c.motivo_anulacion = motivo_txt
        doc.estado = EstadoDocumento.ANULADO
        doc.anulado_en = datetime.now()
        doc.motivo_anulacion = motivo_txt
        data.actividades.insert(
            0,
            Actividad(
                next_id("act", [a.id for a in data.actividades]),
                datetime.now(),
                actor,
                "Anular factura (conciliación)",
                f"{doc.id}: {motivo_txt}",
            ),
        )
        return ResultadoAnulacion(True, f"Documento {doc.id} anulado (sin stock).", documento=doc)

    lotes = lotes_de_documento(data, doc.id)
    if not lotes and impacto is not False:
        return ResultadoAnulacion(
            False,
            "No hay lotes trazables (documento_origen_id) para anulación exacta.",
            ANULACION_RECHAZADA,
            doc,
        )

    for lote in lotes:
        if not lote_integro(lote):
            return ResultadoAnulacion(
                False,
                f"Lote {lote.id} parcialmente consumido "
                f"(restante {lote.cantidad_restante:g} ≠ {lote.cantidad:g}). "
                "Anulación total rechazada.",
                ANULACION_RECHAZADA,
                doc,
            )

    entradas_por_lote = {
        m.lote_id: m
        for m in movimientos_entrada_documento(data, doc.id)
        if getattr(m, "lote_id", None)
    }

    ctx = build_app_context(uow=InMemoryUnitOfWork(data))
    for lote in lotes:
        qty = float(lote.cantidad_restante)
        if qty <= 0:
            continue
        orig = entradas_por_lote.get(lote.id)
        espejo = mov.crear_movimiento(
            producto_id=lote.producto_id,
            lote_id=lote.id,
            tipo=TipoMovimiento.REVERSION_ENTRADA,
            direccion=DireccionMovimiento.SALIDA,
            cantidad=qty,
            fecha=date.today(),
            origen_tipo="anulacion_compra",
            origen_id=doc.id,
            origen_linea_id=getattr(lote, "linea_documento_origen_id", None),
            movimiento_revertido_id=orig.id if orig is not None else None,
            idempotency_key=f"{key}:{lote.id}",
            coste_unitario_snapshot=(
                round(float(lote.precio_total) / float(lote.cantidad), 6)
                if float(lote.cantidad) > 0
                else None
            ),
            coste_total_snapshot=float(lote.precio_total),
            ctx=ctx,
            commit=False,
        )
        if not espejo.ok and not getattr(espejo, "duplicado", False):
            return ResultadoAnulacion(False, espejo.mensaje, ANULACION_RECHAZADA, doc)
        lote.cantidad_restante = 0.0
        lote.anulado = True
        lote.fecha_anulacion = date.today()
        lote.motivo_anulacion = motivo_txt
        lote.anulado_por = actor

    doc.estado = EstadoDocumento.ANULADO
    doc.anulado_en = datetime.now()
    doc.motivo_anulacion = motivo_txt
    data.actividades.insert(
        0,
        Actividad(
            next_id("act", [a.id for a in data.actividades]),
            datetime.now(),
            actor,
            "Anular compra",
            f"{doc.id}: {motivo_txt} · lotes={len(lotes)}",
        ),
    )
    return ResultadoAnulacion(True, f"Documento {doc.id} anulado con reversión exacta.", documento=doc)


def anular_documento_confirmado(
    documento_id: str,
    *,
    motivo: str,
    json_path: Path | str,
    actor: str = "Sistema",
) -> ResultadoAnulacion:
    """Anulación bajo lock A2. Toda la reversión o ninguna."""
    path = Path(json_path).resolve()
    holder: dict = {"result": None}

    def _mutate(data: AppData) -> AppData:
        holder["result"] = _aplicar_anulacion(
            data, documento_id, motivo=motivo, actor=actor
        )
        if not holder["result"].ok:
            raise RuntimeError(holder["result"].mensaje)
        return data

    try:
        transactional_update_appdata(path, _mutate)
    except RuntimeError as exc:
        return holder["result"] or ResultadoAnulacion(False, str(exc), ANULACION_RECHAZADA)
    except Exception as exc:  # noqa: BLE001
        return ResultadoAnulacion(False, f"Persistencia fallida: {exc}", ANULACION_RECHAZADA)
    return holder["result"] or ResultadoAnulacion(False, "Sin resultado.")


def anular_conciliacion(
    conciliacion_id: str,
    *,
    motivo: str,
    json_path: Path | str,
) -> ResultadoAnulacion:
    """Anula una conciliación activa (sin tocar stock)."""
    path = Path(json_path)

    def _mutate(data: AppData) -> AppData:
        c = next(
            (
                x
                for x in getattr(data, "conciliaciones_documento", []) or []
                if x.id == conciliacion_id
            ),
            None,
        )
        if c is None:
            raise RuntimeError("Conciliación no encontrada.")
        est = c.estado.value if hasattr(c.estado, "value") else str(c.estado)
        if est == EstadoConciliacion.ANULADA.value:
            return data
        if est != EstadoConciliacion.ACTIVA.value:
            raise RuntimeError("La conciliación no está activa.")
        c.estado = EstadoConciliacion.ANULADA
        c.anulada_en = datetime.now()
        c.motivo_anulacion = (motivo or "").strip() or "Anulación"
        return data

    try:
        transactional_update_appdata(path, _mutate)
        return ResultadoAnulacion(True, f"Conciliación {conciliacion_id} anulada.")
    except RuntimeError as exc:
        return ResultadoAnulacion(False, str(exc), ANULACION_RECHAZADA)


def registrar_rectificativa_economica(
    *,
    documento_rectificado_id: str,
    motivo: str,
    json_path: Path | str,
    confirmacion_id: str | None = None,
    lineas: list[dict] | None = None,
    actor: str = "Sistema",
) -> ResultadoAnulacion:
    """RECTIFICATIVA con impacto_stock=False (D72/A6): sin tocar lotes ni movimientos."""
    path = Path(json_path)
    token = (confirmacion_id or str(uuid.uuid4())).strip().lower()
    holder: dict = {"result": None}

    def _mutate(data: AppData) -> AppData:
        for d in data.documentos:
            if getattr(d, "confirmacion_id", None) == token:
                holder["result"] = ResultadoAnulacion(
                    True,
                    "Rectificativa económica idempotente.",
                    ANULACION_IDEMPOTENTE,
                    d,
                )
                return data

        original = next(
            (d for d in data.documentos if d.id == documento_rectificado_id), None
        )
        if original is None:
            raise RuntimeError("Documento a rectificar no encontrado.")
        if _estado(original) not in (
            EstadoDocumento.CONFIRMADO.value,
            EstadoDocumento.RECTIFICADO.value,
        ):
            raise RuntimeError(
                "Solo se rectifican documentos confirmados (o ya rectificados)."
            )
        motivo_txt = (motivo or "").strip()
        if not motivo_txt:
            raise RuntimeError("Motivo de rectificación obligatorio.")

        nuevas: list[LineaDocumento] = []
        fuente = lineas
        if not fuente:
            fuente = [
                {
                    "producto_id": ln.producto_id,
                    "cantidad": float(ln.cantidad),
                    "precio_total": float(ln.precio_total),
                    "linea_origen_id": ln.id,
                }
                for ln in original.lineas
            ]
        for raw in fuente:
            nuevas.append(
                LineaDocumento(
                    id=next_id("ln", [x.id for x in nuevas]),
                    producto_id=raw["producto_id"],
                    cantidad=float(raw.get("cantidad", 0)),
                    precio_total=float(raw.get("precio_total", 0)),
                    documento_origen_id=documento_rectificado_id,
                    linea_origen_id=raw.get("linea_origen_id"),
                )
            )

        doc = Documento(
            id=next_id("doc", [d.id for d in data.documentos]),
            tipo=TipoDocumento.RECTIFICATIVA,
            estado=EstadoDocumento.CONFIRMADO,
            fecha_documento=date.today(),
            proveedor_id=original.proveedor_id,
            proveedor_nombre_snapshot=original.proveedor_nombre_snapshot,
            documento_rectificado_id=documento_rectificado_id,
            motivo_rectificacion=motivo_txt,
            confirmacion_id=token,
            impacto_stock=False,
            confirmado_en=datetime.now(),
            lineas=nuevas,
            notas=motivo_txt,
            registrado_por=actor,
        )
        data.documentos.append(doc)
        if _estado(original) == EstadoDocumento.CONFIRMADO.value:
            original.estado = EstadoDocumento.RECTIFICADO
            original.rectificado_en = datetime.now()
        data.actividades.insert(
            0,
            Actividad(
                next_id("act", [a.id for a in data.actividades]),
                datetime.now(),
                actor,
                "Rectificativa económica",
                f"{doc.id} → {documento_rectificado_id}: {motivo_txt}",
            ),
        )
        holder["result"] = ResultadoAnulacion(
            True,
            f"Rectificativa económica {doc.id} (sin impacto de stock).",
            documento=doc,
        )
        return data

    try:
        transactional_update_appdata(path, _mutate)
    except RuntimeError as exc:
        return holder["result"] or ResultadoAnulacion(False, str(exc), ANULACION_RECHAZADA)
    return holder["result"] or ResultadoAnulacion(False, "Sin resultado.")


def registrar_devolucion(
    *,
    documento_origen_id: str,
    lineas: list[dict],
    json_path: Path | str,
    motivo: str,
    confirmacion_id: str | None = None,
) -> ResultadoAnulacion:
    """DEVOLUCION física: salida trazable por lote origen. Rechaza si insuficiente."""
    path = Path(json_path)
    token = (confirmacion_id or str(uuid.uuid4())).strip().lower()
    holder: dict = {"result": None}

    def _mutate(data: AppData) -> AppData:
        origen = next((d for d in data.documentos if d.id == documento_origen_id), None)
        if origen is None:
            raise RuntimeError("Documento origen no encontrado.")
        if _estado(origen) != EstadoDocumento.CONFIRMADO.value:
            raise RuntimeError("Solo se puede devolver desde un documento confirmado.")

        for d in data.documentos:
            if getattr(d, "confirmacion_id", None) == token:
                holder["result"] = ResultadoAnulacion(
                    True, "Devolución idempotente.", ANULACION_IDEMPOTENTE, d
                )
                return data

        ctx = build_app_context(uow=InMemoryUnitOfWork(data))
        nuevas_lineas: list[LineaDocumento] = []
        for raw in lineas:
            lote_id = raw["lote_id"]
            qty = float(raw["cantidad"])
            if qty <= 0:
                raise RuntimeError("Cantidad de devolución debe ser > 0.")
            lote = next((l for l in data.lotes if l.id == lote_id), None)
            if lote is None:
                raise RuntimeError(f"Lote inexistente: {lote_id}")
            if getattr(lote, "documento_origen_id", None) != documento_origen_id:
                raise RuntimeError(
                    f"Lote {lote_id} no pertenece al documento origen."
                )
            if float(lote.cantidad_restante) + 1e-9 < qty:
                raise RuntimeError(
                    f"Stock insuficiente en lote {lote_id}: "
                    f"restante {lote.cantidad_restante:g}, solicitado {qty:g}."
                )
            espejo = mov.crear_movimiento(
                producto_id=lote.producto_id,
                lote_id=lote.id,
                tipo=TipoMovimiento.AJUSTE_SALIDA,
                direccion=DireccionMovimiento.SALIDA,
                cantidad=qty,
                fecha=date.today(),
                origen_tipo="devolucion",
                origen_id=token,
                origen_linea_id=lote_id,
                idempotency_key=f"devolucion:{token}:{lote_id}",
                ctx=ctx,
                commit=False,
            )
            if not espejo.ok and not getattr(espejo, "duplicado", False):
                raise RuntimeError(espejo.mensaje)
            lote.cantidad_restante = round(float(lote.cantidad_restante) - qty, 4)
            nuevas_lineas.append(
                LineaDocumento(
                    id=next_id("ln", [x.id for x in nuevas_lineas]),
                    producto_id=lote.producto_id,
                    cantidad=qty,
                    precio_total=0.0,
                    lote_id=lote.id,
                    movimiento_id=espejo.movimiento.id if espejo.movimiento else None,
                    documento_origen_id=documento_origen_id,
                    linea_origen_id=getattr(lote, "linea_documento_origen_id", None),
                )
            )

        doc = Documento(
            id=next_id("doc", [d.id for d in data.documentos]),
            tipo=TipoDocumento.DEVOLUCION,
            estado=EstadoDocumento.CONFIRMADO,
            fecha_documento=date.today(),
            proveedor_id=origen.proveedor_id,
            proveedor_nombre_snapshot=origen.proveedor_nombre_snapshot,
            documento_rectificado_id=documento_origen_id,
            motivo_rectificacion=(motivo or "").strip() or None,
            confirmacion_id=token,
            impacto_stock=True,
            confirmado_en=datetime.now(),
            lineas=nuevas_lineas,
            notas=(motivo or "").strip() or None,
        )
        data.documentos.append(doc)
        holder["result"] = ResultadoAnulacion(
            True, f"Devolución {doc.id} registrada.", documento=doc
        )
        return data

    try:
        transactional_update_appdata(path, _mutate)
    except RuntimeError as exc:
        return holder["result"] or ResultadoAnulacion(False, str(exc), ANULACION_RECHAZADA)
    return holder["result"] or ResultadoAnulacion(False, "Sin resultado.")
