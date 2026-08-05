"""Análisis de merma agrupado por tipo_servicio_snapshot (histórico).

Grupos:
- desayuno | comida | cena | bebidas | general  (snapshot)
- sin_desglose_historico  (snapshot is None)

No usa Producto.es_bebida para decidir el servicio de la merma.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.core.models import (
    AppData,
    MotivoMerma,
    ORIGEN_SERVICIO_MERMA_LABEL,
    OrigenServicioMerma,
    UnidadProducto,
)
from app.core.services.data_service import get_repository
from app.core.services.unidad_service import presentacion_legible

AMBITO_TODO = "todo"
BUCKET_SIN_DESGLOSE = "sin_desglose_historico"

GRUPOS_SERVICIO: list[str] = [m.value for m in OrigenServicioMerma] + [BUCKET_SIN_DESGLOSE]

GRUPO_LABEL: dict[str, str] = {
    **{m.value: ORIGEN_SERVICIO_MERMA_LABEL[m] for m in OrigenServicioMerma},
    BUCKET_SIN_DESGLOSE: "Sin desglose histórico",
}


@dataclass(frozen=True)
class LineaMermaAnalitica:
    fecha: date
    producto_id: str
    nombre: str
    cantidad: float
    unidad: str
    coste: float
    motivo: str
    tipo_servicio_snapshot: str | None
    bucket_servicio: str
    registro_id: str
    lote_id: str | None
    comentario: str | None
    turno_snapshot: str | None = None
    responsable_id: str | None = None
    responsable_nombre: str | None = None


def _data(data: AppData | None) -> AppData:
    return data if data is not None else get_repository().data


def _unidad(producto_id: str, data: AppData) -> str:
    producto = next((p for p in data.productos if p.id == producto_id), None)
    return producto.unidad.value if producto else "Ud"


def _nombre(producto_id: str, data: AppData) -> str:
    producto = next((p for p in data.productos if p.id == producto_id), None)
    return producto.nombre if producto else producto_id


def bucket_servicio_linea(tipo_servicio_snapshot: str | None) -> str:
    """Lee solo el snapshot; None → sin_desglose_historico. Sin catálogo vivo."""
    if tipo_servicio_snapshot in {m.value for m in OrigenServicioMerma}:
        return tipo_servicio_snapshot
    return BUCKET_SIN_DESGLOSE


def iter_lineas_merma(
    desde: date | None = None,
    hasta: date | None = None,
    *,
    data: AppData | None = None,
    ambito: str = AMBITO_TODO,
    motivos: list[str] | None = None,
    turnos: list[str] | None = None,
    responsables: list[str] | None = None,
    producto_id: str | None = None,
) -> list[LineaMermaAnalitica]:
    app = _data(data)
    resultado: list[LineaMermaAnalitica] = []
    for reg in app.mermas:
        if getattr(reg, "anulado", False):
            continue
        if desde is not None and reg.fecha < desde:
            continue
        if hasta is not None and reg.fecha > hasta:
            continue
        for ln in reg.lineas:
            motivo = ln.motivo.value if isinstance(ln.motivo, MotivoMerma) else str(ln.motivo)
            if motivos is not None and motivo not in motivos:
                continue
            turno = getattr(ln, "turno_snapshot", None)
            if turnos is not None:
                # Incluye histórico sin turno solo si el filtro lo pide explícitamente con ""
                if turno is None:
                    if "" not in turnos:
                        continue
                elif turno not in turnos:
                    continue
            resp_id = getattr(ln, "responsable_id", None)
            if responsables is not None and (resp_id or "") not in responsables:
                continue
            if producto_id is not None and ln.producto_id != producto_id:
                continue
            bucket = bucket_servicio_linea(ln.tipo_servicio_snapshot)
            if ambito != AMBITO_TODO and bucket != ambito:
                continue
            resultado.append(
                LineaMermaAnalitica(
                    fecha=reg.fecha,
                    producto_id=ln.producto_id,
                    nombre=_nombre(ln.producto_id, app),
                    cantidad=ln.cantidad,
                    unidad=_unidad(ln.producto_id, app),
                    coste=round(ln.coste, 2),
                    motivo=motivo,
                    tipo_servicio_snapshot=ln.tipo_servicio_snapshot,
                    bucket_servicio=bucket,
                    registro_id=reg.id,
                    lote_id=ln.lote_id,
                    comentario=ln.comentario,
                    turno_snapshot=turno,
                    responsable_id=resp_id,
                    responsable_nombre=getattr(ln, "responsable_nombre", None),
                )
            )
    return resultado


def resumen_historico_merma(
    desde: date | None = None,
    hasta: date | None = None,
    *,
    data: AppData | None = None,
) -> dict:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    lineas = iter_lineas_merma(desde, hasta, data=data, ambito=AMBITO_TODO)
    sin_servicio = sum(1 for l in lineas if l.bucket_servicio == BUCKET_SIN_DESGLOSE)
    sin_turno = sum(1 for l in lineas if not l.turno_snapshot)
    sin_responsable = sum(1 for l in lineas if not l.responsable_id)
    return {
        "n_lineas": len(lineas),
        "n_sin_servicio": sin_servicio,
        "n_sin_turno": sin_turno,
        "n_sin_responsable": sin_responsable,
        "hay_aviso": sin_servicio > 0 or sin_turno > 0 or sin_responsable > 0,
    }


def coste_por_grupo_servicio(
    desde: date,
    hasta: date,
    *,
    data: AppData | None = None,
) -> dict[str, float]:
    """Coste por cada grupo (incl. sin_desglose). Suma = total periodo."""
    por = {g: 0.0 for g in GRUPOS_SERVICIO}
    for l in iter_lineas_merma(desde, hasta, data=data, ambito=AMBITO_TODO):
        por[l.bucket_servicio] = round(por[l.bucket_servicio] + l.coste, 2)
    return por


def resumen_merma(
    desde: date,
    hasta: date,
    *,
    data: AppData | None = None,
    ambito: str = AMBITO_TODO,
) -> dict:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    repo = get_repository()
    app = _data(data)
    lineas = iter_lineas_merma(desde, hasta, data=app, ambito=ambito)
    merma = sum(l.coste for l in lineas if l.motivo != MotivoMerma.EXPIRACION.value)
    expiracion = sum(l.coste for l in lineas if l.motivo == MotivoMerma.EXPIRACION.value)
    total = round(merma + expiracion, 2)
    por_motivo: dict[str, float] = {}
    for l in lineas:
        por_motivo[l.motivo] = round(por_motivo.get(l.motivo, 0.0) + l.coste, 2)

    por_grupo = coste_por_grupo_servicio(desde, hasta, data=app)
    suma_grupos = round(sum(por_grupo.values()), 2)

    return {
        "total": total,
        "total_fmt": repo.formato_precio(total),
        "merma": round(merma, 2),
        "merma_fmt": repo.formato_precio(merma),
        "expiracion": round(expiracion, 2),
        "expiracion_fmt": repo.formato_precio(expiracion),
        "n_lineas": len(lineas),
        "n_registros": len({l.registro_id for l in lineas}),
        "por_motivo": por_motivo,
        "por_grupo": por_grupo,
        "suma_grupos": suma_grupos,
        "suma_grupos_fmt": repo.formato_precio(suma_grupos),
    }


def ranking_productos_merma(
    desde: date,
    hasta: date,
    *,
    data: AppData | None = None,
    ambito: str = AMBITO_TODO,
    motivos: list[str] | None = None,
    turnos: list[str] | None = None,
    responsables: list[str] | None = None,
    producto_id: str | None = None,
    ascendente: bool = False,
    limite: int | None = None,
    busqueda: str | None = None,
) -> list[dict]:
    """Ranking por coste. Cantidad en unidad del producto (sin mezclar unidades)."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    repo = get_repository()
    app = _data(data)
    acumulado: dict[str, dict] = {}
    for l in iter_lineas_merma(
        desde,
        hasta,
        data=app,
        ambito=ambito,
        motivos=motivos,
        turnos=turnos,
        responsables=responsables,
        producto_id=producto_id,
    ):
        if busqueda and busqueda.strip():
            if busqueda.strip().casefold() not in l.nombre.casefold():
                continue
        if l.cantidad <= 0 and l.coste <= 0:
            continue
        item = acumulado.setdefault(l.producto_id, {
            "producto_id": l.producto_id,
            "nombre": l.nombre,
            "cantidad": 0.0,
            "unidad": l.unidad,
            "usos": 0,
            "coste": 0.0,
            "motivos": set(),
            "servicios": set(),
        })
        if item["unidad"] == l.unidad:
            item["cantidad"] = round(item["cantidad"] + l.cantidad, 6)
        item["usos"] += 1
        item["coste"] = round(item["coste"] + l.coste, 2)
        item["motivos"].add(l.motivo)
        item["servicios"].add(GRUPO_LABEL.get(l.bucket_servicio, l.bucket_servicio))

    filas = []
    for v in acumulado.values():
        if v["usos"] <= 0:
            continue
        producto = next((p for p in app.productos if p.id == v["producto_id"]), None)
        unidad_enum = producto.unidad if producto else UnidadProducto.UD
        cant_fmt, uni_fmt = presentacion_legible(v["cantidad"], unidad_enum)
        filas.append({
            "producto_id": v["producto_id"],
            "nombre": v["nombre"],
            "cantidad": v["cantidad"],
            "unidad": v["unidad"],
            "cantidad_fmt": f"{cant_fmt:g} {uni_fmt}",
            "usos": v["usos"],
            "coste": v["coste"],
            "coste_fmt": repo.formato_precio(v["coste"]),
            "motivos": ", ".join(sorted(v["motivos"])),
            "servicios": ", ".join(sorted(v["servicios"])),
        })
    filas.sort(
        key=lambda x: (x["coste"], x["cantidad"], x["nombre"]),
        reverse=not ascendente,
    )
    if limite is not None:
        filas = filas[:limite]
    return filas


