"""Capa analítica de consumo — Fase 1.

Separa eventos de receta (porciones/frecuencia) y de producto (coste/cantidad).
Nunca suma el coste de una receta junto con el de sus ingredientes en la misma
métrica agregada.

Lectura de snapshots:
  snapshot si existe → si no, catálogo vivo (registros antiguos reconstruidos).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.models import (
    AppData,
    CategoriaReceta,
    LineaDetalleOrigen,
    RegistroDesayuno,
    RegistroRecetaDesayuno,
    RegistroRecetaServicio,
    RegistroServicio,
    TipoServicio,
)
from app.core.repositories.data_repository import DataRepository
from app.core.services.data_service import get_repository
from app.core.services.unidad_service import presentacion_legible

FAMILIA_RECETA = "receta"
FAMILIA_PRODUCTO = "producto"

BUCKET_DESAYUNO = "desayuno"
BUCKET_BEBIDA_EN_DESAYUNO = "bebida_en_desayuno"
BUCKET_BEBIDA_EN_COMIDA = "bebida_en_comida"
BUCKET_BEBIDA_EN_CENA = "bebida_en_cena"
BUCKET_BEBIDA_INDEPENDIENTE = "bebida_independiente"
BUCKET_SIN_DESGLOSE = "sin_desglose_historico"
BUCKET_COMIDA = "comida"
BUCKET_CENA = "cena"

# Etiquetas UI de origen de bebida → bucket interno (Análisis Consumo/Costes).
MAPA_ORIGEN_BEBIDA: dict[str, str] = {
    "Desayuno": BUCKET_BEBIDA_EN_DESAYUNO,
    "Comida": BUCKET_BEBIDA_EN_COMIDA,
    "Cena": BUCKET_BEBIDA_EN_CENA,
    "Registro independiente": BUCKET_BEBIDA_INDEPENDIENTE,
}

ORIGEN_REGISTRO = {
    TipoServicio.DESAYUNO.value: "registro_desayuno",
    TipoServicio.COMIDA.value: "registro_comida",
    TipoServicio.CENA.value: "registro_cena",
    TipoServicio.BEBIDAS.value: "registro_bebidas",
}


@dataclass(frozen=True)
class EventoReceta:
    familia_evento: str
    tipo_servicio: str
    origen_consumo: str
    receta_id: str
    nombre_receta: str
    porciones: float
    categoria_receta: str | None
    registro_origen_id: str
    fecha: date
    usuario: str
    # Siempre None: el coste agregado usa solo eventos_producto.
    coste: float | None = None


@dataclass(frozen=True)
class EventoProducto:
    familia_evento: str
    tipo_servicio: str
    tipo_elemento: str  # producto_directo | ingrediente_receta | extra_receta
    origen_consumo: str
    producto_id: str
    nombre_producto: str
    es_bebida: bool
    consumo_bebida: bool
    bucket_interno: str
    categoria_receta: str | None
    receta_origen_id: str | None
    registro_origen_id: str | None
    cantidad_normalizada: float
    unidad_normalizada: str
    cantidad_visible: float
    unidad_visible: str
    coste: float
    fecha: date
    usuario: str


@dataclass(frozen=True)
class DesgloseDesayuno:
    desayuno: float
    bebida_en_desayuno: float
    sin_desglose_historico: float
    desayuno_total: float


@dataclass(frozen=True)
class CostesServiciosExcluyentes:
    desayuno_total: float
    comida_total: float
    cena_total: float
    bebidas_independientes: float
    coste_general: float


def _app_data(data: AppData | None) -> AppData:
    return data if data is not None else get_repository().data


def _en_periodo(fecha: date, desde: date | None, hasta: date | None) -> bool:
    if desde is not None and fecha < desde:
        return False
    if hasta is not None and fecha > hasta:
        return False
    return True


def resolver_es_bebida(
    det: LineaDetalleOrigen,
    data: AppData,
) -> bool:
    """Snapshot si existe; si no, catálogo vivo."""
    if det.es_bebida_snapshot is not None:
        return bool(det.es_bebida_snapshot)
    producto = DataRepository(data).get_producto(det.producto_id)
    return bool(producto.es_bebida) if producto else False


def resolver_categoria_receta(
    det: LineaDetalleOrigen,
    data: AppData,
) -> str | None:
    """Snapshot → campo legacy categoria_receta → catálogo vivo."""
    if det.categoria_receta_snapshot:
        return det.categoria_receta_snapshot
    if det.categoria_receta:
        return det.categoria_receta
    if not det.receta_origen_id:
        return None
    receta = DataRepository(data).get_receta(det.receta_origen_id)
    return receta.categoria.value if receta else None


def resolver_categoria_receta_registro(
    *,
    snapshot: str | None,
    legacy: str | None,
    receta_id: str,
    data: AppData,
) -> str | None:
    if snapshot:
        return snapshot
    if legacy:
        return legacy
    receta = DataRepository(data).get_receta(receta_id)
    return receta.categoria.value if receta else None


def _bucket_producto_desayuno(det: LineaDetalleOrigen, data: AppData) -> str:
    cat = resolver_categoria_receta(det, data)
    if cat == CategoriaReceta.BEBIDAS.value:
        return BUCKET_BEBIDA_EN_DESAYUNO
    if resolver_es_bebida(det, data):
        return BUCKET_BEBIDA_EN_DESAYUNO
    return BUCKET_DESAYUNO


def _bucket_producto_servicio(
    det: LineaDetalleOrigen,
    tipo_servicio: str,
    data: AppData,
) -> str:
    """Bucket interno para desgloses / bebidas transversales."""
    if tipo_servicio == TipoServicio.DESAYUNO.value:
        return _bucket_producto_desayuno(det, data)
    if tipo_servicio == TipoServicio.BEBIDAS.value:
        return BUCKET_BEBIDA_INDEPENDIENTE
    es_bebida = resolver_es_bebida(det, data)
    cat = resolver_categoria_receta(det, data)
    es_receta_bebida = cat == CategoriaReceta.BEBIDAS.value
    if tipo_servicio == TipoServicio.COMIDA.value:
        if es_bebida or es_receta_bebida:
            return BUCKET_BEBIDA_EN_COMIDA
        return BUCKET_COMIDA
    if tipo_servicio == TipoServicio.CENA.value:
        if es_bebida or es_receta_bebida:
            return BUCKET_BEBIDA_EN_CENA
        return BUCKET_CENA
    return tipo_servicio


def _evento_desde_detalle(
    det: LineaDetalleOrigen,
    *,
    fecha: date,
    usuario: str,
    data: AppData,
    tipo_servicio: str | None = None,
) -> EventoProducto:
    repo = DataRepository(data)
    producto = repo.get_producto(det.producto_id)
    unidad_nat = producto.unidad if producto else None
    nombre = producto.nombre if producto else det.producto_id
    if unidad_nat is not None:
        cant_vis, uni_vis = presentacion_legible(det.cantidad, unidad_nat)
        uni_norm = unidad_nat.value
    else:
        cant_vis, uni_vis = det.cantidad, ""
        uni_norm = ""
    tipo = tipo_servicio or det.tipo_servicio
    es_bebida = resolver_es_bebida(det, data)
    cat = resolver_categoria_receta(det, data)
    bucket = _bucket_producto_servicio(det, tipo, data)
    consumo_bebida = bucket in {
        BUCKET_BEBIDA_EN_DESAYUNO,
        BUCKET_BEBIDA_EN_COMIDA,
        BUCKET_BEBIDA_EN_CENA,
        BUCKET_BEBIDA_INDEPENDIENTE,
    } or es_bebida or cat == CategoriaReceta.BEBIDAS.value
    return EventoProducto(
        familia_evento=FAMILIA_PRODUCTO,
        tipo_servicio=tipo,
        tipo_elemento=det.origen,
        origen_consumo=ORIGEN_REGISTRO.get(tipo, tipo),
        producto_id=det.producto_id,
        nombre_producto=nombre,
        es_bebida=es_bebida,
        consumo_bebida=consumo_bebida,
        bucket_interno=bucket,
        categoria_receta=cat,
        receta_origen_id=det.receta_origen_id,
        registro_origen_id=det.registro_origen_id,
        cantidad_normalizada=det.cantidad,
        unidad_normalizada=uni_norm,
        cantidad_visible=cant_vis,
        unidad_visible=uni_vis,
        coste=float(det.coste),
        fecha=fecha,
        usuario=usuario,
    )


def iter_eventos_producto(
    desde: date | None = None,
    hasta: date | None = None,
    *,
    data: AppData | None = None,
) -> list[EventoProducto]:
    """Eventos de producto (coste/cantidad). Una línea de detalle = un evento."""
    app = _app_data(data)
    eventos: list[EventoProducto] = []

    for d in app.desayunos:
        if getattr(d, "anulado", False):
            continue
        if not _en_periodo(d.fecha, desde, hasta):
            continue
        for det in d.lineas_detalle:
            eventos.append(_evento_desde_detalle(
                det,
                fecha=d.fecha,
                usuario=d.registrado_por,
                data=app,
                tipo_servicio=det.tipo_servicio or TipoServicio.DESAYUNO.value,
            ))

    for r in app.registros_servicio:
        if getattr(r, "anulado", False):
            continue
        if not _en_periodo(r.fecha, desde, hasta):
            continue
        for det in r.lineas_detalle:
            eventos.append(_evento_desde_detalle(
                det,
                fecha=r.fecha,
                usuario=r.registrado_por,
                data=app,
                tipo_servicio=det.tipo_servicio or r.tipo_servicio,
            ))

    return eventos


def _evento_receta_desayuno(
    rr: RegistroRecetaDesayuno,
    registro: RegistroDesayuno,
    data: AppData,
) -> EventoReceta:
    cat = resolver_categoria_receta_registro(
        snapshot=rr.categoria_receta_snapshot,
        legacy=None,
        receta_id=rr.receta_id,
        data=data,
    )
    return EventoReceta(
        familia_evento=FAMILIA_RECETA,
        tipo_servicio=TipoServicio.DESAYUNO.value,
        origen_consumo=ORIGEN_REGISTRO[TipoServicio.DESAYUNO.value],
        receta_id=rr.receta_id,
        nombre_receta=rr.nombre_receta,
        porciones=rr.porciones,
        categoria_receta=cat,
        registro_origen_id=registro.id,
        fecha=registro.fecha,
        usuario=registro.registrado_por,
    )


def _evento_receta_servicio(
    rr: RegistroRecetaServicio,
    registro: RegistroServicio,
    data: AppData,
) -> EventoReceta:
    cat = resolver_categoria_receta_registro(
        snapshot=rr.categoria_receta_snapshot,
        legacy=rr.categoria_receta,
        receta_id=rr.receta_id,
        data=data,
    )
    return EventoReceta(
        familia_evento=FAMILIA_RECETA,
        tipo_servicio=registro.tipo_servicio,
        origen_consumo=ORIGEN_REGISTRO.get(
            registro.tipo_servicio, registro.tipo_servicio,
        ),
        receta_id=rr.receta_id,
        nombre_receta=rr.nombre_receta,
        porciones=rr.porciones,
        categoria_receta=cat,
        registro_origen_id=registro.id,
        fecha=registro.fecha,
        usuario=registro.registrado_por,
    )


def iter_eventos_receta(
    desde: date | None = None,
    hasta: date | None = None,
    *,
    data: AppData | None = None,
) -> list[EventoReceta]:
    """Eventos de receta (porciones/frecuencia). Sin coste de ingredientes."""
    app = _app_data(data)
    eventos: list[EventoReceta] = []
    for d in app.desayunos:
        if getattr(d, "anulado", False):
            continue
        if not _en_periodo(d.fecha, desde, hasta):
            continue
        for rr in d.registros_recetas:
            eventos.append(_evento_receta_desayuno(rr, d, app))
    for r in app.registros_servicio:
        if getattr(r, "anulado", False):
            continue
        if not _en_periodo(r.fecha, desde, hasta):
            continue
        for rr in r.registros_recetas:
            eventos.append(_evento_receta_servicio(rr, r, app))
    return eventos


def desglose_desayuno(
    desde: date | None = None,
    hasta: date | None = None,
    *,
    data: AppData | None = None,
) -> DesgloseDesayuno:
    """Partición A / B / sin_desglose. Total = suma de coste_total de registros."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    app = _app_data(data)
    desayuno = 0.0
    bebida = 0.0
    sin_desglose = 0.0
    total = 0.0

    for d in app.desayunos:
        if getattr(d, "anulado", False):
            continue
        if not _en_periodo(d.fecha, desde, hasta):
            continue
        total += float(d.coste_total)
        if not d.lineas_detalle:
            sin_desglose += float(d.coste_total)
            continue
        for det in d.lineas_detalle:
            bucket = _bucket_producto_desayuno(det, app)
            if bucket == BUCKET_BEBIDA_EN_DESAYUNO:
                bebida += float(det.coste)
            else:
                desayuno += float(det.coste)

    return DesgloseDesayuno(
        desayuno=round(desayuno, 2),
        bebida_en_desayuno=round(bebida, 2),
        sin_desglose_historico=round(sin_desglose, 2),
        desayuno_total=round(total, 2),
    )


