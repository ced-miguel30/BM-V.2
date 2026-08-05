"""Facturas + conciliación con albaranes (Fase 11).

- Línea con documento_origen_id/linea_origen_id → conciliación (solo metadatos; sin stock).
- Línea sin origen → factura directa → lote + entrada_factura (atómico).
- P04 cerrado: conciliación = metadatos; sin movimiento neutro en ledger.
- Sin rectificativas (F12). ID técnico ≠ referencia_externa.
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
from app.core.services.albaran_service import buscar_documento
from app.core.services.inventory_batch_service import (
    restaurar_cantidades_restantes,
    snapshot_cantidades_restantes,
)
from app.core.services.proveedor_service import snapshot_proveedor
from app.core.services.ubicacion_stock_service import validar_ubicacion_catalogo
from app.core.storage.session_store import get_data, persist_data

ORIGEN_TIPO_FACTURA = "factura"
ORIGEN_TIPO_ANULACION_FACTURA = "anulacion_factura"


@dataclass
class ResultadoFactura:
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


def listar_facturas(
    ctx: AppContext | None = None,
    *,
    estado: str | None = None,
) -> list[Documento]:
    data = _ctx(ctx).uow.get_data()
    docs = [
        d
        for d in getattr(data, "documentos", []) or []
        if _tipo(d) == TipoDocumento.FACTURA.value
    ]
    if estado:
        docs = [d for d in docs if _estado(d) == estado]
    return sorted(docs, key=lambda d: (d.fecha_documento, d.id), reverse=True)


def linea_albaran_ya_conciliada(
    data: AppData,
    linea_albaran_id: str,
    *,
    excluir_factura_id: str | None = None,
) -> Documento | None:
    """Devuelve la factura confirmada que ya usa esa línea de albarán, si existe."""
    for d in getattr(data, "documentos", []) or []:
        if _tipo(d) != TipoDocumento.FACTURA.value:
            continue
        if _estado(d) != EstadoDocumento.CONFIRMADO.value:
            continue
        if excluir_factura_id and d.id == excluir_factura_id:
            continue
        for ln in d.lineas:
            if ln.linea_origen_id == linea_albaran_id:
                return d
    return None


def crear_borrador_factura(
    *,
    fecha_documento: date | None = None,
    proveedor_id: str | None = None,
    referencia_externa: str | None = None,
    notas: str | None = None,
    archivo_ids: list[str] | None = None,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoFactura:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)
    if denied:
        return ResultadoFactura(False, denied)

    c = _ctx(ctx)
    data = c.uow.get_data()
    if not hasattr(data, "documentos") or data.documentos is None:
        data.documentos = []

    snap_nombre = None
    snap_nif = None
    if proveedor_id:
        prov = next((p for p in data.proveedores if p.id == proveedor_id), None)
        if prov is None:
            return ResultadoFactura(False, f"Proveedor inexistente: {proveedor_id}")
        snap_nombre, snap_nif = snapshot_proveedor(prov)

    for aid in archivo_ids or []:
        if not any(a.id == aid for a in getattr(data, "archivos_documentales", []) or []):
            return ResultadoFactura(False, f"Archivo inexistente: {aid}")

    doc = Documento(
        id=next_id("doc", [d.id for d in data.documentos]),
        tipo=TipoDocumento.FACTURA,
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
            "Crear factura borrador",
            f"{doc.id} · ref={doc.referencia_externa or '—'}",
        ),
    )
    if commit:
        c.uow.commit(data)
    return ResultadoFactura(True, f"Factura borrador {doc.id} creada.", doc)


def anadir_linea_factura(
    documento_id: str,
    *,
    producto_id: str,
    cantidad: float,
    precio_total: float,
    ubicacion_destino_id: str | None = None,
    impuesto_id: str | None = None,
    fecha_expiracion: date | None = None,
    documento_origen_id: str | None = None,
    linea_origen_id: str | None = None,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoFactura:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)
    if denied:
        return ResultadoFactura(False, denied)

    c = _ctx(ctx)
    data = c.uow.get_data()
    doc = buscar_documento(data, documento_id)
    if doc is None:
        return ResultadoFactura(False, "Documento no encontrado.")
    if _estado(doc) != EstadoDocumento.BORRADOR.value:
        return ResultadoFactura(False, "Solo se editan facturas en borrador.")
    if _tipo(doc) != TipoDocumento.FACTURA.value:
        return ResultadoFactura(False, "El documento no es una factura.")

    try:
        qty = float(cantidad)
        precio = float(precio_total)
    except (TypeError, ValueError):
        return ResultadoFactura(False, "Cantidad o precio no numéricos.")
    if qty <= 0:
        return ResultadoFactura(False, "La cantidad debe ser > 0.")
    if precio < 0:
        return ResultadoFactura(False, "El precio no puede ser negativo.")

    prod = next((p for p in data.productos if p.id == producto_id), None)
    if prod is None:
        return ResultadoFactura(False, "Producto no encontrado.")

    origen_doc_id = (documento_origen_id or "").strip() or None
    origen_ln_id = (linea_origen_id or "").strip() or None
    if bool(origen_doc_id) != bool(origen_ln_id):
        return ResultadoFactura(
            False,
            "Conciliación requiere documento_origen_id y linea_origen_id juntos.",
        )
    if origen_ln_id:
        err = _validar_enlace_albaran(
            data,
            documento_origen_id=origen_doc_id,  # type: ignore[arg-type]
            linea_origen_id=origen_ln_id,
            producto_id=producto_id,
            excluir_factura_id=doc.id,
        )
        if err:
            return ResultadoFactura(False, err)

    ubi = ubicacion_destino_id
    if origen_ln_id:
        # Conciliación: no exige ubicación (no crea stock)
        ubi = None
    elif ubi:
        err_u = validar_ubicacion_catalogo(data, ubi)
        if err_u:
            return ResultadoFactura(False, err_u)
    elif getattr(prod, "ubicacion_ids", None):
        ubi = prod.ubicacion_ids[0]

    pct_snap = None
    if impuesto_id:
        imp = next((i for i in data.impuestos if i.id == impuesto_id), None)
        if imp is None:
            return ResultadoFactura(False, "Impuesto no encontrado.")
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
        documento_origen_id=origen_doc_id,
        linea_origen_id=origen_ln_id,
    )
    doc.lineas.append(linea)
    if commit:
        c.uow.commit(data)
    modo = "conciliación" if origen_ln_id else "factura directa"
    return ResultadoFactura(True, f"Línea {linea.id} añadida ({modo}).", doc)


def _validar_enlace_albaran(
    data: AppData,
    *,
    documento_origen_id: str,
    linea_origen_id: str,
    producto_id: str,
    excluir_factura_id: str | None = None,
) -> str | None:
    alb = buscar_documento(data, documento_origen_id)
    if alb is None:
        return f"Albarán origen inexistente: {documento_origen_id}"
    if _tipo(alb) != TipoDocumento.ALBARAN.value:
        return "El documento origen no es un albarán."
    if _estado(alb) != EstadoDocumento.CONFIRMADO.value:
        return "Solo se concilian albaranes confirmados."
    ln = next((x for x in alb.lineas if x.id == linea_origen_id), None)
    if ln is None:
        return f"Línea de albarán inexistente: {linea_origen_id}"
    if ln.producto_id != producto_id:
        return (
            f"Producto de factura ({producto_id}) ≠ "
            f"producto de línea albarán ({ln.producto_id})."
        )
    otra = linea_albaran_ya_conciliada(
        data, linea_origen_id, excluir_factura_id=excluir_factura_id
    )
    if otra is not None:
        return f"Línea albarán {linea_origen_id} ya conciliada en factura {otra.id}."
    return None


def preview_confirmacion(doc: Documento) -> list[str]:
    if not doc.lineas:
        return ["Sin líneas: no se puede confirmar."]
    out = []
    for ln in doc.lineas:
        if ln.linea_origen_id:
            out.append(
                f"{ln.id}: CONCILIACIÓN · {ln.producto_nombre_snapshot or ln.producto_id} "
                f"× {ln.cantidad:g} · {ln.precio_total:.2f} € "
                f"↔ alb {ln.documento_origen_id}/{ln.linea_origen_id} (sin stock)"
            )
        else:
            out.append(
                f"{ln.id}: FACTURA DIRECTA · {ln.producto_nombre_snapshot or ln.producto_id} "
                f"× {ln.cantidad:g} → lote nuevo · {ln.precio_total:.2f} €"
            )
    return out


def confirmar_factura(
    documento_id: str,
    *,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoFactura:
    """Atómico. Conciliación = metadatos; directa = lotes + entrada_factura."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)
    if denied:
        return ResultadoFactura(False, denied)

    c = _ctx(ctx)
    data = c.uow.get_data()
    doc = buscar_documento(data, documento_id)
    if doc is None:
        return ResultadoFactura(False, "Documento no encontrado.")
    if _estado(doc) != EstadoDocumento.BORRADOR.value:
        return ResultadoFactura(False, "Solo se confirman borradores.")
    if _tipo(doc) != TipoDocumento.FACTURA.value:
        return ResultadoFactura(False, "El documento no es una factura.")
    if not doc.lineas:
        return ResultadoFactura(False, "La factura no tiene líneas.")

    # Revalidar enlaces de conciliación
    for ln in doc.lineas:
        if ln.linea_origen_id:
            err = _validar_enlace_albaran(
                data,
                documento_origen_id=ln.documento_origen_id or "",
                linea_origen_id=ln.linea_origen_id,
                producto_id=ln.producto_id,
                excluir_factura_id=doc.id,
            )
            if err:
                return ResultadoFactura(False, err)

    if not hasattr(data, "movimientos") or data.movimientos is None:
        data.movimientos = []

    snap = snapshot_cantidades_restantes(data)
    n_lotes = len(data.lotes)
    n_mov = len(data.movimientos)
    n_act = len(data.actividades)
    lineas_backup = [(ln.lote_id, ln.movimiento_id) for ln in doc.lineas]
    archivos_backup = {
        a.id: a.documento_id
        for a in getattr(data, "archivos_documentales", []) or []
        if a.id in (doc.archivo_ids or [])
    }

    try:
        marca = doc.proveedor_nombre_snapshot
        n_directas = 0
        n_conc = 0
        for ln in doc.lineas:
            if ln.linea_origen_id:
                # Solo metadatos — sin lote ni movimiento
                ln.lote_id = None
                ln.movimiento_id = None
                n_conc += 1
                continue

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
                tipo=TipoMovimiento.ENTRADA_FACTURA,
                direccion=DireccionMovimiento.ENTRADA,
                cantidad=float(ln.cantidad),
                fecha=doc.fecha_documento,
                origen_tipo=ORIGEN_TIPO_FACTURA,
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
            n_directas += 1

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
                "Confirmar factura",
                f"{doc.id}: {n_conc} conciliación(es), {n_directas} directa(s)",
            ),
        )
        if commit:
            c.uow.commit(data)
        return ResultadoFactura(True, f"Factura {doc.id} confirmada.", doc)
    except Exception as exc:  # noqa: BLE001
        restaurar_cantidades_restantes(data, snap)
        del data.lotes[n_lotes:]
        del data.movimientos[n_mov:]
        del data.actividades[n_act:]
        for ln, (lid, mid) in zip(doc.lineas, lineas_backup):
            ln.lote_id = lid
            ln.movimiento_id = mid
        for a in getattr(data, "archivos_documentales", []) or []:
            if a.id in archivos_backup:
                a.documento_id = archivos_backup[a.id]
        doc.estado = EstadoDocumento.BORRADOR
        doc.confirmado_en = None
        return ResultadoFactura(False, f"Confirmación abortada: {exc}", doc)