def coste_por_motivo(
    desde: date,
    hasta: date,
    *,
    data: AppData | None = None,
    ambito: str = AMBITO_TODO,
) -> list[dict]:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    repo = get_repository()
    por: dict[str, float] = {}
    for l in iter_lineas_merma(desde, hasta, data=data, ambito=ambito):
        por[l.motivo] = round(por.get(l.motivo, 0.0) + l.coste, 2)
    total = sum(por.values()) or 1.0
    return [
        {
            "categoria": motivo,
            "importe": coste,
            "porcentaje": round((coste / total) * 100, 1),
            "coste_fmt": repo.formato_precio(coste),
        }
        for motivo, coste in sorted(por.items(), key=lambda x: x[1], reverse=True)
    ]


def evolucion_merma(
    desde: date,
    hasta: date,
    *,
    data: AppData | None = None,
    ambito: str = AMBITO_TODO,
) -> list[dict]:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    if desde > hasta:
        desde, hasta = hasta, desde
    series: dict[date, dict] = {}
    cursor = desde
    while cursor <= hasta:
        series[cursor] = {
            "fecha": cursor,
            "Merma": 0.0,
            "Expiración": 0.0,
            "Otros": 0.0,
        }
        cursor += timedelta(days=1)

    for l in iter_lineas_merma(desde, hasta, data=data, ambito=ambito):
        bucket = series.get(l.fecha)
        if bucket is None:
            continue
        if l.motivo == MotivoMerma.EXPIRACION.value:
            bucket["Expiración"] = round(bucket["Expiración"] + l.coste, 2)
        elif l.motivo == MotivoMerma.MERMA.value:
            bucket["Merma"] = round(bucket["Merma"] + l.coste, 2)
        else:
            bucket["Otros"] = round(bucket["Otros"] + l.coste, 2)

    return [series[d] for d in sorted(series.keys())]


def distribucion_servicio(
    desde: date,
    hasta: date,
    *,
    data: AppData | None = None,
) -> list[dict]:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    repo = get_repository()
    por = coste_por_grupo_servicio(desde, hasta, data=data)
    total = sum(por.values()) or 1.0
    return [
        {
            "categoria": GRUPO_LABEL[g],
            "importe": coste,
            "porcentaje": round((coste / total) * 100, 1) if sum(por.values()) else 0.0,
            "coste_fmt": repo.formato_precio(coste),
            "grupo": g,
        }
        for g, coste in por.items()
    ]