def _suma_registros_servicio(
    app: AppData,
    tipo: str,
    desde: date | None,
    hasta: date | None,
) -> float:
    return round(
        sum(
            float(r.coste_total)
            for r in app.registros_servicio
            if r.tipo_servicio == tipo
            and not getattr(r, "anulado", False)
            and _en_periodo(r.fecha, desde, hasta)
        ),
        2,
    )


def coste_servicios_excluyentes(
    desde: date | None = None,
    hasta: date | None = None,
    *,
    data: AppData | None = None,
) -> CostesServiciosExcluyentes:
    """Cuatro categorías mutuamente excluyentes + coste_general."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    app = _app_data(data)
    des = desglose_desayuno(desde, hasta, data=app).desayuno_total
    comida = _suma_registros_servicio(app, TipoServicio.COMIDA.value, desde, hasta)
    cena = _suma_registros_servicio(app, TipoServicio.CENA.value, desde, hasta)
    bebidas = _suma_registros_servicio(app, TipoServicio.BEBIDAS.value, desde, hasta)
    general = round(des + comida + cena + bebidas, 2)
    return CostesServiciosExcluyentes(
        desayuno_total=des,
        comida_total=comida,
        cena_total=cena,
        bebidas_independientes=bebidas,
        coste_general=general,
    )


def coste_bucket_bebida(
    bucket: str,
    desde: date | None = None,
    hasta: date | None = None,
    *,
    data: AppData | None = None,
) -> float:
    """Coste transversal de un bucket de bebida (solo eventos_producto)."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    return round(
        sum(
            e.coste
            for e in iter_eventos_producto(desde, hasta, data=data)
            if e.bucket_interno == bucket
        ),
        2,
    )


