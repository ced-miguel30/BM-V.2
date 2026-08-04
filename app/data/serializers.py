"""Serialización JSON para datos en disco."""

from __future__ import annotations

import json
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any

from app.core.models import (
    Actividad,
    AlertaOperativa,
    AppData,
    ArchivoDocumental,
    Categoria,
    CategoriaReceta,
    ConfiguracionHotel,
    Departamento,
    DireccionMovimiento,
    Documento,
    EstadoDocumento,
    EstadoRecuento,
    ExtraRecetaDesayuno,
    ExtraRecetaServicio,
    Impuesto,
    IngredienteReceta,
    LineaAjuste,
    LineaDesayuno,
    LineaDetalleOrigen,
    LineaDocumento,
    LineaMerma,
    LineaRecuento,
    LineaServicio,
    LoteStock,
    MotivoAjuste,
    MotivoMerma,
    MovimientoInventario,
    OmisionRecetaDesayuno,
    OmisionRecetaServicio,
    Producto,
    Proveedor,
    Receta,
    RegistroAjuste,
    RegistroDesayuno,
    RegistroMerma,
    RegistroRecetaDesayuno,
    RegistroRecetaServicio,
    RegistroServicio,
    RelacionProductoProveedor,
    ResponsableMerma,
    RolUsuario,
    SesionRecuento,
    Subcategoria,
    TipoAlerta,
    TipoArticulo,
    TipoDocumento,
    TipoMovimiento,
    Ubicacion,
    UnidadProducto,
    Usuario,
)
from app.core.models.registro_servicio import ConsumoLoteDetalle


