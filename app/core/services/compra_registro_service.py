"""Registro de compras — borrador SoT + confirmación idempotente (B3 + B1).

Flujo crítico usa ``transactional_update_appdata`` (A2). No muta AppData de
sesión hasta confirmar disco cuando se pasa ``json_path``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

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
from app.core.models.conciliacion import ConciliacionLineaDocumento, EstadoConciliacion
from app.core.models.enums import DireccionMovimiento, TipoMovimiento
from app.core.services import movimiento_service as mov
from app.core.services.contenido_hash import (
    contenido_hash_intencion,
    payload_intencion_documento,
)
from app.core.services.conversion_compra import (
    ConversionDesconocidaError,
    resolver_factor_conversion,
)
from app.core.services.documento_totales import recalcular_totales_documento
from app.core.services.money import as_decimal, money_round
from app.core.services.persistencia_appdata import (
    read_appdata_json,
    transactional_update_appdata,
)
from app.core.services.proveedor_service import snapshot_proveedor


ALERTA_PRECIO_PCT_DEFAULT = Decimal("10")

CONFIRMACION_OK = "ok"
CONFIRMACION_IDEMPOTENTE = "idempotente"
CONFIRMACION_CONFLICTO = "CONFIRMACION_CONFLICTO"
CONFIRMACION_ID_DUPLICADO = "CONFIRMACION_ID_DUPLICADO"
YA_CONFIRMADO = "YA_CONFIRMADO"


@dataclass
class AdjuntoEntrada:
    """Bytes de un adjunto nuevo a publicar en la misma confirmación (§5)."""

    contenido: bytes
    nombre_original: str
    mime_type: str | None = None


@dataclass
class ResultadoCompra:
    ok: bool
    mensaje: str
    codigo: str = CONFIRMACION_OK
    documento: Documento | None = None
    alerta_precio: list[str] | None = None
    adjuntos_publicados: list[str] | None = None
    """storage_keys publicados en esta operación."""
    adjuntos_estado: str | None = None
    """ok | compensado | incierto — JSON+binario no son atómicos conjuntamente."""


def _estado(doc: Documento) -> str:
    e = doc.estado
    return e.value if hasattr(e, "value") else str(e)


def _tipo(doc: Documento) -> str:
    t = doc.tipo
    return t.value if hasattr(t, "value") else str(t)


def impacto_stock_dominio(
    tipo: str,
    *,
    tiene_conciliaciones: bool,
) -> bool:
    """D90: la UI no elige; el dominio decide."""
    t = (tipo or "").lower()
    if t == TipoDocumento.ALBARAN.value:
        return True
    if t == TipoDocumento.FACTURA.value:
        return not tiene_conciliaciones
    if t == TipoDocumento.RECTIFICATIVA.value:
        return False
    if t == "devolucion":
        return True  # salida; B2 implementará efecto
    return False


def referencia_duplicada(
    data: AppData,
    *,
    proveedor_id: str | None,
    referencia_externa: str | None,
    exclude_doc_id: str | None = None,
) -> bool:
    ref = (referencia_externa or "").strip().lower()
    if not ref or not proveedor_id:
        return False
    for d in data.documentos:
        if exclude_doc_id and d.id == exclude_doc_id:
            continue
        if d.proveedor_id != proveedor_id:
            continue
        if (d.referencia_externa or "").strip().lower() == ref:
            if _estado(d) != EstadoDocumento.ANULADO.value:
                return True
    return False


def alertas_subida_precio(
    data: AppData,
    doc: Documento,
    *,
    umbral_pct: Decimal = ALERTA_PRECIO_PCT_DEFAULT,
) -> list[str]:
    avisos: list[str] = []
    if not doc.proveedor_id:
        return avisos
    for ln in doc.lineas:
        if ln.precio_unitario_compra is None:
            continue
        rel = next(
            (
                r
                for r in getattr(data, "relaciones_producto_proveedor", []) or []
                if r.producto_id == ln.producto_id
                and r.proveedor_id == doc.proveedor_id
                and r.activo
                and getattr(r, "ultimo_precio_unitario_compra", None) is not None
            ),
            None,
        )
        if rel is None:
            continue
        ultimo = as_decimal(rel.ultimo_precio_unitario_compra)
        if ultimo <= 0:
            continue
        actual = as_decimal(ln.precio_unitario_compra)
        if actual > ultimo * (1 + umbral_pct / Decimal("100")):
            avisos.append(
                f"Línea {ln.id}: precio {actual} supera {umbral_pct}% sobre último {ultimo}"
            )
    return avisos


def construir_hash_documento(doc: Documento, conciliaciones: list[dict] | None = None) -> str:
    lineas_payload = []
    for ln in doc.lineas:
        lineas_payload.append(
            {
                "client_line_key": ln.client_line_key or ln.id,
                "producto_id": ln.producto_id,
                "cantidad_compra": ln.cantidad_compra,
                "cantidad_inventario": ln.cantidad_inventario,
                "unidad_compra": ln.unidad_compra,
                "unidad_inventario": ln.unidad_inventario,
                "factor_conversion": ln.factor_conversion,
                "precio_unitario_compra": ln.precio_unitario_compra,
                "precio_incluye_igic": bool(ln.precio_incluye_igic),
                "descuento_porcentaje": ln.descuento_porcentaje,
                "descuento_importe": ln.descuento_importe,
                "impuesto_id": ln.impuesto_id,
                "impuesto_porcentaje_snapshot": ln.impuesto_porcentaje_snapshot,
                "codigo_lote_proveedor": ln.codigo_lote_proveedor,
                "fecha_expiracion": (
                    ln.fecha_expiracion.isoformat() if ln.fecha_expiracion else None
                ),
                "ubicacion_destino_id": ln.ubicacion_destino_id,
            }
        )
    payload = payload_intencion_documento(
        tipo=_tipo(doc),
        proveedor_id=doc.proveedor_id,
        referencia_externa=doc.referencia_externa,
        fecha_documento=(
            doc.fecha_documento.isoformat() if doc.fecha_documento else None
        ),
        fecha_recepcion=(
            doc.fecha_recepcion.isoformat()
            if getattr(doc, "fecha_recepcion", None)
            else None
        ),
        ubicacion_entrada_id=getattr(doc, "ubicacion_entrada_id", None),
        moneda=getattr(doc, "moneda", None),
        descuento_cabecera_importe=doc.descuento_cabecera_importe,
        lineas=lineas_payload,
        conciliaciones_propuestas=conciliaciones,
    )
    return contenido_hash_intencion(payload)


def _preparar_lineas_compra(data: AppData, doc: Documento) -> None:
    """B1: resuelve factores y cantidad_inventario; recalcula totales."""
    for ln in doc.lineas:
        if not ln.client_line_key:
            ln.client_line_key = str(uuid.uuid4())
        if ln.cantidad_compra is None:
            raise ValueError(f"Línea {ln.id}: falta cantidad_compra.")
        if ln.precio_unitario_compra is None:
            raise ValueError(f"Línea {ln.id}: falta precio_unitario_compra.")
        prod = next((p for p in data.productos if p.id == ln.producto_id), None)
        if prod is None:
            raise ValueError(f"Producto inexistente: {ln.producto_id}")
        unidad_inv = ln.unidad_inventario or (
            prod.unidad.value if hasattr(prod.unidad, "value") else str(prod.unidad)
        )
        factor_cat = None
        if doc.proveedor_id:
            rel = next(
                (
                    r
                    for r in getattr(data, "relaciones_producto_proveedor", []) or []
                    if r.producto_id == ln.producto_id
                    and r.proveedor_id == doc.proveedor_id
                    and r.activo
                ),
                None,
            )
            if rel is not None:
                factor_cat = getattr(rel, "factor_compra", None)
        try:
            factor = resolver_factor_conversion(
                unidad_compra=ln.unidad_compra or unidad_inv,
                unidad_inventario=unidad_inv,
                factor_explicito=ln.factor_conversion,
                factor_catalogo=factor_cat,
            )
        except ConversionDesconocidaError as exc:
            raise ValueError(str(exc)) from exc
        ln.factor_conversion = factor
        ln.unidad_inventario = unidad_inv
        if not ln.unidad_compra:
            ln.unidad_compra = unidad_inv
        ln.cantidad_inventario = as_decimal(ln.cantidad_compra) * factor
        ln.producto_nombre_snapshot = ln.producto_nombre_snapshot or prod.nombre
        ln.unidad_snapshot = ln.unidad_snapshot or unidad_inv

    if recalcular_totales_documento(doc) is None:
        raise ValueError("No se pudieron recalcular totales documentales.")


def _aplicar_confirmacion(
    data: AppData,
    documento_id: str,
    *,
    confirmacion_id: str,
    contenido_hash: str,
    conciliaciones_propuestas: list[dict] | None,
) -> ResultadoCompra:
    doc = next((d for d in data.documentos if d.id == documento_id), None)
    if doc is None:
        return ResultadoCompra(False, "Documento no encontrado.")

    # Idempotencia / conflictos globales
    for other in data.documentos:
        cid = getattr(other, "confirmacion_id", None)
        if not cid or cid != confirmacion_id:
            continue
        if other.id == doc.id:
            if getattr(other, "contenido_hash", None) == contenido_hash:
                return ResultadoCompra(
                    True,
                    "Confirmación idempotente (sin cambios).",
                    codigo=CONFIRMACION_IDEMPOTENTE,
                    documento=other,
                )
            return ResultadoCompra(
                False,
                "Mismo confirmacion_id con contenido_hash distinto.",
                codigo=CONFIRMACION_CONFLICTO,
                documento=other,
            )
        return ResultadoCompra(
            False,
            f"confirmacion_id ya usado en documento {other.id}.",
            codigo=CONFIRMACION_ID_DUPLICADO,
        )

    if _estado(doc) == EstadoDocumento.CONFIRMADO.value:
        return ResultadoCompra(
            False,
            "Documento ya confirmado con otro token.",
            codigo=YA_CONFIRMADO,
            documento=doc,
        )
    if _estado(doc) != EstadoDocumento.BORRADOR.value:
        return ResultadoCompra(False, "Solo se confirman borradores.", documento=doc)

    esperado = construir_hash_documento(doc, conciliaciones_propuestas)
    if esperado != contenido_hash:
        return ResultadoCompra(
            False,
            "contenido_hash no coincide con la intención del borrador.",
            codigo=CONFIRMACION_CONFLICTO,
            documento=doc,
        )

    if referencia_duplicada(
        data,
        proveedor_id=doc.proveedor_id,
        referencia_externa=doc.referencia_externa,
        exclude_doc_id=doc.id,
    ):
        return ResultadoCompra(
            False,
            "referencia_externa duplicada para el mismo proveedor (bloqueo al confirmar).",
            documento=doc,
        )

    try:
        _preparar_lineas_compra(data, doc)
    except ValueError as exc:
        return ResultadoCompra(False, str(exc), documento=doc)

    keys = {ln.client_line_key for ln in doc.lineas}
    if len(keys) != len(doc.lineas):
        return ResultadoCompra(False, "client_line_key duplicada en el documento.")

    tiene_conc = bool(conciliaciones_propuestas)
    entra_stock = impacto_stock_dominio(_tipo(doc), tiene_conciliaciones=tiene_conc)
    doc.impacto_stock = entra_stock  # snapshot dominio (ignora UI)

    if not hasattr(data, "movimientos") or data.movimientos is None:
        data.movimientos = []
    if not hasattr(data, "conciliaciones_documento") or data.conciliaciones_documento is None:
        data.conciliaciones_documento = []

    avisos = alertas_subida_precio(data, doc)

    # Conciliaciones (factura sin stock)
    if tiene_conc and _tipo(doc) == TipoDocumento.FACTURA.value:
        for prop in conciliaciones_propuestas or []:
            lf = prop.get("linea_factura_id") or prop.get("linea_factura_client_key")
            la = prop.get("linea_albaran_id")
            qty = as_decimal(prop.get("cantidad_conciliada"))
            if qty <= 0:
                return ResultadoCompra(False, "cantidad_conciliada debe ser > 0.")
            # Resolver client_line_key → id
            ln_f = next(
                (
                    x
                    for x in doc.lineas
                    if x.id == lf or x.client_line_key == lf
                ),
                None,
            )
            if ln_f is None:
                return ResultadoCompra(False, f"Línea factura no encontrada: {lf}")
            ln_a = None
            doc_a = None
            for d in data.documentos:
                for x in d.lineas:
                    if x.id == la or x.client_line_key == la:
                        ln_a, doc_a = x, d
                        break
                if ln_a:
                    break
            if ln_a is None or doc_a is None:
                return ResultadoCompra(False, f"Línea albarán no encontrada: {la}")
            if _tipo(doc_a) != TipoDocumento.ALBARAN.value:
                return ResultadoCompra(False, "La línea origen no pertenece a un albarán.")
            if _estado(doc_a) != EstadoDocumento.CONFIRMADO.value:
                return ResultadoCompra(False, "El albarán debe estar confirmado.")
            if ln_f.producto_id != ln_a.producto_id:
                return ResultadoCompra(False, "Producto distinto en conciliación.")
            # Una activa por par
            if any(
                c.linea_factura_id == ln_f.id
                and c.linea_albaran_id == ln_a.id
                and (
                    c.estado.value if hasattr(c.estado, "value") else str(c.estado)
                )
                == EstadoConciliacion.ACTIVA.value
                for c in data.conciliaciones_documento
            ):
                return ResultadoCompra(
                    False, "Ya existe conciliación activa para ese par de líneas."
                )
            qty_a = as_decimal(ln_a.cantidad_inventario or ln_a.cantidad)
            qty_f = as_decimal(ln_f.cantidad_inventario or ln_f.cantidad)
            sum_a = sum(
                (
                    as_decimal(c.cantidad_conciliada)
                    for c in data.conciliaciones_documento
                    if c.linea_albaran_id == ln_a.id
                    and (
                        c.estado.value if hasattr(c.estado, "value") else str(c.estado)
                    )
                    == EstadoConciliacion.ACTIVA.value
                ),
                Decimal("0"),
            )
            sum_f = sum(
                (
                    as_decimal(c.cantidad_conciliada)
                    for c in data.conciliaciones_documento
                    if c.linea_factura_id == ln_f.id
                    and (
                        c.estado.value if hasattr(c.estado, "value") else str(c.estado)
                    )
                    == EstadoConciliacion.ACTIVA.value
                ),
                Decimal("0"),
            )
            if sum_a + qty > qty_a or sum_f + qty > qty_f:
                return ResultadoCompra(False, "Cantidad conciliada excede el tope.")
            cid = next_id("con", [c.id for c in data.conciliaciones_documento])
            data.conciliaciones_documento.append(
                ConciliacionLineaDocumento(
                    id=cid,
                    linea_factura_id=ln_f.id,
                    linea_albaran_id=ln_a.id,
                    cantidad_conciliada=qty,
                    fecha=doc.fecha_documento,
                    estado=EstadoConciliacion.ACTIVA,
                    importe_conciliado=(
                        as_decimal(prop["importe_conciliado"])
                        if prop.get("importe_conciliado") is not None
                        else None
                    ),
                    confirmacion_id=confirmacion_id,
                    creado_en=datetime.now(),
                )
            )

    # Entrada de stock (albarán / factura directa)
    if entra_stock:
        # Unicidad (documento_id, linea_id)
        for ln in doc.lineas:
            for m in data.movimientos:
                if (
                    m.origen_id == doc.id
                    and m.origen_linea_id == ln.id
                    and (
                        m.tipo.value if hasattr(m.tipo, "value") else str(m.tipo)
                    ).startswith("entrada")
                ):
                    return ResultadoCompra(
                        False,
                        f"Ya existe movimiento de entrada para línea {ln.id}.",
                    )
            qty = float(ln.cantidad_inventario or 0)
            if qty <= 0:
                return ResultadoCompra(False, f"cantidad_inventario inválida en {ln.id}")
            coste = as_decimal(ln.coste_inventariable_linea or 0)
            coste_unit = ln.coste_unitario_inventario
            lote = LoteStock(
                next_id("l", [l.id for l in data.lotes]),
                ln.producto_id,
                float(money_round(coste)),
                qty,
                qty,
                doc.fecha_documento,
                ln.fecha_expiracion,
                doc.proveedor_nombre_snapshot,
                None,
                documento_origen_id=doc.id,
                linea_documento_origen_id=ln.id,
            )
            data.lotes.append(lote)
            tipo_mov = (
                TipoMovimiento.ENTRADA_ALBARAN
                if _tipo(doc) == TipoDocumento.ALBARAN.value
                else TipoMovimiento.ENTRADA_FACTURA
            )
            from app.core.application.context import build_app_context
            from app.core.application.unit_of_work import InMemoryUnitOfWork

            ctx_local = build_app_context(uow=InMemoryUnitOfWork(data))
            espejo = mov.crear_movimiento(
                producto_id=ln.producto_id,
                lote_id=lote.id,
                tipo=tipo_mov,
                direccion=DireccionMovimiento.ENTRADA,
                cantidad=qty,
                fecha=doc.fecha_documento,
                origen_tipo=_tipo(doc),
                origen_id=doc.id,
                origen_linea_id=ln.id,
                hora=doc.hora,
                coste_unitario_snapshot=(
                    float(coste_unit) if coste_unit is not None else None
                ),
                coste_total_snapshot=float(money_round(coste)),
                ubicacion_destino_id=ln.ubicacion_destino_id
                or getattr(doc, "ubicacion_entrada_id", None),
                ctx=ctx_local,
                commit=False,
            )
            if not espejo.ok and not getattr(espejo, "duplicado", False):
                return ResultadoCompra(False, espejo.mensaje)
            ln.lote_id = lote.id
            ln.movimiento_id = espejo.movimiento.id if espejo.movimiento else None
            # Actualizar último precio relación
            if doc.proveedor_id and ln.precio_unitario_compra is not None:
                for r in getattr(data, "relaciones_producto_proveedor", []) or []:
                    if (
                        r.producto_id == ln.producto_id
                        and r.proveedor_id == doc.proveedor_id
                        and r.activo
                    ):
                        r.ultimo_precio_unitario_compra = as_decimal(
                            ln.precio_unitario_compra
                        )

    doc.estado = EstadoDocumento.CONFIRMADO
    doc.confirmado_en = datetime.now()
    doc.confirmacion_id = confirmacion_id
    doc.contenido_hash = contenido_hash
    data.actividades.insert(
        0,
        Actividad(
            next_id("act", [a.id for a in data.actividades]),
            datetime.now(),
            "Sistema",
            "Confirmar compra",
            f"{doc.id} token={confirmacion_id[:8]}… stock={entra_stock}",
        ),
    )
    return ResultadoCompra(
        True,
        f"Documento {doc.id} confirmado.",
        codigo=CONFIRMACION_OK,
        documento=doc,
        alerta_precio=avisos or None,
    )


def guardar_borrador(
    data: AppData,
    *,
    tipo: str = TipoDocumento.ALBARAN.value,
    fecha_documento: date | None = None,
    proveedor_id: str | None = None,
    referencia_externa: str | None = None,
    notas: str | None = None,
    moneda: str = "EUR",
    descuento_cabecera_importe: Decimal | str | float = 0,
    ubicacion_entrada_id: str | None = None,
    fecha_recepcion: date | None = None,
    lineas: list[dict] | None = None,
    documento_id: str | None = None,
) -> ResultadoCompra:
    """Crea o actualiza borrador en memoria (SoT). Persistencia = caller/A2."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)
    if denied:
        return ResultadoCompra(False, denied, codigo="no_autorizado")

    if documento_id:
        doc = next((d for d in data.documentos if d.id == documento_id), None)
        if doc is None:
            return ResultadoCompra(False, "Borrador no encontrado.")
        if _estado(doc) != EstadoDocumento.BORRADOR.value:
            return ResultadoCompra(False, "Solo se editan borradores.")
    else:
        if not hasattr(data, "documentos") or data.documentos is None:
            data.documentos = []
        snap_n = snap_f = None
        if proveedor_id:
            prov = next((p for p in data.proveedores if p.id == proveedor_id), None)
            if prov is None:
                return ResultadoCompra(False, f"Proveedor inexistente: {proveedor_id}")
            snap_n, snap_f = snapshot_proveedor(prov)
        doc = Documento(
            id=next_id("doc", [d.id for d in data.documentos]),
            tipo=tipo,
            estado=EstadoDocumento.BORRADOR,
            fecha_documento=fecha_documento or date.today(),
            proveedor_id=proveedor_id,
            proveedor_nombre_snapshot=snap_n,
            nif_cif_snapshot=snap_f,
            referencia_externa=(referencia_externa or "").strip() or None,
            notas=(notas or "").strip() or None,
            moneda=moneda,
            descuento_cabecera_importe=as_decimal(descuento_cabecera_importe),
            ubicacion_entrada_id=ubicacion_entrada_id,
            fecha_recepcion=fecha_recepcion,
            creado_en=datetime.now(),
            lineas=[],
        )
        data.documentos.append(doc)

    if lineas is not None:
        nuevas: list[LineaDocumento] = []
        for raw in lineas:
            lid = raw.get("id") or next_id("ln", [x.id for x in nuevas] + [x.id for x in doc.lineas])
            clk = raw.get("client_line_key") or str(uuid.uuid4())
            nuevas.append(
                LineaDocumento(
                    id=lid,
                    producto_id=raw["producto_id"],
                    cantidad=float(raw.get("cantidad") or 0),
                    precio_total=float(raw.get("precio_total") or 0),
                    client_line_key=clk,
                    cantidad_compra=as_decimal(raw["cantidad_compra"])
                    if raw.get("cantidad_compra") is not None
                    else None,
                    unidad_compra=raw.get("unidad_compra"),
                    precio_unitario_compra=as_decimal(raw["precio_unitario_compra"])
                    if raw.get("precio_unitario_compra") is not None
                    else None,
                    precio_incluye_igic=bool(raw.get("precio_incluye_igic", False)),
                    factor_conversion=as_decimal(raw["factor_conversion"])
                    if raw.get("factor_conversion") is not None
                    else None,
                    unidad_inventario=raw.get("unidad_inventario"),
                    descuento_porcentaje=as_decimal(raw.get("descuento_porcentaje") or 0),
                    descuento_importe=as_decimal(raw.get("descuento_importe") or 0),
                    impuesto_id=raw.get("impuesto_id"),
                    impuesto_porcentaje_snapshot=as_decimal(raw["impuesto_porcentaje"])
                    if raw.get("impuesto_porcentaje") is not None
                    else None,
                    codigo_lote_proveedor=raw.get("codigo_lote_proveedor"),
                    fecha_expiracion=raw.get("fecha_expiracion"),
                    ubicacion_destino_id=raw.get("ubicacion_destino_id"),
                )
            )
        doc.lineas = nuevas
        doc.descuento_cabecera_importe = as_decimal(descuento_cabecera_importe)
        try:
            _preparar_lineas_compra(data, doc)
        except ValueError as exc:
            return ResultadoCompra(False, str(exc), documento=doc)

    aviso_ref = None
    if referencia_duplicada(
        data,
        proveedor_id=doc.proveedor_id,
        referencia_externa=doc.referencia_externa,
        exclude_doc_id=doc.id,
    ):
        aviso_ref = ["Aviso: referencia_externa duplicada (bloqueo al confirmar)."]

    return ResultadoCompra(
        True,
        f"Borrador {doc.id} guardado.",
        documento=doc,
        alerta_precio=aviso_ref,
    )