def ranking_recetas(
    desde: date | None = None,
    hasta: date | None = None,
    *,
    data: AppData | None = None,
    ascendente: bool = False,
    limite: int | None = None,
    tipo_servicio: str | None = None,
    categoria_receta: str | None = None,
    busqueda: str | None = None,
) -> list[dict]:
    """Rankings por porciones. Solo elementos con porciones > 0."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    acumulado: dict[str, dict] = {}
    for e in iter_eventos_receta(desde, hasta, data=data):
        if e.porciones <= 0:
            continue
        if tipo_servicio and e.tipo_servicio != tipo_servicio:
            continue
        if categoria_receta and e.categoria_receta != categoria_receta:
            continue
        if busqueda and busqueda.strip():
            q = busqueda.strip().casefold()
            if q not in e.nombre_receta.casefold():
                continue
        item = acumulado.setdefault(e.receta_id, {
            "receta_id": e.receta_id,
            "nombre": e.nombre_receta,
            "porciones": 0.0,
            "usos": 0,
            "categoria_receta": e.categoria_receta,
            "tipo_servicio": e.tipo_servicio,
        })
        item["porciones"] = round(item["porciones"] + e.porciones, 4)
        item["usos"] += 1

    # Coste acumulado desde eventos_producto (ingredientes/extras), no desde eventos_receta.
    costes_receta: dict[str, float] = {}
    for e in iter_eventos_producto(desde, hasta, data=data):
        if not e.receta_origen_id:
            continue
        if tipo_servicio and e.tipo_servicio != tipo_servicio:
            continue
        costes_receta[e.receta_origen_id] = round(
            costes_receta.get(e.receta_origen_id, 0.0) + e.coste, 2,
        )

    filas = []
    for v in acumulado.values():
        if v["porciones"] <= 0:
            continue
        v = dict(v)
        v["coste"] = costes_receta.get(v["receta_id"], 0.0)
        filas.append(v)
    filas.sort(key=lambda x: (x["porciones"], x["nombre"]), reverse=not ascendente)
    if limite is not None:
        filas = filas[:limite]
    return filas


def ranking_productos(
    desde: date | None = None,
    hasta: date | None = None,
    *,
    data: AppData | None = None,
    ascendente: bool = False,
    limite: int | None = None,
    solo_bebidas: bool | None = None,
    bucket: str | None = None,
    tipo_servicio: str | None = None,
    tipos_elemento: list[str] | None = None,
    solo_consumo_bebida: bool | None = None,
    busqueda: str | None = None,
) -> list[dict]:
    """Rankings por coste. Cantidad solo en unidad_normalizada del producto."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    acumulado: dict[str, dict] = {}
    for e in iter_eventos_producto(desde, hasta, data=data):
        if solo_bebidas is True and not e.consumo_bebida:
            continue
        if solo_bebidas is False and e.consumo_bebida:
            continue
        if solo_consumo_bebida is True and not e.consumo_bebida:
            continue
        if solo_consumo_bebida is False and e.consumo_bebida:
            continue
        if bucket is not None and e.bucket_interno != bucket:
            continue
        if tipo_servicio and e.tipo_servicio != tipo_servicio:
            continue
        if tipos_elemento is not None and e.tipo_elemento not in tipos_elemento:
            continue
        if busqueda and busqueda.strip():
            from app.core.services.text_search import contiene_texto

            if not contiene_texto(e.nombre_producto, busqueda):
                continue
        if e.cantidad_normalizada <= 0 and e.coste <= 0:
            continue
        item = acumulado.setdefault(e.producto_id, {
            "producto_id": e.producto_id,
            "nombre": e.nombre_producto,
            "cantidad_normalizada": 0.0,
            "unidad_normalizada": e.unidad_normalizada,
            "usos": 0,
            "coste": 0.0,
            "es_bebida": e.es_bebida,
            "tipos": set(),
        })
        if item["unidad_normalizada"] == e.unidad_normalizada:
            item["cantidad_normalizada"] = round(
                item["cantidad_normalizada"] + e.cantidad_normalizada, 6,
            )
        item["usos"] += 1
        item["coste"] = round(item["coste"] + e.coste, 2)
        item["tipos"].add(e.tipo_elemento)
    filas = []
    for v in acumulado.values():
        if v["usos"] <= 0:
            continue
        fila = dict(v)
        fila["tipos"] = sorted(fila["tipos"])
        filas.append(fila)
    filas.sort(
        key=lambda x: (x["coste"], x["cantidad_normalizada"], x["nombre"]),
        reverse=not ascendente,
    )
    if limite is not None:
        filas = filas[:limite]
    return filas


