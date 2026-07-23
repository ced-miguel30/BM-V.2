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
    CategoriaReceta,
    ConfiguracionHotel,
    ExtraRecetaDesayuno,
    ExtraRecetaServicio,
    IngredienteReceta,
    LineaDesayuno,
    LineaDetalleOrigen,
    LineaMerma,
    LineaServicio,
    LoteStock,
    MotivoMerma,
    OmisionRecetaDesayuno,
    OmisionRecetaServicio,
    Producto,
    Receta,
    RegistroDesayuno,
    RegistroMerma,
    RegistroRecetaDesayuno,
    RegistroRecetaServicio,
    RegistroServicio,
    RolUsuario,
    TipoAlerta,
    UnidadProducto,
    Usuario,
)


class _Encoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _parse_time(value: str | None) -> time | None:
    return time.fromisoformat(value) if value else None


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
            }
            for r in data.registros_servicio
        ],
        "recetas": [
            {
                "id": r.id,
                "nombre": r.nombre,
                "categoria": r.categoria.value,
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
                        # Aditivo: ausente en JSON antiguo → None al cargar.
                        "tipo_servicio_snapshot": ln.tipo_servicio_snapshot,
                    }
                    for ln in m.lineas
                ],
                "coste_total": m.coste_total, "registrado_por": m.registrado_por,
            }
            for m in data.mermas
        ],
        "alertas": [
            {
                "id": a.id, "tipo": a.tipo.value, "titulo": a.titulo, "mensaje": a.mensaje,
                "fecha": a.fecha.isoformat(), "activa": a.activa, "producto_id": a.producto_id,
            }
            for a in data.alertas
        ],
        "alertas_descartadas": list(data.alertas_descartadas),
        "usuarios": [
            {"id": u.id, "nombre": u.nombre, "rol": u.rol.value, "activo": u.activo}
            for u in data.usuarios
        ],
        "configuracion": {
            "nombre_establecimiento": data.configuracion.nombre_establecimiento,
            "moneda": data.configuracion.moneda,
            "simbolo_moneda": data.configuracion.simbolo_moneda,
            "logo_path": data.configuracion.logo_path,
        } if data.configuracion else None,
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
            )
            for p in payload.get("productos", [])
        ],
        lotes=[
            LoteStock(
                l["id"], l["producto_id"], l["precio_total"], l["cantidad"], l["cantidad_restante"],
                _parse_date(l.get("fecha_compra")), _parse_date(l.get("fecha_expiracion")),
                l.get("marca_proveedor"), l.get("alerta_expiracion_dias"),
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
                    )
                    for rr in d.get("registros_recetas", [])
                ],
                hora=_parse_time(d.get("hora")),
                lineas_detalle=[
                    _detalle_from_dict(det) for det in d.get("lineas_detalle", [])
                ],
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
                    )
                    for rr in r.get("registros_recetas", [])
                ],
                hora=_parse_time(r.get("hora")),
                lineas_detalle=[
                    _detalle_from_dict(det) for det in r.get("lineas_detalle", [])
                ],
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
                    )
                    for ln in m.get("lineas", [])
                ],
                m.get("coste_total", 0), m.get("registrado_por", ""),
                hora=_parse_time(m.get("hora")),
            )
            for m in payload.get("mermas", [])
        ],
        alertas=[
            AlertaOperativa(
                a["id"], TipoAlerta(a["tipo"]), a["titulo"], a["mensaje"],
                _parse_date(a["fecha"]),  # type: ignore[arg-type]
                a.get("activa", True), a.get("producto_id"),
            )
            for a in payload.get("alertas", [])
        ],
        alertas_descartadas=list(payload.get("alertas_descartadas", [])),
        usuarios=[
            Usuario(u["id"], u["nombre"], RolUsuario(u["rol"]), u.get("activo", True))
            for u in payload.get("usuarios", [])
        ],
        configuracion=ConfiguracionHotel(**config) if config else None,
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, cls=_Encoder, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
