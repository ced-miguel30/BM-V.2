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
    ConfiguracionHotel,
    ExtraRecetaDesayuno,
    IngredienteReceta,
    LineaDesayuno,
    LineaMerma,
    LoteStock,
    MotivoMerma,
    OmisionRecetaDesayuno,
    Producto,
    Receta,
    RegistroDesayuno,
    RegistroMerma,
    RegistroRecetaDesayuno,
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
            }
            for d in data.desayunos
        ],
        "recetas": [
            {
                "id": r.id,
                "nombre": r.nombre,
                "ingredientes": [
                    {"producto_id": i.producto_id, "cantidad": i.cantidad}
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
                    {"producto_id": ln.producto_id, "cantidad": ln.cantidad, "coste": ln.coste,
                     "motivo": ln.motivo.value, "comentario": ln.comentario, "lote_id": ln.lote_id}
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
                    )
                    for rr in d.get("registros_recetas", [])
                ],
                hora=_parse_time(d.get("hora")),
            )
            for d in payload.get("desayunos", [])
        ],
        recetas=[
            Receta(
                r["id"],
                r["nombre"],
                [
                    IngredienteReceta(i["producto_id"], i["cantidad"])
                    for i in r.get("ingredientes", [])
                ],
            )
            for r in payload.get("recetas", [])
        ],
        mermas=[
            RegistroMerma(
                m["id"], _parse_date(m["fecha"]),  # type: ignore[arg-type]
                [
                    LineaMerma(ln["producto_id"], ln["cantidad"], ln["coste"],
                               MotivoMerma(ln["motivo"]), ln.get("comentario"), ln.get("lote_id"))
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
            Actividad(a["id"], _parse_datetime(a["fecha_hora"]), a["usuario"], a["accion"], a["detalle"])
            for a in payload.get("actividades", [])
        ],
        usuario_actual_id=payload.get("meta", {}).get("usuario_actual_id", ""),
    )


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, cls=_Encoder, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