def resumen_consumo(
    desde: date | None = None,
    hasta: date | None = None,
    *,
    data: AppData | None = None,
) -> dict:
    """KPIs de resumen para el gestor de consumo."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    app = _app_data(data)
    productos = iter_eventos_producto(desde, hasta, data=app)
    costes = coste_servicios_excluyentes(desde, hasta, data=app)
    n_reg = 0
    for d in app.desayunos:
        if getattr(d, "anulado", False):
            continue
        if _en_periodo(d.fecha, desde, hasta):
            n_reg += 1
    for r in app.registros_servicio:
        if getattr(r, "anulado", False):
            continue
        if _en_periodo(r.fecha, desde, hasta):
            n_reg += 1
    pares = [
        ("Desayuno", costes.desayuno_total),
        ("Comida", costes.comida_total),
        ("Cena", costes.cena_total),
        ("Bebidas", costes.bebidas_independientes),
    ]
    mayor_nombre, mayor_importe = max(pares, key=lambda x: x[1])
    ant_desde, ant_hasta = None, None
    var = None
    if desde is not None and hasta is not None:
        ant_desde, ant_hasta = periodo_anterior(desde, hasta)
        ant = coste_servicios_excluyentes(ant_desde, ant_hasta, data=app)
        if ant.coste_general > 0:
            var = round(
                ((costes.coste_general - ant.coste_general) / ant.coste_general) * 100.0, 1,
            )
        elif costes.coste_general > 0:
            var = 100.0
    return {
        "n_eventos_producto": len(productos),
        "coste_consumo": costes.coste_general,
        "n_registros": n_reg,
        "categoria_mayor": mayor_nombre,
        "categoria_mayor_importe": mayor_importe,
        "variacion_pct": var,
        "por_categoria": {
            "Desayuno": costes.desayuno_total,
            "Comida": costes.comida_total,
            "Cena": costes.cena_total,
            "Bebidas": costes.bebidas_independientes,
        },
    }


def periodo_anterior(desde: date, hasta: date) -> tuple[date, date]:
    """Periodo de igual duración inmediatamente anterior a [desde, hasta]."""
    dias = (hasta - desde).days + 1
    hasta_ant = date.fromordinal(desde.toordinal() - 1)
    desde_ant = date.fromordinal(hasta_ant.toordinal() - dias + 1)
    return desde_ant, hasta_ant


TEXTO_EXPLICACION_CALCULO = """
**Cómo se calculan los totales (anti doble conteo)**

