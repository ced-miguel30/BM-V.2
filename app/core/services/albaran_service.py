"""Albaranes → entrada de inventario (Fase 10).

Confirmación atómica: documento + lotes + movimientos ledger.
Sin facturas (F11). ID técnico ≠ referencia_externa del proveedor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.core.application.context import AppContext
from app.core.application.id_generator import next_id
from app.core.models import (
    Actividad,
    AppData,
    Documento,
    EstadoDocumento,
    LineaDocumento,
    LoteStock,
    TipoDocumento,
)
from app.core.models.enums import DireccionMovimiento, TipoMovimiento
from app.core.services import movimiento_service as mov
from app.core.services.inventory_batch_service import (
    restaurar_cantidades_restantes,
    snapshot_cantidades_restantes,
)
from app.core.services.proveedor_service import snapshot_proveedor
from app.core.services.ubicacion_stock_service import validar_ubicacion_catalogo
from app.core.storage.session_store import get_data, persist_data

ORIGEN_TIPO_ALBARAN = "albaran"
ORIGEN_TIPO_ANULACION_ALBARAN = "anulacion_albaran"


@dataclass
class ResultadoAlbaran:
    ok: bool
    mensaje: str
    documento: Documento | None = None


def _ctx(ctx: AppContext | None = None) -> AppContext:
    if ctx is not None:
        return ctx
    from app.core.application.actor import actor_desde_appdata
    from app.core.application.clock import SystemClock
    from app.core.application.unit_of_work import InMemoryUnitOfWork

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


def listar_albaranes(
    ctx: AppContext | None = None,
    *,
    estado: str | None = None,
) -> list[Documento]:
    data = _ctx(ctx).uow.get_data()
    docs = [
        d
        for d in getattr(data, "documentos", []) or []
        if _tipo(d) == TipoDocumento.ALBARAN.value
    ]
    if estado:
        docs = [d for d in docs if _estado(d) == estado]
    return sorted(docs, key=lambda d: (d.fecha_documento, d.id), reverse=True)


def buscar_documento(data: AppData, doc_id: str) -> Documento | None:
    return next((d for d in getattr(data, "documentos", []) or [] if d.id == doc_id), None)


def crear_borrador_albaran(
    *,
    fecha_documento: date | None = None,
    proveedor_id: str | None = None,
    referencia_externa: str | None = None,
    notas: str | None = None,
    archivo_ids: list[str] | None = None,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoAlbaran:
    c = _ctx(ctx)
    data = c.uow.get_data()
    if not hasattr(data, "documentos") or data.documentos is None:
        data.documentos = []

    snap_nombre = None
    snap_nif = None
    if proveedor_id:
        prov = next((p for p in data.proveedores if p.id == proveedor_id), None)
        if prov is None:
            return ResultadoAlbaran(False, f"Proveedor inexistente: {proveedor_id}")
        snap_nombre, snap_nif = snapshot_proveedor(prov)

    for aid in archivo_ids or []:
        if not any(a.id == aid for a in getattr(data, "archivos_documentales", []) or []):
            return ResultadoAlbaran(False, f"Archivo inexistente: {aid}")

    doc = Documento(
        id=next_id("doc", [d.id for d in data.documentos]),
        tipo=TipoDocumento.ALBARAN,
        estado=EstadoDocumento.BORRADOR,
        fecha_documento=fecha_documento
        or (c.clock.today() if getattr(c, "clock", None) else date.today()),
        proveedor_id=proveedor_id,
        proveedor_nombre_snapshot=snap_nombre,
        nif_cif_snapshot=snap_nif,
        referencia_externa=(referencia_externa or "").strip() or None,
        lineas=[],
        archivo_ids=list(archivo_ids or []),
        registrado_por=getattr(getattr(c, "actor", None), "nombre", None) or "Sistema",
        hora=c.clock.now().time() if getattr(c, "clock", None) else None,
        creado_en=datetime.now(),
        notas=(notas or "").strip() or None,
    )
    data.documentos.append(doc)
    data.actividades.insert(
        0,
        Actividad(
            next_id("act", [a.id for a in data.actividades]),
            datetime.now(),
            doc.registrado_por,
            "Crear albarán borrador",
            f"{doc.id} · ref={doc.referencia_externa or '—'}",
        ),
    )
    if commit:
        c.uow.commit(data)
    return ResultadoAlbaran(True, f"Albarán borrador {doc.id} creado.", doc)


def anadir_linea_albaran(
    documento_id: str,
    *,
    producto_id: str,
    cantidad: float,
    precio_total: float,
    ubicacion_destino_id: str | None = None,
    impuesto_id: str | None = None,
    fecha_expiracion: date | None = None,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoAlbaran:
    c = _ctx(ctx)
    data = c.uow.get_data()
    doc = buscar_documento(data, documento_id)
    if doc is None:
        return ResultadoAlbaran(False, "Documento no encontrado.")
    if _estado(doc) != EstadoDocumento.BORRADOR.value:
        return ResultadoAlbaran(False, "Solo se editan albaranes en borrador.")
    if _tipo(doc) != TipoDocumento.ALBARAN.value:
        return ResultadoAlbaran(False, "El documento no es un albarán.")

    try:
        qty = float(cantidad)
        precio = float(precio_total)
    except (TypeError, ValueError):
        return ResultadoAlbaran(False, "Cantidad o precio no numéricos.")
    if qty <= 0:
        return ResultadoAlbaran(False, "La cantidad debe ser > 0.")
    if precio < 0:
        return ResultadoAlbaran(False, "El precio no puede ser negativo.")

    prod = next((p for p in data.productos if p.id == producto_id), None)
    if prod is None:
        return ResultadoAlbaran(False, "Producto no encontrado.")

    ubi = ubicacion_destino_id
    if ubi:
        err = validar_ubicacion_catalogo(data, ubi)
        if err:
            return ResultadoAlbaran(False, err)
    elif getattr(prod, "ubicacion_ids", None):
        ubi = prod.ubicacion_ids[0]

    pct_snap = None
    if impuesto_id:
        imp = next((i for i in data.impuestos if i.id == impuesto_id), None)
        if imp is None:
            return ResultadoAlbaran(False, "Impuesto no encontrado.")
        pct_snap = Decimal(str(imp.porcentaje))

    linea = LineaDocumento(
        id=next_id("ln", [ln.id for ln in doc.lineas]),
        producto_id=producto_id,
        cantidad=round(qty, 4),
        precio_total=round(precio, 2),
        impuesto_id=impuesto_id,
        impuesto_porcentaje_snapshot=pct_snap,
        ubicacion_destino_id=ubi,
        producto_nombre_snapshot=prod.nombre,
        unidad_snapshot=(
            prod.unidad.value if hasattr(prod.unidad, "value") else str(prod.unidad)
        ),
        fecha_expiracion=fecha_expiracion,
    )
    doc.lineas.append(linea)
    if commit:
        c.uow.commit(data)
    return ResultadoAlbaran(True, f"Línea {linea.id} añadida.", doc)


def preview_confirmacion(doc: Documento) -> list[str]:
    if not doc.lineas:
        return ["Sin líneas: no se puede confirmar."]
    out = []
    for ln in doc.lineas:
        out.append(
            f"{ln.id}: {ln.producto_nombre_snapshot or ln.producto_id} "
            f"× {ln.cantidad:g} → lote nuevo · {ln.precio_total:.2f} €"
            + (f" · ubi {ln.ubicacion_destino_id}" if ln.ubicacion_destino_id else "")
        )
    return out


def confirmar_albaran(
    documento_id: str,
    *,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoAlbaran:
    """Atómico: lotes + movimientos entrada_albaran + estado confirmado."""
    c = _ctx(ctx)
    data = c.uow.get_data()
    doc = buscar_documento(data, documento_id)
    if doc is None:
        return ResultadoAlbaran(False, "Documento no encontrado.")
    if _estado(doc) != EstadoDocumento.BORRADOR.value:
        return ResultadoAlbaran(False, "Solo se confirman borradores.")
    if not doc.lineas:
        return ResultadoAlbaran(False, "El albarán no tiene líneas.")

    if not hasattr(data, "movimientos") or data.movimientos is None:
        data.movimientos = []

    snap = snapshot_cantidades_restantes(data)
    n_lotes = len(data.lotes)
    n_mov = len(data.movimientos)
    n_act = len(data.actividades)
    lineas_backup = [
        (ln.lote_id, ln.movimiento_id) for ln in doc.lineas
    ]

    try:
        marca = doc.proveedor_nombre_snapshot
        for ln in doc.lineas:
            lote = LoteStock(
                next_id("l", [l.id for l in data.lotes]),
                ln.producto_id,
                round(float(ln.precio_total), 2),
                float(ln.cantidad),
                float(ln.cantidad),
                doc.fecha_documento,
                ln.fecha_expiracion,
                marca,
                None,
            )
            data.lotes.append(lote)
            espejo = mov.crear_movimiento(
                producto_id=ln.producto_id,
                lote_id=lote.id,
                tipo=TipoMovimiento.ENTRADA_ALBARAN,
                direccion=DireccionMovimiento.ENTRADA,
                cantidad=float(ln.cantidad),
                fecha=doc.fecha_documento,
                origen_tipo=ORIGEN_TIPO_ALBARAN,
                origen_id=doc.id,
                origen_linea_id=ln.id,
                hora=doc.hora,
                usuario_id=getattr(getattr(c, "actor", None), "id", None),
                coste_unitario_snapshot=(
                    round(float(ln.precio_total) / float(ln.cantidad), 6)
                    if float(ln.cantidad) > 0
                    else None
                ),
                coste_total_snapshot=round(float(ln.precio_total), 2),
                ubicacion_destino_id=ln.ubicacion_destino_id,
                ctx=c,
                commit=False,
            )
            if not espejo.ok and not espejo.duplicado:
                raise RuntimeError(espejo.mensaje)
            ln.lote_id = lote.id
            ln.movimiento_id = espejo.movimiento.id if espejo.movimiento else None

        # Enlazar archivos al documento
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

        doc.estado = EstadoDocumento.CONFIRMADO
        doc.confirmado_en = datetime.now()
        data.actividades.insert(
            0,
            Actividad(
                next_id("act", [a.id for a in data.actividades]),
                datetime.now(),
                getattr(getattr(c, "actor", None), "nombre", None) or "Sistema",
                "Confirmar albarán",
                f"{doc.id}: {len(doc.lineas)} línea(s) → lotes + ledger",
            ),
        )
        if commit:
            c.uow.commit(data)
        return ResultadoAlbaran(True, f"Albarán {doc.id} confirmado.", doc)
    except Exception as exc:  # noqa: BLE001
        restaurar_cantidades_restantes(data, snap)
        del data.lotes[n_lotes:]
        del data.movimientos[n_mov:]
        del data.actividades[n_act:]
        for ln, (lid, mid) in zip(doc.lineas, lineas_backup):
            ln.lote_id = lid
            ln.movimiento_id = mid
        doc.estado = EstadoDocumento.BORRADOR
        doc.confirmado_en = None
        return ResultadoAlbaran(False, f"Confirmación abortada: {exc}", doc)


def anular_albaran(
    documento_id: str,
    *,
    motivo: str | None = None,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoAlbaran:
    """Anula confirmado: reversion_entrada por restante de cada lote; append-only."""
    c = _ctx(ctx)
    data = c.uow.get_data()
    doc = buscar_documento(data, documento_id)
    if doc is None:
        return ResultadoAlbaran(False, "Documento no encontrado.")
    estado = _estado(doc)
    if estado == EstadoDocumento.ANULADO.value:
        return ResultadoAlbaran(False, "Ya está anulado.")
    if estado == EstadoDocumento.BORRADOR.value:
        doc.estado = EstadoDocumento.ANULADO
        doc.anulado_en = datetime.now()
        doc.motivo_anulacion = (motivo or "").strip() or "Borrador descartado"
        if commit:
            c.uow.commit(data)
        return ResultadoAlbaran(True, f"Borrador {doc.id} anulado.", doc)
    if estado != EstadoDocumento.CONFIRMADO.value:
        return ResultadoAlbaran(False, f"Estado no anulable: {estado}")

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
    doc_estado_prev = doc.estado
    doc_anulado_en_prev = doc.anulado_en
    doc_motivo_prev = doc.motivo_anulacion
    try:
        for ln in doc.lineas:
            if not ln.lote_id:
                continue
            lote = next((l for l in data.lotes if l.id == ln.lote_id), None)
            if lote is None:
                continue
            restante = float(lote.cantidad_restante)
            if restante <= 1e-9:
                lote.anulado = True
                lote.fecha_anulacion = date.today()
                lote.motivo_anulacion = f"Anulación albarán {doc.id} (sin restante)"
                lote.referencia_anulacion = doc.id
                continue
            if abs(restante - float(lote.cantidad)) > 1e-6:
                raise RuntimeError(
                    f"Lote {lote.id} parcialmente consumido "
                    f"(restante {restante:g} ≠ original {lote.cantidad:g}); "
                    "anulación bloqueada."
                )
            espejo = mov.crear_movimiento(
                producto_id=ln.producto_id,
                lote_id=ln.lote_id,
                tipo=TipoMovimiento.REVERSION_ENTRADA,
                direccion=DireccionMovimiento.SALIDA,
                cantidad=restante,
                fecha=date.today(),
                origen_tipo=ORIGEN_TIPO_ANULACION_ALBARAN,
                origen_id=doc.id,
                origen_linea_id=ln.id,
                movimiento_revertido_id=ln.movimiento_id,
                ubicacion_origen_id=ln.ubicacion_destino_id,
                usuario_id=getattr(getattr(c, "actor", None), "id", None),
                ctx=c,
                commit=False,
            )
            if not espejo.ok and not espejo.duplicado:
                raise RuntimeError(espejo.mensaje)
            lote.cantidad_restante = 0.0
            lote.anulado = True
            lote.fecha_anulacion = date.today()
            lote.motivo_anulacion = (motivo or f"Anulación albarán {doc.id}").strip()
            lote.referencia_anulacion = doc.id

        doc.estado = EstadoDocumento.ANULADO
        doc.anulado_en = datetime.now()
        doc.motivo_anulacion = (motivo or "").strip() or "Anulación de albarán"
        data.actividades.insert(
            0,
            Actividad(
                next_id("act", [a.id for a in data.actividades]),
                datetime.now(),
                getattr(getattr(c, "actor", None), "nombre", None) or "Sistema",
                "Anular albarán",
                f"{doc.id}: {doc.motivo_anulacion}",
            ),
        )
        if commit:
            c.uow.commit(data)
        return ResultadoAlbaran(True, f"Albarán {doc.id} anulado.", doc)
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
        doc.estado = doc_estado_prev
        doc.anulado_en = doc_anulado_en_prev
        doc.motivo_anulacion = doc_motivo_prev
        return ResultadoAlbaran(False, f"Anulación abortada: {exc}", doc)
