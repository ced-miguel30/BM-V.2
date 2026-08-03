"""Rectificativas documentales (Fase 12).

Corrige un albarán o factura CONFIRMADO sin edición silenciosa:
- Crea documento RECTIFICATIVA enlazado (documento_rectificado_id).
- Al confirmar: revierte stock de líneas con lote (mismas reglas que anulación)
  y marca el original como RECTIFICADO.
- Líneas solo-metadato (conciliación) no tocan stock.
- Sin búsqueda/exportación (F13). Sin OCR.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.core.application.context import AppContext
from app.core.application.id_generator import next_id
from app.core.models import (
    Actividad,
    AppData,
    Documento,
    EstadoDocumento,
    LineaDocumento,
    TipoDocumento,
)
from app.core.models.enums import DireccionMovimiento, TipoMovimiento
from app.core.services import movimiento_service as mov
from app.core.services.albaran_service import buscar_documento
from app.core.services.inventory_batch_service import (
    restaurar_cantidades_restantes,
    snapshot_cantidades_restantes,
)
from app.core.storage.session_store import get_data, persist_data

ORIGEN_TIPO_RECTIFICATIVA = "rectificativa"
ORIGEN_TIPO_ANULACION_RECTIFICATIVA = "anulacion_rectificativa"

_TIPOS_RECTIFICABLES = frozenset(
    {TipoDocumento.ALBARAN.value, TipoDocumento.FACTURA.value}
)


@dataclass
class ResultadoRectificativa:
    ok: bool
    mensaje: str
    documento: Documento | None = None


def _ctx(ctx: AppContext | None = None) -> AppContext:
    if ctx is not None:
        return ctx
    from app.core.application.actor import actor_desde_appdata
    from app.core.application.clock import SystemClock

    class _Uow:
        def get_data(self) -> AppData:
            return get_data()

        def commit(self, data: AppData | None = None) -> AppData:
            return persist_data(data if data is not None else get_data())

    uow = _Uow()
    return AppContext(
        uow=uow,
        actor=actor_desde_appdata(uow.get_data()),
        clock=SystemClock(),
    )


def _estado(doc: Documento) -> str:
    e = doc.estado
    return e.value if hasattr(e, "value") else str(e)


def _tipo(doc: Documento) -> str:
    t = doc.tipo
    return t.value if hasattr(t, "value") else str(t)


def listar_rectificativas(
    ctx: AppContext | None = None,
    *,
    estado: str | None = None,
) -> list[Documento]:
    data = _ctx(ctx).uow.get_data()
    docs = [
        d
        for d in getattr(data, "documentos", []) or []
        if _tipo(d) == TipoDocumento.RECTIFICATIVA.value
    ]
    if estado:
        docs = [d for d in docs if _estado(d) == estado]
    return sorted(docs, key=lambda d: (d.fecha_documento, d.id), reverse=True)


def rectificativa_confirmada_de(
    data: AppData, documento_original_id: str
) -> Documento | None:
    for d in getattr(data, "documentos", []) or []:
        if _tipo(d) != TipoDocumento.RECTIFICATIVA.value:
            continue
        if d.documento_rectificado_id != documento_original_id:
            continue
        if _estado(d) == EstadoDocumento.CONFIRMADO.value:
            return d
    return None


def crear_borrador_rectificativa(
    documento_rectificado_id: str,
    *,
    motivo: str,
    fecha_documento: date | None = None,
    referencia_externa: str | None = None,
    archivo_ids: list[str] | None = None,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoRectificativa:
    """Copia líneas del original; no edita el original."""
    c = _ctx(ctx)
    data = c.uow.get_data()
    if not hasattr(data, "documentos") or data.documentos is None:
        data.documentos = []

    motivo_limpio = (motivo or "").strip()
    if not motivo_limpio:
        return ResultadoRectificativa(False, "El motivo de rectificación es obligatorio.")

    original = buscar_documento(data, documento_rectificado_id)
    if original is None:
        return ResultadoRectificativa(False, "Documento a rectificar no encontrado.")
    if _tipo(original) not in _TIPOS_RECTIFICABLES:
        return ResultadoRectificativa(
            False, "Solo se rectifican albaranes o facturas."
        )
    if _estado(original) != EstadoDocumento.CONFIRMADO.value:
        return ResultadoRectificativa(
            False,
            f"El original debe estar confirmado (estado={_estado(original)}).",
        )
    if rectificativa_confirmada_de(data, original.id) is not None:
        return ResultadoRectificativa(
            False, f"Ya existe una rectificativa confirmada para {original.id}."
        )
    # Evitar dos borradores simultáneos del mismo original
    for d in data.documentos:
        if (
            _tipo(d) == TipoDocumento.RECTIFICATIVA.value
            and d.documento_rectificado_id == original.id
            and _estado(d) == EstadoDocumento.BORRADOR.value
        ):
            return ResultadoRectificativa(
                False,
                f"Ya hay un borrador de rectificativa ({d.id}) para {original.id}.",
            )

    for aid in archivo_ids or []:
        if not any(a.id == aid for a in getattr(data, "archivos_documentales", []) or []):
            return ResultadoRectificativa(False, f"Archivo inexistente: {aid}")

    lineas: list[LineaDocumento] = []
    for ln in original.lineas:
        lineas.append(
            LineaDocumento(
                id=next_id("ln", [x.id for x in lineas]),
                producto_id=ln.producto_id,
                cantidad=float(ln.cantidad),
                precio_total=float(ln.precio_total),
                impuesto_id=ln.impuesto_id,
                impuesto_porcentaje_snapshot=ln.impuesto_porcentaje_snapshot,
                ubicacion_destino_id=ln.ubicacion_destino_id,
                producto_nombre_snapshot=ln.producto_nombre_snapshot,
                unidad_snapshot=ln.unidad_snapshot,
                fecha_expiracion=ln.fecha_expiracion,
                documento_origen_id=original.id,
                linea_origen_id=ln.id,
                # lote/movimiento quedan en el original; se usan al confirmar
            )
        )

    doc = Documento(
        id=next_id("doc", [d.id for d in data.documentos]),
        tipo=TipoDocumento.RECTIFICATIVA,
        estado=EstadoDocumento.BORRADOR,
        fecha_documento=fecha_documento
        or (c.clock.today() if getattr(c, "clock", None) else date.today()),
        proveedor_id=original.proveedor_id,
        proveedor_nombre_snapshot=original.proveedor_nombre_snapshot,
        nif_cif_snapshot=original.nif_cif_snapshot,
        referencia_externa=(referencia_externa or "").strip() or None,
        lineas=lineas,
        archivo_ids=list(archivo_ids or []),
        registrado_por=getattr(getattr(c, "actor", None), "nombre", None) or "Sistema",
        hora=c.clock.now().time() if getattr(c, "clock", None) else None,
        creado_en=datetime.now(),
        documento_rectificado_id=original.id,
        motivo_rectificacion=motivo_limpio,
        notas=f"Rectifica {original.id} ({_tipo(original)})",
    )
    data.documentos.append(doc)
    data.actividades.insert(
        0,
        Actividad(
            next_id("act", [a.id for a in data.actividades]),
            datetime.now(),
            doc.registrado_por,
            "Crear rectificativa borrador",
            f"{doc.id} → {original.id}: {motivo_limpio}",
        ),
    )
    if commit:
        c.uow.commit(data)
    return ResultadoRectificativa(
        True,
        f"Rectificativa borrador {doc.id} creada ({len(lineas)} línea(s)).",
        doc,
    )


def preview_confirmacion(doc: Documento, data: AppData) -> list[str]:
    if not doc.documento_rectificado_id:
        return ["Sin documento_rectificado_id."]
    original = buscar_documento(data, doc.documento_rectificado_id)
    if original is None:
        return ["Original no encontrado."]
    out = [f"Rectifica {original.id} ({_tipo(original)}) → estado RECTIFICADO"]
    for ln in doc.lineas:
        orig_ln = next(
            (x for x in original.lineas if x.id == ln.linea_origen_id), None
        )
        if orig_ln is None:
            out.append(f"{ln.id}: línea origen {ln.linea_origen_id} no encontrada")
            continue
        if orig_ln.lote_id:
            out.append(
                f"{ln.id}: REVERSO STOCK · {ln.producto_nombre_snapshot or ln.producto_id} "
                f"lote {orig_ln.lote_id} × {ln.cantidad:g} · {ln.precio_total:.2f} €"
            )
        else:
            out.append(
                f"{ln.id}: SOLO METADATOS · {ln.producto_nombre_snapshot or ln.producto_id} "
                f"× {ln.cantidad:g} (sin stock)"
            )
    return out


def confirmar_rectificativa(
    documento_id: str,
    *,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoRectificativa:
    c = _ctx(ctx)
    data = c.uow.get_data()
    doc = buscar_documento(data, documento_id)
    if doc is None:
        return ResultadoRectificativa(False, "Documento no encontrado.")
    if _tipo(doc) != TipoDocumento.RECTIFICATIVA.value:
        return ResultadoRectificativa(False, "El documento no es una rectificativa.")
    if _estado(doc) != EstadoDocumento.BORRADOR.value:
        return ResultadoRectificativa(False, "Solo se confirman borradores.")
    if not doc.documento_rectificado_id:
        return ResultadoRectificativa(False, "Falta documento_rectificado_id.")
    if not doc.lineas:
        return ResultadoRectificativa(False, "La rectificativa no tiene líneas.")

    original = buscar_documento(data, doc.documento_rectificado_id)
    if original is None:
        return ResultadoRectificativa(False, "Documento original no encontrado.")
    if _estado(original) != EstadoDocumento.CONFIRMADO.value:
        return ResultadoRectificativa(
            False, f"Original no confirmado (estado={_estado(original)})."
        )
    if rectificativa_confirmada_de(data, original.id) is not None:
        return ResultadoRectificativa(
            False, f"Ya existe rectificativa confirmada para {original.id}."
        )

    # Debe cubrir todas las líneas del original (rectificación total)
    origen_ids = {ln.linea_origen_id for ln in doc.lineas if ln.linea_origen_id}
    originales_ids = {ln.id for ln in original.lineas}
    if origen_ids != originales_ids:
        return ResultadoRectificativa(
            False,
            "La rectificativa debe incluir todas las líneas del original "
            f"(faltan o sobran respecto a {original.id}).",
        )

    if not hasattr(data, "movimientos") or data.movimientos is None:
        data.movimientos = []

    snap = snapshot_cantidades_restantes(data)
    n_mov = len(data.movimientos)
    n_act = len(data.actividades)
    lote_flags = {
        l.id: (
            l.anulado,
            l.fecha_anulacion,
            l.motivo_anulacion,
            l.referencia_anulacion,
            getattr(l, "anulado_por", "") or "",
        )
        for l in data.lotes
    }
    orig_estado_prev = original.estado
    orig_rect_en_prev = original.rectificado_en
    archivos_backup = {
        a.id: a.documento_id
        for a in getattr(data, "archivos_documentales", []) or []
        if a.id in (doc.archivo_ids or [])
    }

    try:
        for ln in doc.lineas:
            orig_ln = next(
                (x for x in original.lineas if x.id == ln.linea_origen_id), None
            )
            if orig_ln is None:
                raise RuntimeError(f"Línea origen {ln.linea_origen_id} no encontrada")
            if not orig_ln.lote_id:
                continue
            lote = next((l for l in data.lotes if l.id == orig_ln.lote_id), None)
            if lote is None:
                continue
            restante = float(lote.cantidad_restante)
            if restante <= 1e-9:
                lote.anulado = True
                lote.fecha_anulacion = date.today()
                lote.motivo_anulacion = (
                    f"Rectificativa {doc.id} (sin restante)"
                )
                lote.referencia_anulacion = doc.id
                continue
            if abs(restante - float(lote.cantidad)) > 1e-6:
                raise RuntimeError(
                    f"Lote {lote.id} parcialmente consumido "
                    f"(restante {restante:g} ≠ original {lote.cantidad:g}); "
                    "rectificación bloqueada."
                )
            espejo = mov.crear_movimiento(
                producto_id=orig_ln.producto_id,
                lote_id=orig_ln.lote_id,
                tipo=TipoMovimiento.REVERSION_ENTRADA,
                direccion=DireccionMovimiento.SALIDA,
                cantidad=restante,
                fecha=date.today(),
                origen_tipo=ORIGEN_TIPO_RECTIFICATIVA,
                origen_id=doc.id,
                origen_linea_id=ln.id,
                movimiento_revertido_id=orig_ln.movimiento_id,
                ubicacion_origen_id=orig_ln.ubicacion_destino_id,
                usuario_id=getattr(getattr(c, "actor", None), "id", None),
                ctx=c,
                commit=False,
            )
            if not espejo.ok and not espejo.duplicado:
                raise RuntimeError(espejo.mensaje)
            lote.cantidad_restante = 0.0
            lote.anulado = True
            lote.fecha_anulacion = date.today()
            lote.motivo_anulacion = (
                doc.motivo_rectificacion or f"Rectificativa {doc.id}"
            ).strip()
            lote.referencia_anulacion = doc.id

        for aid in doc.archivo_ids:
            arch = next(
                (
                    a
                    for a in getattr(data, "archivos_documentales", []) or []
                    if a.id == aid
                ),
                None,
            )
            if arch is not None:
                arch.documento_id = doc.id

        ahora = datetime.now()
        original.estado = EstadoDocumento.RECTIFICADO
        original.rectificado_en = ahora
        doc.estado = EstadoDocumento.CONFIRMADO
        doc.confirmado_en = ahora
        data.actividades.insert(
            0,
            Actividad(
                next_id("act", [a.id for a in data.actividades]),
                ahora,
                getattr(getattr(c, "actor", None), "nombre", None) or "Sistema",
                "Confirmar rectificativa",
                f"{doc.id} rectifica {original.id}: {doc.motivo_rectificacion}",
            ),
        )
        if commit:
            c.uow.commit(data)
        return ResultadoRectificativa(
            True, f"Rectificativa {doc.id} confirmada; {original.id} → rectificado.", doc
        )
    except Exception as exc:  # noqa: BLE001
        restaurar_cantidades_restantes(data, snap)
        del data.movimientos[n_mov:]
        del data.actividades[n_act:]
        for lote in data.lotes:
            flags = lote_flags.get(lote.id)
            if flags is None:
                continue
            (
                lote.anulado,
                lote.fecha_anulacion,
                lote.motivo_anulacion,
                lote.referencia_anulacion,
                lote.anulado_por,
            ) = flags
        for a in getattr(data, "archivos_documentales", []) or []:
            if a.id in archivos_backup:
                a.documento_id = archivos_backup[a.id]
        original.estado = orig_estado_prev
        original.rectificado_en = orig_rect_en_prev
        doc.estado = EstadoDocumento.BORRADOR
        doc.confirmado_en = None
        return ResultadoRectificativa(False, f"Confirmación abortada: {exc}", doc)


def anular_rectificativa(
    documento_id: str,
    *,
    motivo: str | None = None,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoRectificativa:
    """Solo borradores. Confirmada = append-only en F12."""
    c = _ctx(ctx)
    data = c.uow.get_data()
    doc = buscar_documento(data, documento_id)
    if doc is None:
        return ResultadoRectificativa(False, "Documento no encontrado.")
    if _tipo(doc) != TipoDocumento.RECTIFICATIVA.value:
        return ResultadoRectificativa(False, "El documento no es una rectificativa.")
    estado = _estado(doc)
    if estado == EstadoDocumento.ANULADO.value:
        return ResultadoRectificativa(False, "Ya está anulada.")
    if estado == EstadoDocumento.CONFIRMADO.value:
        return ResultadoRectificativa(
            False,
            "No se anula una rectificativa confirmada en F12 (append-only).",
        )
    if estado != EstadoDocumento.BORRADOR.value:
        return ResultadoRectificativa(False, f"Estado no anulable: {estado}")

    doc.estado = EstadoDocumento.ANULADO
    doc.anulado_en = datetime.now()
    doc.motivo_anulacion = (motivo or "").strip() or "Borrador descartado"
    if commit:
        c.uow.commit(data)
    return ResultadoRectificativa(True, f"Borrador {doc.id} anulado.", doc)