def anular_factura(
    documento_id: str,
    *,
    motivo: str | None = None,
    ctx: AppContext | None = None,
    commit: bool = True,
) -> ResultadoFactura:
    """Anula factura. Conciliación: libera enlace. Directa: reverso de restante."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)
    if denied:
        return ResultadoFactura(False, denied)

    c = _ctx(ctx)
    data = c.uow.get_data()
    doc = buscar_documento(data, documento_id)
    if doc is None:
        return ResultadoFactura(False, "Documento no encontrado.")
    if _tipo(doc) != TipoDocumento.FACTURA.value:
        return ResultadoFactura(False, "El documento no es una factura.")
    estado = _estado(doc)
    if estado == EstadoDocumento.ANULADO.value:
        return ResultadoFactura(False, "Ya está anulada.")
    if estado == EstadoDocumento.RECTIFICADO.value:
        return ResultadoFactura(
            False,
            "Documento rectificado: no se anula; consultar la rectificativa.",
        )
    if estado == EstadoDocumento.BORRADOR.value:
        doc.estado = EstadoDocumento.ANULADO
        doc.anulado_en = datetime.now()
        doc.motivo_anulacion = (motivo or "").strip() or "Borrador descartado"
        if commit:
            c.uow.commit(data)
        return ResultadoFactura(True, f"Borrador {doc.id} anulado.", doc)
    if estado != EstadoDocumento.CONFIRMADO.value:
        return ResultadoFactura(False, f"Estado no anulable: {estado}")

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
            if ln.linea_origen_id:
                # Conciliación: nada que revertir en stock
                continue
            if not ln.lote_id:
                continue
            lote = next((l for l in data.lotes if l.id == ln.lote_id), None)
            if lote is None:
                continue
            restante = float(lote.cantidad_restante)
            if restante <= 1e-9:
                lote.anulado = True
                lote.fecha_anulacion = date.today()
                lote.motivo_anulacion = f"Anulación factura {doc.id} (sin restante)"
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
                origen_tipo=ORIGEN_TIPO_ANULACION_FACTURA,
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
            lote.motivo_anulacion = (motivo or f"Anulación factura {doc.id}").strip()
            lote.referencia_anulacion = doc.id

        doc.estado = EstadoDocumento.ANULADO
        doc.anulado_en = datetime.now()
        doc.motivo_anulacion = (motivo or "").strip() or "Anulación de factura"
        data.actividades.insert(
            0,
            Actividad(
                next_id("act", [a.id for a in data.actividades]),
                datetime.now(),
                getattr(getattr(c, "actor", None), "nombre", None) or "Sistema",
                "Anular factura",
                f"{doc.id}: {doc.motivo_anulacion}",
            ),
        )
        if commit:
            c.uow.commit(data)
        return ResultadoFactura(True, f"Factura {doc.id} anulada.", doc)
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
        return ResultadoFactura(False, f"Anulación abortada: {exc}", doc)