def _parse_tipo_articulo(raw: Any) -> TipoArticulo | str | None:
    """Ausente → None. Valor conocido → enum. Desconocido → str (conservar)."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, TipoArticulo):
        return raw
    if not isinstance(raw, str):
        return str(raw)
    try:
        return TipoArticulo(raw)
    except ValueError:
        return raw


def _configuracion_to_dict(cfg: ConfiguracionHotel) -> dict:
    return {
        "nombre_establecimiento": cfg.nombre_establecimiento,
        "moneda": cfg.moneda,
        "simbolo_moneda": cfg.simbolo_moneda,
        "logo_path": cfg.logo_path,
        "ledger_schema_version": int(
            getattr(cfg, "ledger_schema_version", 7) or 7
        ),
        "ledger_activation_iso": getattr(cfg, "ledger_activation_iso", None),
        "ledger_balance_mode": str(
            getattr(cfg, "ledger_balance_mode", "shadow") or "shadow"
        ),
        "ledger_qty_tolerance": float(
            getattr(cfg, "ledger_qty_tolerance", 1e-4) or 1e-4
        ),
    }


def _configuracion_from_dict(raw: dict | None) -> ConfiguracionHotel | None:
    """JSON antiguo (solo 4 campos) y campos 7B aditivos."""
    if not raw:
        return None
    mode = str(raw.get("ledger_balance_mode") or "shadow").strip().lower()
    if mode not in ("legacy", "shadow", "ledger"):
        mode = "shadow"
    try:
        schema = int(raw.get("ledger_schema_version", 7))
    except (TypeError, ValueError):
        schema = 7
    try:
        tol = float(raw.get("ledger_qty_tolerance", 1e-4))
    except (TypeError, ValueError):
        tol = 1e-4
    return ConfiguracionHotel(
        nombre_establecimiento=raw.get("nombre_establecimiento", "Hotel Boutique"),
        moneda=raw.get("moneda", "EUR"),
        simbolo_moneda=raw.get("simbolo_moneda", "€"),
        logo_path=raw.get("logo_path"),
        ledger_schema_version=schema,
        ledger_activation_iso=raw.get("ledger_activation_iso"),
        ledger_balance_mode=mode,
        ledger_qty_tolerance=tol,
    )


def _parse_tipo_movimiento(raw: Any) -> TipoMovimiento | str:
    """Conocido → enum. Desconocido → str (no convertir silenciosamente)."""
    if isinstance(raw, TipoMovimiento):
        return raw
    s = "" if raw is None else str(raw)
    try:
        return TipoMovimiento(s)
    except ValueError:
        return s


def _parse_direccion_movimiento(raw: Any) -> DireccionMovimiento | str:
    """Conocido → enum. Desconocido → str (no convertir silenciosamente)."""
    if isinstance(raw, DireccionMovimiento):
        return raw
    s = "" if raw is None else str(raw)
    try:
        return DireccionMovimiento(s)
    except ValueError:
        return s


def _movimiento_to_dict(m: MovimientoInventario) -> dict:
    return {
        "id": m.id,
        "producto_id": m.producto_id,
        "lote_id": m.lote_id,
        "tipo": m.tipo.value if hasattr(m.tipo, "value") else m.tipo,
        "direccion": (
            m.direccion.value if hasattr(m.direccion, "value") else m.direccion
        ),
        "cantidad": m.cantidad,
        "fecha": m.fecha.isoformat() if m.fecha else None,
        "hora": m.hora.isoformat() if m.hora else None,
        "origen_tipo": m.origen_tipo,
        "origen_id": m.origen_id,
        "origen_linea_id": m.origen_linea_id,
        "movimiento_revertido_id": m.movimiento_revertido_id,
        "usuario_id": m.usuario_id,
        "idempotency_key": m.idempotency_key,
        "coste_unitario_snapshot": m.coste_unitario_snapshot,
        "coste_total_snapshot": m.coste_total_snapshot,
        "creado_en": m.creado_en.isoformat() if m.creado_en else None,
        "ubicacion_origen_id": getattr(m, "ubicacion_origen_id", None),
        "ubicacion_destino_id": getattr(m, "ubicacion_destino_id", None),
    }


def _movimiento_from_dict(raw: dict) -> MovimientoInventario:
    fecha_raw = raw.get("fecha")
    fecha = _parse_date(fecha_raw) if fecha_raw else date.today()
    if fecha is None:
        fecha = date.today()
    creado_raw = raw.get("creado_en")
    return MovimientoInventario(
        id=raw.get("id", ""),
        producto_id=raw.get("producto_id", ""),
        lote_id=raw.get("lote_id", ""),
        tipo=_parse_tipo_movimiento(raw.get("tipo")),
        direccion=_parse_direccion_movimiento(raw.get("direccion")),
        cantidad=float(raw.get("cantidad", 0.0)),
        fecha=fecha,
        hora=_parse_time(raw.get("hora")),
        origen_tipo=raw.get("origen_tipo", "") or "",
        origen_id=raw.get("origen_id", "") or "",
        origen_linea_id=raw.get("origen_linea_id"),
        movimiento_revertido_id=raw.get("movimiento_revertido_id"),
        usuario_id=raw.get("usuario_id"),
        idempotency_key=raw.get("idempotency_key"),
        coste_unitario_snapshot=(
            float(raw["coste_unitario_snapshot"])
            if raw.get("coste_unitario_snapshot") is not None
            else None
        ),
        coste_total_snapshot=(
            float(raw["coste_total_snapshot"])
            if raw.get("coste_total_snapshot") is not None
            else None
        ),
        creado_en=_parse_datetime(creado_raw) if creado_raw else None,
        ubicacion_origen_id=raw.get("ubicacion_origen_id"),
        ubicacion_destino_id=raw.get("ubicacion_destino_id"),
    )


def _recuento_to_dict(r: SesionRecuento) -> dict:
    return {
        "id": r.id,
        "ubicacion_id": r.ubicacion_id,
        "fecha": r.fecha.isoformat() if r.fecha else None,
        "usuario_id": r.usuario_id,
        "estado": r.estado.value if hasattr(r.estado, "value") else r.estado,
        "motivo": r.motivo,
        "hora": r.hora.isoformat() if r.hora else None,
        "creado_en": r.creado_en.isoformat() if r.creado_en else None,
        "confirmado_en": (
            r.confirmado_en.isoformat() if r.confirmado_en else None
        ),
        "anulado_en": r.anulado_en.isoformat() if r.anulado_en else None,
        "snapshot_esperado": dict(r.snapshot_esperado or {}),
        "lineas": [
            {
                "producto_id": ln.producto_id,
                "lote_id": ln.lote_id,
                "cantidad_esperada": ln.cantidad_esperada,
                "cantidad_contada": ln.cantidad_contada,
                "producto_nombre_snapshot": ln.producto_nombre_snapshot,
                "unidad_snapshot": ln.unidad_snapshot,
                "ajuste_id": ln.ajuste_id,
            }
            for ln in r.lineas
        ],
    }


def _parse_estado_recuento(raw: Any) -> EstadoRecuento | str:
    if isinstance(raw, EstadoRecuento):
        return raw
    s = "" if raw is None else str(raw)
    try:
        return EstadoRecuento(s)
    except ValueError:
        return s or EstadoRecuento.BORRADOR.value


def _recuento_from_dict(raw: dict) -> SesionRecuento:
    fecha_raw = raw.get("fecha")
    fecha = _parse_date(fecha_raw) if fecha_raw else date.today()
    if fecha is None:
        fecha = date.today()
    return SesionRecuento(
        id=raw.get("id", ""),
        ubicacion_id=raw.get("ubicacion_id", ""),
        fecha=fecha,
        usuario_id=raw.get("usuario_id"),
        estado=_parse_estado_recuento(raw.get("estado")),
        motivo=raw.get("motivo"),
        lineas=[
            LineaRecuento(
                producto_id=ln.get("producto_id", ""),
                lote_id=ln.get("lote_id", ""),
                cantidad_esperada=float(ln.get("cantidad_esperada", 0)),
                cantidad_contada=float(ln.get("cantidad_contada", 0)),
                producto_nombre_snapshot=ln.get("producto_nombre_snapshot"),
                unidad_snapshot=ln.get("unidad_snapshot"),
                ajuste_id=ln.get("ajuste_id"),
            )
            for ln in raw.get("lineas", []) or []
        ],
        hora=_parse_time(raw.get("hora")),
        creado_en=(
            _parse_datetime(raw["creado_en"]) if raw.get("creado_en") else None
        ),
        confirmado_en=(
            _parse_datetime(raw["confirmado_en"])
            if raw.get("confirmado_en")
            else None
        ),
        anulado_en=(
            _parse_datetime(raw["anulado_en"]) if raw.get("anulado_en") else None
        ),
        snapshot_esperado={
            str(k): float(v)
            for k, v in (raw.get("snapshot_esperado") or {}).items()
        },
    )


def _proveedor_to_dict(p: Proveedor) -> dict:
    return {
        "id": p.id,
        "nombre_fiscal": p.nombre_fiscal,
        "nombre_comercial": p.nombre_comercial,
        "nif_cif": p.nif_cif,
        "direccion": p.direccion,
        "contacto": p.contacto,
        "telefono": p.telefono,
        "email": p.email,
        "condiciones_pago": p.condiciones_pago,
        "activo": bool(p.activo),
    }


def _proveedor_from_dict(raw: dict) -> Proveedor:
    return Proveedor(
        id=raw.get("id", ""),
        nombre_fiscal=raw.get("nombre_fiscal", "") or "",
        nombre_comercial=raw.get("nombre_comercial"),
        nif_cif=raw.get("nif_cif"),
        direccion=raw.get("direccion"),
        contacto=raw.get("contacto"),
        telefono=raw.get("telefono"),
        email=raw.get("email"),
        condiciones_pago=raw.get("condiciones_pago"),
        activo=bool(raw.get("activo", True)),
    )


def _impuesto_to_dict(i: Impuesto) -> dict:
    from decimal import Decimal

    pct = i.porcentaje
    if isinstance(pct, Decimal):
        pct_s = format(pct, "f")
    else:
        pct_s = str(pct)
    return {
        "id": i.id,
        "nombre": i.nombre,
        "porcentaje": pct_s,
        "vigencia_desde": (
            i.vigencia_desde.isoformat() if i.vigencia_desde else None
        ),
        "vigencia_hasta": (
            i.vigencia_hasta.isoformat() if i.vigencia_hasta else None
        ),
        "activo": bool(i.activo),
        "descripcion": i.descripcion,
    }


def _impuesto_from_dict(raw: dict) -> Impuesto:
    from decimal import Decimal, InvalidOperation

    try:
        pct = Decimal(str(raw.get("porcentaje", "0")))
    except (InvalidOperation, ValueError, TypeError):
        pct = Decimal("0")
    vd = raw.get("vigencia_desde")
    vh = raw.get("vigencia_hasta")
    return Impuesto(
        id=raw.get("id", ""),
        nombre=raw.get("nombre", "") or "",
        porcentaje=pct,
        vigencia_desde=_parse_date(vd) if vd else None,
        vigencia_hasta=_parse_date(vh) if vh else None,
        activo=bool(raw.get("activo", True)),
        descripcion=raw.get("descripcion"),
    )


def _relacion_pp_to_dict(r: RelacionProductoProveedor) -> dict:
    return {
        "id": r.id,
        "producto_id": r.producto_id,
        "proveedor_id": r.proveedor_id,
        "codigo_proveedor": r.codigo_proveedor,
        "preferente": bool(r.preferente),
        "proveedor_nombre_snapshot": r.proveedor_nombre_snapshot,
        "nif_cif_snapshot": r.nif_cif_snapshot,
        "activo": bool(r.activo),
    }


def _relacion_pp_from_dict(raw: dict) -> RelacionProductoProveedor:
    return RelacionProductoProveedor(
        id=raw.get("id", ""),
        producto_id=raw.get("producto_id", "") or "",
        proveedor_id=raw.get("proveedor_id", "") or "",
        codigo_proveedor=raw.get("codigo_proveedor"),
        preferente=bool(raw.get("preferente", False)),
        proveedor_nombre_snapshot=raw.get("proveedor_nombre_snapshot"),
        nif_cif_snapshot=raw.get("nif_cif_snapshot"),
        activo=bool(raw.get("activo", True)),
    )


def _archivo_documental_to_dict(a: ArchivoDocumental) -> dict:
    return {
        "id": a.id,
        "nombre_original": a.nombre_original,
        "mime_type": a.mime_type,
        "tamanio_bytes": int(a.tamanio_bytes),
        "sha256": a.sha256,
        "ruta_relativa": a.ruta_relativa,
        "usuario_id": a.usuario_id,
        "creado_en": a.creado_en.isoformat() if a.creado_en else None,
        "documento_id": a.documento_id,
        "notas": a.notas,
        "activo": bool(a.activo),
    }


def _archivo_documental_from_dict(raw: dict) -> ArchivoDocumental:
    creado = raw.get("creado_en")
    return ArchivoDocumental(
        id=raw.get("id", ""),
        nombre_original=raw.get("nombre_original", "") or "",
        mime_type=raw.get("mime_type", "") or "application/octet-stream",
        tamanio_bytes=int(raw.get("tamanio_bytes", 0) or 0),
        sha256=raw.get("sha256", "") or "",
        ruta_relativa=raw.get("ruta_relativa", "") or "",
        usuario_id=raw.get("usuario_id"),
        creado_en=_parse_datetime(creado) if creado else None,
        documento_id=raw.get("documento_id"),
        notas=raw.get("notas"),
        activo=bool(raw.get("activo", True)),
    )


def _parse_tipo_documento(raw) -> TipoDocumento | str:
    if isinstance(raw, TipoDocumento):
        return raw
    s = "" if raw is None else str(raw)
    try:
        return TipoDocumento(s)
    except ValueError:
        return s


def _parse_estado_documento(raw) -> EstadoDocumento | str:
    if isinstance(raw, EstadoDocumento):
        return raw
    s = "" if raw is None else str(raw)
    try:
        return EstadoDocumento(s)
    except ValueError:
        return s or EstadoDocumento.BORRADOR.value


def _documento_to_dict(d: Documento) -> dict:
    return {
        "id": d.id,
        "tipo": d.tipo.value if hasattr(d.tipo, "value") else d.tipo,
        "estado": d.estado.value if hasattr(d.estado, "value") else d.estado,
        "fecha_documento": (
            d.fecha_documento.isoformat() if d.fecha_documento else None
        ),
        "proveedor_id": d.proveedor_id,
        "proveedor_nombre_snapshot": d.proveedor_nombre_snapshot,
        "nif_cif_snapshot": d.nif_cif_snapshot,
        "referencia_externa": d.referencia_externa,
        "archivo_ids": list(d.archivo_ids or []),
        "registrado_por": d.registrado_por,
        "hora": d.hora.isoformat() if d.hora else None,
        "creado_en": d.creado_en.isoformat() if d.creado_en else None,
        "confirmado_en": (
            d.confirmado_en.isoformat() if d.confirmado_en else None
        ),
        "anulado_en": d.anulado_en.isoformat() if d.anulado_en else None,
        "motivo_anulacion": d.motivo_anulacion,
        "notas": d.notas,
        "documento_rectificado_id": d.documento_rectificado_id,
        "motivo_rectificacion": d.motivo_rectificacion,
        "rectificado_en": (
            d.rectificado_en.isoformat() if d.rectificado_en else None
        ),
        "lineas": [
            {
                "id": ln.id,
                "producto_id": ln.producto_id,
                "cantidad": ln.cantidad,
                "precio_total": ln.precio_total,
                "impuesto_id": ln.impuesto_id,
                "impuesto_porcentaje_snapshot": (
                    format(ln.impuesto_porcentaje_snapshot, "f")
                    if ln.impuesto_porcentaje_snapshot is not None
                    else None
                ),
                "ubicacion_destino_id": ln.ubicacion_destino_id,
                "lote_id": ln.lote_id,
                "producto_nombre_snapshot": ln.producto_nombre_snapshot,
                "unidad_snapshot": ln.unidad_snapshot,
                "fecha_expiracion": (
                    ln.fecha_expiracion.isoformat() if ln.fecha_expiracion else None
                ),
                "movimiento_id": ln.movimiento_id,
                "documento_origen_id": ln.documento_origen_id,
                "linea_origen_id": ln.linea_origen_id,
            }
            for ln in d.lineas
        ],
    }


def _documento_from_dict(raw: dict) -> Documento:
    from decimal import Decimal, InvalidOperation

    fecha_raw = raw.get("fecha_documento")
    fecha = _parse_date(fecha_raw) if fecha_raw else date.today()
    if fecha is None:
        fecha = date.today()
    lineas: list[LineaDocumento] = []
    for ln in raw.get("lineas", []) or []:
        pct = ln.get("impuesto_porcentaje_snapshot")
        pct_d = None
        if pct is not None and pct != "":
            try:
                pct_d = Decimal(str(pct))
            except (InvalidOperation, ValueError):
                pct_d = None
        fe = ln.get("fecha_expiracion")
        lineas.append(
            LineaDocumento(
                id=ln.get("id", ""),
                producto_id=ln.get("producto_id", "") or "",
                cantidad=float(ln.get("cantidad", 0) or 0),
                precio_total=float(ln.get("precio_total", 0) or 0),
                impuesto_id=ln.get("impuesto_id"),
                impuesto_porcentaje_snapshot=pct_d,
                ubicacion_destino_id=ln.get("ubicacion_destino_id"),
                lote_id=ln.get("lote_id"),
                producto_nombre_snapshot=ln.get("producto_nombre_snapshot"),
                unidad_snapshot=ln.get("unidad_snapshot"),
                fecha_expiracion=_parse_date(fe) if fe else None,
                movimiento_id=ln.get("movimiento_id"),
                documento_origen_id=ln.get("documento_origen_id"),
                linea_origen_id=ln.get("linea_origen_id"),
            )
        )
    return Documento(
        id=raw.get("id", ""),
        tipo=_parse_tipo_documento(raw.get("tipo")),
        estado=_parse_estado_documento(raw.get("estado")),
        fecha_documento=fecha,
        proveedor_id=raw.get("proveedor_id"),
        proveedor_nombre_snapshot=raw.get("proveedor_nombre_snapshot"),
        nif_cif_snapshot=raw.get("nif_cif_snapshot"),
        referencia_externa=raw.get("referencia_externa"),
        lineas=lineas,
        archivo_ids=list(raw.get("archivo_ids", []) or []),
        registrado_por=raw.get("registrado_por", "") or "",
        hora=_parse_time(raw.get("hora")),
        creado_en=(
            _parse_datetime(raw["creado_en"]) if raw.get("creado_en") else None
        ),
        confirmado_en=(
            _parse_datetime(raw["confirmado_en"])
            if raw.get("confirmado_en")
            else None
        ),
        anulado_en=(
            _parse_datetime(raw["anulado_en"]) if raw.get("anulado_en") else None
        ),
        motivo_anulacion=raw.get("motivo_anulacion"),
        notas=raw.get("notas"),
        documento_rectificado_id=raw.get("documento_rectificado_id"),
        motivo_rectificacion=raw.get("motivo_rectificacion"),
        rectificado_en=(
            _parse_datetime(raw["rectificado_en"])
            if raw.get("rectificado_en")
            else None
        ),
    )


class _Encoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        try:
            from decimal import Decimal

            if isinstance(obj, Decimal):
                return format(obj, "f")
        except Exception:  # noqa: BLE001
            pass
        return super().default(obj)


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _parse_time(value: str | None) -> time | None:
    return time.fromisoformat(value) if value else None


def _consumo_lote_to_dict(c: ConsumoLoteDetalle) -> dict:
    return {
        "lote_id": c.lote_id,
        "producto_id": c.producto_id,
        "cantidad": c.cantidad,
        "coste": c.coste,
    }


def _consumo_lote_from_dict(raw: dict) -> ConsumoLoteDetalle:
    return ConsumoLoteDetalle(
        lote_id=raw.get("lote_id", ""),
        producto_id=raw.get("producto_id", ""),
        cantidad=float(raw.get("cantidad", 0.0)),
        coste=float(raw.get("coste", 0.0)),
    )


def _detalle_to_dict(det: LineaDetalleOrigen) -> dict:
    return {
        "origen": det.origen,
        "producto_id": det.producto_id,
        "cantidad": det.cantidad,
        "coste": det.coste,
        "receta_origen_id": det.receta_origen_id,
        "registro_origen_id": det.registro_origen_id,
        "tipo_servicio": det.tipo_servicio,
        "categoria_receta": det.categoria_receta,
        "es_bebida_snapshot": det.es_bebida_snapshot,
        "categoria_receta_snapshot": det.categoria_receta_snapshot,
        "consumos_lote": [_consumo_lote_to_dict(c) for c in det.consumos_lote],
    }


def _detalle_from_dict(raw: dict) -> LineaDetalleOrigen:
    return LineaDetalleOrigen(
        origen=raw["origen"],
        producto_id=raw["producto_id"],
        cantidad=raw["cantidad"],
        coste=raw.get("coste", 0.0),
        receta_origen_id=raw.get("receta_origen_id"),
        registro_origen_id=raw.get("registro_origen_id"),
        tipo_servicio=raw.get("tipo_servicio", ""),
        categoria_receta=raw.get("categoria_receta"),
        es_bebida_snapshot=raw.get("es_bebida_snapshot"),
        categoria_receta_snapshot=raw.get("categoria_receta_snapshot"),
        consumos_lote=[
            _consumo_lote_from_dict(c) for c in raw.get("consumos_lote", [])
        ],
    )


def appdata_to_dict(data: AppData) -> dict:
    return {
        "meta": {"usuario_actual_id": data.usuario_actual_id, "origen": "demo"},
        "productos": [
            {
                "id": p.id,
                "nombre": p.nombre,
                "unidad": p.unidad.value,
                "stock_minimo": p.stock_minimo,
                "es_bebida": p.es_bebida,
                "servicios_disponibles": list(p.servicios_disponibles),
                "categoria_inventario": p.categoria_inventario,
                "categoria_id": p.categoria_id,
                "subcategoria_id": p.subcategoria_id,
                "departamento_ids": list(p.departamento_ids),
                "ubicacion_ids": list(getattr(p, "ubicacion_ids", []) or []),
                "tipo_articulo": (
                    p.tipo_articulo.value
                    if hasattr(p.tipo_articulo, "value")
                    else p.tipo_articulo
                ),
            }
            for p in data.productos
        ],
        "lotes": [
            {
                "id": l.id, "producto_id": l.producto_id, "precio_total": l.precio_total,
                "cantidad": l.cantidad, "cantidad_restante": l.cantidad_restante,
                "fecha_compra": l.fecha_compra.isoformat() if l.fecha_compra else None,
                "fecha_expiracion": l.fecha_expiracion.isoformat() if l.fecha_expiracion else None,
                "marca_proveedor": l.marca_proveedor,
                "alerta_expiracion_dias": l.alerta_expiracion_dias,
                "anulado": bool(getattr(l, "anulado", False)),
                "fecha_anulacion": (
                    l.fecha_anulacion.isoformat()
                    if getattr(l, "fecha_anulacion", None) else None
                ),
                "hora_anulacion": (
                    l.hora_anulacion.isoformat()
                    if getattr(l, "hora_anulacion", None) else None
                ),
                "motivo_anulacion": getattr(l, "motivo_anulacion", "") or "",
                "referencia_anulacion": getattr(l, "referencia_anulacion", "") or "",
                "anulado_por": getattr(l, "anulado_por", "") or "",
            }
            for l in data.lotes
        ],
        "desayunos": [
            {
                "id": d.id, "fecha": d.fecha.isoformat(),
                "hora": d.hora.isoformat() if d.hora else None,
                "lineas": [
                    {
                        "producto_id": ln.producto_id,
                        "cantidad": ln.cantidad,
                        "coste": ln.coste,
                        "es_extra": ln.es_extra,
                    }
                    for ln in d.lineas
                ],
                "coste_total": d.coste_total, "registrado_por": d.registrado_por,
                "num_huespedes": d.num_huespedes,
                "registros_recetas": [
                    {
                        "receta_id": rr.receta_id,
                        "nombre_receta": rr.nombre_receta,
                        "porciones": rr.porciones,
                        "categoria_receta_snapshot": rr.categoria_receta_snapshot,
                        "porciones_estandar_snapshot": rr.porciones_estandar_snapshot,
                        "factor_aplicado": rr.factor_aplicado,
                        "extras": [
                            {"producto_id": e.producto_id, "cantidad": e.cantidad}
                            for e in rr.extras
                        ],
                        "omisiones": [
                            {"producto_id": o.producto_id}
                            for o in rr.omisiones
                        ],
                    }
                    for rr in d.registros_recetas
                ],
                "lineas_detalle": [_detalle_to_dict(det) for det in d.lineas_detalle],
                "anulado": bool(getattr(d, "anulado", False)),
                "fecha_anulacion": (
                    d.fecha_anulacion.isoformat()
                    if getattr(d, "fecha_anulacion", None) else None
                ),
                "hora_anulacion": (
                    d.hora_anulacion.isoformat()
                    if getattr(d, "hora_anulacion", None) else None
                ),
                "motivo_anulacion": getattr(d, "motivo_anulacion", "") or "",
                "referencia_anulacion": getattr(d, "referencia_anulacion", "") or "",
                "anulado_por": getattr(d, "anulado_por", "") or "",
            }
            for d in data.desayunos
        ],
        "registros_servicio": [
            {
                "id": r.id,
                "tipo_servicio": r.tipo_servicio,
                "fecha": r.fecha.isoformat(),
                "hora": r.hora.isoformat() if r.hora else None,
                "lineas": [
                    {
                        "producto_id": ln.producto_id,
                        "cantidad": ln.cantidad,
                        "coste": ln.coste,
                        "es_extra": ln.es_extra,
                    }
                    for ln in r.lineas
                ],
                "coste_total": r.coste_total,
                "registrado_por": r.registrado_por,
                "num_huespedes": r.num_huespedes,
                "registros_recetas": [
                    {
                        "receta_id": rr.receta_id,
                        "nombre_receta": rr.nombre_receta,
                        "porciones": rr.porciones,
                        "categoria_receta": rr.categoria_receta,
                        "categoria_receta_snapshot": rr.categoria_receta_snapshot,
                        "porciones_estandar_snapshot": rr.porciones_estandar_snapshot,
                        "factor_aplicado": rr.factor_aplicado,
                        "extras": [
                            {"producto_id": e.producto_id, "cantidad": e.cantidad}
                            for e in rr.extras
                        ],
                        "omisiones": [
                            {"producto_id": o.producto_id}
                            for o in rr.omisiones
                        ],
                    }
                    for rr in r.registros_recetas
                ],
                "lineas_detalle": [_detalle_to_dict(det) for det in r.lineas_detalle],
                "anulado": bool(getattr(r, "anulado", False)),
                "fecha_anulacion": (
                    r.fecha_anulacion.isoformat()
                    if getattr(r, "fecha_anulacion", None) else None
                ),
                "hora_anulacion": (
                    r.hora_anulacion.isoformat()
                    if getattr(r, "hora_anulacion", None) else None
                ),
                "motivo_anulacion": getattr(r, "motivo_anulacion", "") or "",
                "referencia_anulacion": getattr(r, "referencia_anulacion", "") or "",
                "anulado_por": getattr(r, "anulado_por", "") or "",
            }
            for r in data.registros_servicio
        ],
        "recetas": [
            {
                "id": r.id,
                "nombre": r.nombre,
                "categoria": r.categoria.value,
                "servicios_disponibles": list(r.servicios_disponibles),
                "porciones_estandar": r.porciones_estandar,
                "ingredientes": [
                    {
                        "producto_id": i.producto_id,
                        "cantidad": i.cantidad,
                        "cantidad_presentacion": i.cantidad_presentacion,
                        "unidad_presentacion": i.unidad_presentacion,
                    }
                    for i in r.ingredientes
                ],
            }
            for r in data.recetas
        ],
        "mermas": [
            {
                "id": m.id, "fecha": m.fecha.isoformat(),
                "hora": m.hora.isoformat() if m.hora else None,
                "lineas": [
                    {
                        "producto_id": ln.producto_id,
                        "cantidad": ln.cantidad,
                        "coste": ln.coste,
                        "motivo": ln.motivo.value,
                        "comentario": ln.comentario,
                        "lote_id": ln.lote_id,
                        # Aditivos: ausentes en JSON antiguo → None al cargar.
                        "tipo_servicio_snapshot": ln.tipo_servicio_snapshot,
                        "turno_snapshot": ln.turno_snapshot,
                        "responsable_id": ln.responsable_id,
                        "responsable_nombre": ln.responsable_nombre,
                        "producto_nombre_snapshot": ln.producto_nombre_snapshot,
                        "unidad_snapshot": ln.unidad_snapshot,
                    }
                    for ln in m.lineas
                ],
                "coste_total": m.coste_total, "registrado_por": m.registrado_por,
                "anulado": bool(getattr(m, "anulado", False)),
                "fecha_anulacion": (
                    m.fecha_anulacion.isoformat()
                    if getattr(m, "fecha_anulacion", None) else None
                ),
                "hora_anulacion": (
                    m.hora_anulacion.isoformat()
                    if getattr(m, "hora_anulacion", None) else None
                ),
                "motivo_anulacion": getattr(m, "motivo_anulacion", "") or "",
                "referencia_anulacion": getattr(m, "referencia_anulacion", "") or "",
                "anulado_por": getattr(m, "anulado_por", "") or "",
            }
            for m in data.mermas
        ],
        "ajustes": [
            {
                "id": a.id,
                "fecha": a.fecha.isoformat(),
                "hora": a.hora.isoformat() if a.hora else None,
                "lineas": [
                    {
                        "producto_id": ln.producto_id,
                        "lote_id": ln.lote_id,
                        "cantidad_antes": ln.cantidad_antes,
                        "cantidad_despues": ln.cantidad_despues,
                        "motivo": ln.motivo.value,
                        "comentario": ln.comentario,
                        "producto_nombre_snapshot": ln.producto_nombre_snapshot,
                        "unidad_snapshot": ln.unidad_snapshot,
                    }
                    for ln in a.lineas
                ],
                "registrado_por": a.registrado_por,
            }
            for a in data.ajustes
        ],
        "responsables_merma": [
            {"id": r.id, "nombre": r.nombre, "activo": r.activo}
            for r in data.responsables_merma
        ],
        "departamentos": [
            {"id": d.id, "nombre": d.nombre, "activo": d.activo}
            for d in data.departamentos
        ],
        "categorias": [
            {"id": c.id, "nombre": c.nombre, "activo": c.activo}
            for c in data.categorias
        ],
        "subcategorias": [
            {
                "id": s.id,
                "nombre": s.nombre,
                "categoria_id": s.categoria_id,
                "activo": s.activo,
            }
            for s in data.subcategorias
        ],
        "ubicaciones": [
            {"id": u.id, "nombre": u.nombre, "activo": u.activo}
            for u in getattr(data, "ubicaciones", []) or []
        ],
        "movimientos": [
            _movimiento_to_dict(m)
            for m in getattr(data, "movimientos", []) or []
        ],
        "recuentos": [
            _recuento_to_dict(r)
            for r in getattr(data, "recuentos", []) or []
        ],
        "proveedores": [
            _proveedor_to_dict(p)
            for p in getattr(data, "proveedores", []) or []
        ],
        "impuestos": [
            _impuesto_to_dict(i)
            for i in getattr(data, "impuestos", []) or []
        ],
        "relaciones_producto_proveedor": [
            _relacion_pp_to_dict(r)
            for r in getattr(data, "relaciones_producto_proveedor", []) or []
        ],
        "archivos_documentales": [
            _archivo_documental_to_dict(a)
            for a in getattr(data, "archivos_documentales", []) or []
        ],
        "documentos": [
            _documento_to_dict(d)
            for d in getattr(data, "documentos", []) or []
        ],
        "alertas": [
            {
                "id": a.id, "tipo": a.tipo.value, "titulo": a.titulo, "mensaje": a.mensaje,
                "fecha": a.fecha.isoformat(), "activa": a.activa, "producto_id": a.producto_id,
                "estado": getattr(a, "estado", "pendiente") or "pendiente",
                "lote_id": getattr(a, "lote_id", None),
            }
            for a in data.alertas
        ],
        "alertas_descartadas": list(data.alertas_descartadas),
        "usuarios": [
            {"id": u.id, "nombre": u.nombre, "rol": u.rol.value, "activo": u.activo}
            for u in data.usuarios
        ],
        "configuracion": _configuracion_to_dict(data.configuracion)
        if data.configuracion
        else None,
        "actividades": [
            {
                "id": a.id, "fecha_hora": a.fecha_hora.isoformat(),
                "usuario": a.usuario, "accion": a.accion, "detalle": a.detalle,
                "modulo": a.modulo, "resultado": a.resultado,
                "tipo_exportacion": a.tipo_exportacion,
                "periodo_afectado": a.periodo_afectado,
                "archivo_generado": a.archivo_generado,
            }
            for a in data.actividades
        ],
    }


def dict_to_appdata(payload: dict) -> AppData:
    config = payload.get("configuracion")
    return AppData(
        productos=[
            Producto(
                p["id"],
                p["nombre"],
                UnidadProducto(p["unidad"]),
                p.get("stock_minimo"),
                p.get("es_bebida", False),
                # Ausente → lista vacía («No configurado»); no inventar servicios.
                [
                    s for s in p.get("servicios_disponibles", [])
                    if isinstance(s, str)
                ],
                p.get("categoria_inventario"),
                categoria_id=p.get("categoria_id"),
                subcategoria_id=p.get("subcategoria_id"),
                departamento_ids=[
                    d for d in p.get("departamento_ids", []) or []
                    if isinstance(d, str) and d
                ],
                ubicacion_ids=[
                    u for u in p.get("ubicacion_ids", []) or []
                    if isinstance(u, str) and u
                ],
                tipo_articulo=_parse_tipo_articulo(p.get("tipo_articulo")),
            )
            for p in payload.get("productos", [])
        ],
        lotes=[
            LoteStock(
                l["id"], l["producto_id"], l["precio_total"], l["cantidad"], l["cantidad_restante"],
                _parse_date(l.get("fecha_compra")), _parse_date(l.get("fecha_expiracion")),
                l.get("marca_proveedor"), l.get("alerta_expiracion_dias"),
                anulado=bool(l.get("anulado", False)),
                fecha_anulacion=_parse_date(l.get("fecha_anulacion")),
                hora_anulacion=_parse_time(l.get("hora_anulacion")),
                motivo_anulacion=l.get("motivo_anulacion", "") or "",
                referencia_anulacion=l.get("referencia_anulacion", "") or "",
                anulado_por=l.get("anulado_por", "") or "",
            )
            for l in payload.get("lotes", [])
        ],
        desayunos=[
            RegistroDesayuno(
                d["id"], _parse_date(d["fecha"]),  # type: ignore[arg-type]
                [
                    LineaDesayuno(
                        ln["producto_id"],
                        ln["cantidad"],
                        ln["coste"],
                        ln.get("es_extra", False),
                    )
                    for ln in d.get("lineas", [])
                ],
                d.get("coste_total", 0), d.get("registrado_por", ""),
                d.get("num_huespedes", 30),
                [
                    RegistroRecetaDesayuno(
                        rr["receta_id"],
                        rr["nombre_receta"],
                        rr["porciones"],
                        [
                            ExtraRecetaDesayuno(e["producto_id"], e["cantidad"])
                            for e in rr.get("extras", [])
                        ],
                        [
                            OmisionRecetaDesayuno(o["producto_id"])
                            for o in rr.get("omisiones", [])
                        ],
                        categoria_receta_snapshot=rr.get("categoria_receta_snapshot"),
                        porciones_estandar_snapshot=rr.get("porciones_estandar_snapshot"),
                        factor_aplicado=rr.get("factor_aplicado"),
                    )
                    for rr in d.get("registros_recetas", [])
                ],
                hora=_parse_time(d.get("hora")),
                lineas_detalle=[
                    _detalle_from_dict(det) for det in d.get("lineas_detalle", [])
                ],
                anulado=bool(d.get("anulado", False)),
                fecha_anulacion=_parse_date(d.get("fecha_anulacion")),
                hora_anulacion=_parse_time(d.get("hora_anulacion")),
                motivo_anulacion=d.get("motivo_anulacion", "") or "",
                referencia_anulacion=d.get("referencia_anulacion", "") or "",
                anulado_por=d.get("anulado_por", "") or "",
            )
            for d in payload.get("desayunos", [])
        ],
        registros_servicio=[
            RegistroServicio(
                r["id"],
                r["tipo_servicio"],
                _parse_date(r["fecha"]),  # type: ignore[arg-type]
                [
                    LineaServicio(
                        ln["producto_id"],
                        ln["cantidad"],
                        ln["coste"],
                        ln.get("es_extra", False),
                    )
                    for ln in r.get("lineas", [])
                ],
                r.get("coste_total", 0),
                r.get("registrado_por", ""),
                r.get("num_huespedes", 0),
                [
                    RegistroRecetaServicio(
                        rr["receta_id"],
                        rr["nombre_receta"],
                        rr["porciones"],
                        [
                            ExtraRecetaServicio(e["producto_id"], e["cantidad"])
                            for e in rr.get("extras", [])
                        ],
                        [
                            OmisionRecetaServicio(o["producto_id"])
                            for o in rr.get("omisiones", [])
                        ],
                        categoria_receta=rr.get("categoria_receta"),
                        categoria_receta_snapshot=rr.get(
                            "categoria_receta_snapshot",
                            rr.get("categoria_receta"),
                        ),
                        porciones_estandar_snapshot=rr.get("porciones_estandar_snapshot"),
                        factor_aplicado=rr.get("factor_aplicado"),
                    )
                    for rr in r.get("registros_recetas", [])
                ],
                hora=_parse_time(r.get("hora")),
                lineas_detalle=[
                    _detalle_from_dict(det) for det in r.get("lineas_detalle", [])
                ],
                anulado=bool(r.get("anulado", False)),
                fecha_anulacion=_parse_date(r.get("fecha_anulacion")),
                hora_anulacion=_parse_time(r.get("hora_anulacion")),
                motivo_anulacion=r.get("motivo_anulacion", "") or "",
                referencia_anulacion=r.get("referencia_anulacion", "") or "",
                anulado_por=r.get("anulado_por", "") or "",
            )
            for r in payload.get("registros_servicio", [])
        ],
        recetas=[
            Receta(
                r["id"],
                r["nombre"],
                [
                    IngredienteReceta(
                        i["producto_id"],
                        i["cantidad"],
                        i.get("cantidad_presentacion"),
                        i.get("unidad_presentacion"),
                    )
                    for i in r.get("ingredientes", [])
                ],
                # Recetas antiguas sin categoría → Desayuno (compatibilidad).
                CategoriaReceta(r.get("categoria", CategoriaReceta.DESAYUNO.value)),
                [
                    s for s in r.get("servicios_disponibles", [])
                    if isinstance(s, str)
                ],
                # Ausente / null = no configurado (Fase 7).
                r.get("porciones_estandar"),
            )
            for r in payload.get("recetas", [])
        ],
        mermas=[
            RegistroMerma(
                m["id"], _parse_date(m["fecha"]),  # type: ignore[arg-type]
                [
                    LineaMerma(
                        ln["producto_id"],
                        ln["cantidad"],
                        ln["coste"],
                        MotivoMerma(ln["motivo"]),
                        ln.get("comentario"),
                        ln.get("lote_id"),
                        # NULL / ausente = histórico sin desglose; no reinterpretar.
                        ln.get("tipo_servicio_snapshot"),
                        ln.get("turno_snapshot"),
                        ln.get("responsable_id"),
                        ln.get("responsable_nombre"),
                        ln.get("producto_nombre_snapshot"),
                        ln.get("unidad_snapshot"),
                    )
                    for ln in m.get("lineas", [])
                ],
                m.get("coste_total", 0), m.get("registrado_por", ""),
                hora=_parse_time(m.get("hora")),
                anulado=bool(m.get("anulado", False)),
                fecha_anulacion=_parse_date(m.get("fecha_anulacion")),
                hora_anulacion=_parse_time(m.get("hora_anulacion")),
                motivo_anulacion=m.get("motivo_anulacion", "") or "",
                referencia_anulacion=m.get("referencia_anulacion", "") or "",
                anulado_por=m.get("anulado_por", "") or "",
            )
            for m in payload.get("mermas", [])
        ],
        ajustes=[
            RegistroAjuste(
                a["id"],
                _parse_date(a["fecha"]),  # type: ignore[arg-type]
                [
                    LineaAjuste(
                        ln["producto_id"],
                        ln["lote_id"],
                        ln["cantidad_antes"],
                        ln["cantidad_despues"],
                        MotivoAjuste(ln["motivo"]),
                        ln.get("comentario"),
                        ln.get("producto_nombre_snapshot"),
                        ln.get("unidad_snapshot"),
                    )
                    for ln in a.get("lineas", [])
                ],
                a.get("registrado_por", ""),
                hora=_parse_time(a.get("hora")),
            )
            for a in payload.get("ajustes", [])
        ],
        responsables_merma=[
            ResponsableMerma(
                r["id"], r["nombre"], r.get("activo", True),
            )
            for r in payload.get("responsables_merma", [])
        ],
        departamentos=[
            Departamento(
                d["id"], d["nombre"], d.get("activo", True),
            )
            for d in payload.get("departamentos", [])
        ],
        categorias=[
            Categoria(
                c["id"], c["nombre"], c.get("activo", True),
            )
            for c in payload.get("categorias", [])
        ],
        subcategorias=[
            Subcategoria(
                s["id"],
                s["nombre"],
                s["categoria_id"],
                s.get("activo", True),
            )
            for s in payload.get("subcategorias", [])
        ],
        ubicaciones=[
            Ubicacion(
                u["id"], u["nombre"], u.get("activo", True),
            )
            for u in payload.get("ubicaciones", [])
        ],
        movimientos=[
            _movimiento_from_dict(m)
            for m in payload.get("movimientos", [])
        ],
        recuentos=[
            _recuento_from_dict(r)
            for r in payload.get("recuentos", [])
        ],
        proveedores=[
            _proveedor_from_dict(p)
            for p in payload.get("proveedores", [])
        ],
        impuestos=[
            _impuesto_from_dict(i)
            for i in payload.get("impuestos", [])
        ],
        relaciones_producto_proveedor=[
            _relacion_pp_from_dict(r)
            for r in payload.get("relaciones_producto_proveedor", [])
        ],
        archivos_documentales=[
            _archivo_documental_from_dict(a)
            for a in payload.get("archivos_documentales", [])
        ],
        documentos=[
            _documento_from_dict(d)
            for d in payload.get("documentos", [])
        ],
        alertas=[
            AlertaOperativa(
                a["id"], TipoAlerta(a["tipo"]), a["titulo"], a["mensaje"],
                _parse_date(a["fecha"]),  # type: ignore[arg-type]
                a.get("activa", True), a.get("producto_id"),
                estado=a.get("estado") or "pendiente",
                lote_id=a.get("lote_id"),
            )
            for a in payload.get("alertas", [])
        ],
        alertas_descartadas=list(payload.get("alertas_descartadas", [])),
        usuarios=[
            Usuario(u["id"], u["nombre"], RolUsuario(u["rol"]), u.get("activo", True))
            for u in payload.get("usuarios", [])
        ],
        configuracion=_configuracion_from_dict(config),
        actividades=[
            Actividad(
                a["id"], _parse_datetime(a["fecha_hora"]), a["usuario"], a["accion"], a["detalle"],
                modulo=a.get("modulo"),
                resultado=a.get("resultado"),
                tipo_exportacion=a.get("tipo_exportacion"),
                periodo_afectado=a.get("periodo_afectado"),
                archivo_generado=a.get("archivo_generado"),
            )
            for a in payload.get("actividades", [])
        ],
        usuario_actual_id=payload.get("meta", {}).get("usuario_actual_id", ""),
    )


def save_json(path: Path, data: dict) -> None:
    """Persiste un dict como JSON UTF-8 de forma atómica (Fase A2)."""
    _reject_protected_demo_write(path)
    from app.core.storage.json_atomic import atomic_write_json

    atomic_write_json(path, data)


def _reject_protected_demo_write(path: Path | str) -> None:
    """Si BM_TEST_ISOLATION está activo, bloquea escrituras al JSON demo canónico."""
    import os

    flag = os.environ.get("BM_TEST_ISOLATION", "").strip().lower()
    if flag not in ("1", "true", "yes"):
        return
    try:
        from app.core.storage.demo_files import DEMO_FILE

        if Path(path).resolve() == DEMO_FILE.resolve():
            raise RuntimeError(
                f"BM_TEST_ISOLATION: forbidden write to {DEMO_FILE.resolve()}"
            )
    except ImportError:
        return


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