1. **Coste de consumo global** = suma de `coste_total` de registros de Desayuno + Comida + Cena + Bebidas (excluyentes). Los registros anulados no entran.
2. **Recetas vs productos:** el coste monetario sale solo de líneas de producto (`lineas_detalle` / eventos producto). Las recetas aportan porciones/frecuencia; **nunca** se suma el coste de una receta junto con el de sus ingredientes en el mismo total.
3. **Escalado de recetas (Fase 8):** el factor multiplica cantidades al registrar; el análisis **no** vuelve a escalar. Lee el detalle y el `coste_total` ya persistidos.
4. **Desayuno interno:** «Desayuno» + «Bebidas en desayuno» son desglose interno de `desayuno_total`, no una 5.ª categoría del Dashboard.
5. **Merma / expiración:** se analizan aparte; no se atribuyen a un servicio de consumo sin vínculo fiable.
6. **Histórico incompleto:** registros sin `lineas_detalle` (o merma sin `tipo_servicio_snapshot` / turno / responsable) se advierten; no se reinventan datos antiguos.
""".strip()


def _detalle_coste(lineas_detalle: list) -> float:
    return round(sum(float(getattr(d, "coste", 0.0) or 0.0) for d in lineas_detalle), 2)


def resumen_historico_incompleto(
    desde: date | None = None,
    hasta: date | None = None,
    *,
    data: AppData | None = None,
) -> dict:
    """Registros con coste pero sin detalle de origen (histórico incompleto)."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    app = _app_data(data)
    sin_detalle = 0
    coste_sin_detalle = 0.0
    divergencias = 0

    for d in app.desayunos:
        if getattr(d, "anulado", False):
            continue
        if not _en_periodo(d.fecha, desde, hasta):
            continue
        detalle = list(getattr(d, "lineas_detalle", None) or [])
        if not detalle:
            if float(d.coste_total or 0) > 0:
                sin_detalle += 1
                coste_sin_detalle += float(d.coste_total or 0)
            continue
        if abs(_detalle_coste(detalle) - float(d.coste_total or 0)) > 0.02:
            divergencias += 1

    for r in app.registros_servicio:
        if getattr(r, "anulado", False):
            continue
        if not _en_periodo(r.fecha, desde, hasta):
            continue
        detalle = list(getattr(r, "lineas_detalle", None) or [])
        if not detalle:
            if float(r.coste_total or 0) > 0:
                sin_detalle += 1
                coste_sin_detalle += float(r.coste_total or 0)
            continue
        if abs(_detalle_coste(detalle) - float(r.coste_total or 0)) > 0.02:
            divergencias += 1

    return {
        "n_sin_detalle": sin_detalle,
        "coste_sin_detalle": round(coste_sin_detalle, 2),
        "n_divergencias_detalle_total": divergencias,
        "hay_aviso": sin_detalle > 0 or divergencias > 0,
    }