def confirmar_compra(
    documento_id: str,
    *,
    confirmacion_id: str,
    contenido_hash: str,
    json_path: Path | str,
    conciliaciones_propuestas: list[dict] | None = None,
    adjuntos: list[AdjuntoEntrada] | None = None,
    storage_root: Path | str | None = None,
) -> ResultadoCompra:
    """Confirmación crítica (§5): lock → relectura → (publish binarios) → JSON A2.

    JSON + binario **no** son una transacción atómica conjunta. Si el JSON falla
    tras publicar binarios, se compensan (borran) los publicados en esta
    operación. Si el JSON ya quedó confirmado, no se borran adjuntos (estado
    ``incierto`` solo si la compensación falla).
    """
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)
    if denied:
        return ResultadoCompra(False, denied, codigo="no_autorizado")

    import copy

    from app.core.models import ArchivoDocumental
    from app.core.storage.archivo_storage import LocalArchivoStorage, PublishBatch
    from app.core.storage.json_atomic import JsonWriteLock, atomic_write_json
    from app.data.serializers import appdata_to_dict

    token = (confirmacion_id or "").strip().lower()
    try:
        uuid.UUID(token)
    except ValueError:
        return ResultadoCompra(False, "confirmacion_id debe ser UUID.")

    path = Path(json_path).resolve()
    store: LocalArchivoStorage | None = None
    if adjuntos:
        root = Path(storage_root) if storage_root else (path.parent.parent / "documentos_storage")
        store = LocalArchivoStorage(root)

    batch = PublishBatch()
    handles = []
    adjuntos_estado = "ok"

    try:
        with JsonWriteLock(path):
            fresh = read_appdata_json(path) if path.exists() else AppData()
            working = copy.deepcopy(fresh)

            # Idempotencia temprana (sin publicar binarios de nuevo)
            early = _aplicar_confirmacion(
                copy.deepcopy(fresh),
                documento_id,
                confirmacion_id=token,
                contenido_hash=contenido_hash,
                conciliaciones_propuestas=conciliaciones_propuestas,
            )
            if early.ok and early.codigo == CONFIRMACION_IDEMPOTENTE:
                return ResultadoCompra(
                    True,
                    early.mensaje,
                    codigo=CONFIRMACION_IDEMPOTENTE,
                    documento=early.documento,
                    adjuntos_estado="ok",
                )
            if not early.ok:
                # Conflictos / validación: sin publicar binarios
                return early

            # Staging + publish (pasos 5–7) solo si hay adjuntos nuevos
            if adjuntos and store is not None:
                for adj in adjuntos:
                    handles.append(
                        store.stage(
                            adj.contenido,
                            adj.nombre_original,
                            mime_type=adj.mime_type,
                        )
                    )
                batch = store.publish_batch(handles)
                if not hasattr(working, "archivos_documentales") or working.archivos_documentales is None:
                    working.archivos_documentales = []
                doc_pre = next((d for d in working.documentos if d.id == documento_id), None)
                for h in handles:
                    arch_id = next_id(
                        "adoc", [a.id for a in working.archivos_documentales]
                    )
                    try:
                        rel = h.final_path.relative_to(path.parent.parent).as_posix()
                    except ValueError:
                        rel = str(h.final_path)
                    meta = ArchivoDocumental(
                        id=arch_id,
                        nombre_original=h.nombre_original_seguro,
                        mime_type=h.mime_type,
                        tamanio_bytes=h.tamanio_bytes,
                        sha256=h.sha256,
                        ruta_relativa=rel,
                        storage_key=h.storage_key,
                        documento_id=documento_id,
                        creado_en=datetime.now(),
                        activo=True,
                    )
                    working.archivos_documentales.append(meta)
                    if doc_pre is not None:
                        doc_pre.archivo_ids = list(doc_pre.archivo_ids or []) + [arch_id]

            result = _aplicar_confirmacion(
                working,
                documento_id,
                confirmacion_id=token,
                contenido_hash=contenido_hash,
                conciliaciones_propuestas=conciliaciones_propuestas,
            )
            if not result.ok:
                if store is not None and batch.published_keys:
                    store.rollback_published(batch)
                    adjuntos_estado = "compensado"
                result.adjuntos_estado = adjuntos_estado
                return result

            # Persistencia JSON (pasos 10–12) sin re-adquirir lock
            atomic_write_json(
                path,
                appdata_to_dict(working),
                acquire_lock=False,
            )
            result.adjuntos_publicados = list(batch.published_keys) or None
            result.adjuntos_estado = "ok"
            return result
    except Exception as exc:  # noqa: BLE001
        # Fallo tras publish / antes o durante JSON → compensar binarios
        if store is not None and batch.published_keys:
            try:
                store.rollback_published(batch)
                adjuntos_estado = "compensado"
            except Exception:  # noqa: BLE001
                adjuntos_estado = "incierto"
        return ResultadoCompra(
            False,
            f"Persistencia fallida: {exc}",
            adjuntos_estado=adjuntos_estado,
            adjuntos_publicados=list(batch.published_keys) or None,
        )


def guardar_borrador_persistente(
    *,
    json_path: Path | str,
    **kwargs,
) -> ResultadoCompra:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)
    if denied:
        return ResultadoCompra(False, denied, codigo="no_autorizado")

    holder: dict = {"result": None}

    def _mutate(data: AppData) -> AppData:
        holder["result"] = guardar_borrador(data, **kwargs)
        if not holder["result"].ok:
            raise RuntimeError(holder["result"].mensaje)
        return data

    try:
        transactional_update_appdata(json_path, _mutate)
    except RuntimeError as exc:
        return holder["result"] or ResultadoCompra(False, str(exc))
    return holder["result"] or ResultadoCompra(False, "Sin resultado.")