def coherencia_detalle_vs_coste_total(
    lineas_detalle: list,
    coste_total: float,
    *,
    tolerancia: float = 0.02,
) -> bool:
    """True si hay detalle y su suma coincide con coste_total (escalado ya aplicado)."""
    if not lineas_detalle:
        return False
    return abs(_detalle_coste(lineas_detalle) - float(coste_total or 0)) <= tolerancia


__all__ = [
    "BUCKET_BEBIDA_EN_CENA",
    "BUCKET_BEBIDA_EN_COMIDA",
    "BUCKET_BEBIDA_EN_DESAYUNO",
    "BUCKET_BEBIDA_INDEPENDIENTE",
    "BUCKET_COMIDA",
    "BUCKET_CENA",
    "BUCKET_DESAYUNO",
    "BUCKET_SIN_DESGLOSE",
    "CostesServiciosExcluyentes",
    "DesgloseDesayuno",
    "EventoProducto",
    "EventoReceta",
    "FAMILIA_PRODUCTO",
    "FAMILIA_RECETA",
    "MAPA_ORIGEN_BEBIDA",
    "TEXTO_EXPLICACION_CALCULO",
    "coherencia_detalle_vs_coste_total",
    "coste_bucket_bebida",
    "coste_servicios_excluyentes",
    "desglose_desayuno",
    "iter_eventos_producto",
    "iter_eventos_receta",
    "periodo_anterior",
    "resumen_historico_incompleto",
    "ranking_productos",
    "ranking_recetas",
    "resolver_categoria_receta",
    "resolver_es_bebida",
    "resumen_consumo",
]
