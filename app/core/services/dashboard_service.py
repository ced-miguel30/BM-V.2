"""Agregados y series para el Dashboard ejecutivo (Fase 2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.core.models import AppData, TipoServicio
from app.core.repositories.data_repository import DataRepository
from app.core.services import analitica_consumo_service as analitica
from app.core.services.data_service import get_repository
from app.core.services.exportacion_semanal_service import limite_semana


@dataclass(frozen=True)
class Periodo:
    desde: date
    hasta: date
    etiqueta: str


def resolver_periodo(
    opcion: str,
    *,
    desde_custom: date | None = None,
    hasta_custom: date | None = None,
    hoy: date | None = None,
) -> Periodo:
    hoy = hoy or date.today()
    if opcion == "Hoy":
        return Periodo(hoy, hoy, "Hoy")
    if opcion == "Esta semana":
        lunes, _ = limite_semana(hoy)
        return Periodo(lunes, hoy, "Esta semana")
    if opcion == "Rango personalizado" and desde_custom and hasta_custom:
        d0, d1 = (desde_custom, hasta_custom) if desde_custom <= hasta_custom else (hasta_custom, desde_custom)
        return Periodo(d0, d1, "Rango personalizado")
    # Este mes (default)
    return Periodo(hoy.replace(day=1), hoy, "Este mes")


def _data(data: AppData | None) -> AppData:
    return data if data is not None else get_repository().data


def contar_servicios(
    desde: date,
    hasta: date,
    *,
    data: AppData | None = None,
) -> dict[str, int]:
    app = _data(data)
    cont = {
        TipoServicio.DESAYUNO.value: 0,
        TipoServicio.COMIDA.value: 0,
        TipoServicio.CENA.value: 0,
        TipoServicio.BEBIDAS.value: 0,
    }
    for d in app.desayunos:
        if desde <= d.fecha <= hasta:
            cont[TipoServicio.DESAYUNO.value] += 1
    for r in app.registros_servicio:
        if desde <= r.fecha <= hasta and r.tipo_servicio in cont:
            cont[r.tipo_servicio] += 1
    return cont


def total_registros(desde: date, hasta: date, *, data: AppData | None = None) -> int:
    return sum(contar_servicios(desde, hasta, data=data).values())


def huespedes_desayuno(desde: date, hasta: date, *, data: AppData | None = None) -> int:
    app = _data(data)
    return sum(
        int(d.num_huespedes)
        for d in app.desayunos
        if desde <= d.fecha <= hasta and d.num_huespedes > 0
    )


def coste_filtrado(
    desde: date,
    hasta: date,
    *,
    categoria: str,
    desglose_desayuno: str | None = None,
    data: AppData | None = None,
) -> float:
    """Coste según filtro de categoría Dashboard (excluyentes)."""
    app = _data(data)
    if categoria == "Todas":
        return analitica.coste_servicios_excluyentes(desde, hasta, data=app).coste_general
    if categoria == "Desayuno":
        d = analitica.desglose_desayuno(desde, hasta, data=app)
        if desglose_desayuno == "Desayuno":
            return d.desayuno
        if desglose_desayuno == "Bebidas en desayuno":
            return d.bebida_en_desayuno
        return d.desayuno_total
    if categoria == "Comida":
        return analitica.coste_servicios_excluyentes(desde, hasta, data=app).comida_total
    if categoria == "Cena":
        return analitica.coste_servicios_excluyentes(desde, hasta, data=app).cena_total
    if categoria == "Bebidas":
        return analitica.coste_servicios_excluyentes(desde, hasta, data=app).bebidas_independientes
    return 0.0


def registros_filtrados(
    desde: date,
    hasta: date,
    *,
    categoria: str,
    data: AppData | None = None,
) -> int:
    cont = contar_servicios(desde, hasta, data=data)
    if categoria == "Todas":
        return sum(cont.values())
    mapa = {
        "Desayuno": TipoServicio.DESAYUNO.value,
        "Comida": TipoServicio.COMIDA.value,
        "Cena": TipoServicio.CENA.value,
        "Bebidas": TipoServicio.BEBIDAS.value,
    }
    return cont.get(mapa.get(categoria, ""), 0)


def variacion_pct(actual: float, anterior: float) -> float | None:
    if anterior <= 0:
        return None if actual == 0 else 100.0
    return round(((actual - anterior) / anterior) * 100.0, 1)


def categoria_mayor_coste(
    desde: date,
    hasta: date,
    *,
    data: AppData | None = None,
) -> tuple[str, float, float]:
    c = analitica.coste_servicios_excluyentes(desde, hasta, data=data)
    pares = [
        ("Desayuno", c.desayuno_total),
        ("Comida", c.comida_total),
        ("Cena", c.cena_total),
        ("Bebidas", c.bebidas_independientes),
    ]
    nombre, importe = max(pares, key=lambda x: x[1])
    pct = round((importe / c.coste_general) * 100.0, 1) if c.coste_general > 0 else 0.0
    return nombre, importe, pct


def evolucion_por_categoria(
    desde: date,
    hasta: date,
    *,
    modo_desayuno: bool = False,
    data: AppData | None = None,
) -> list[dict]:
    """Serie diaria para gráfico de líneas."""
    app = _data(data)
    if desde > hasta:
        desde, hasta = hasta, desde
    filas: list[dict] = []
    cursor = desde
    while cursor <= hasta:
        if modo_desayuno:
            d = analitica.desglose_desayuno(cursor, cursor, data=app)
            filas.append({
                "fecha": cursor,
                "Desayuno": d.desayuno,
                "Bebidas en desayuno": d.bebida_en_desayuno,
                "Sin desglose histórico": d.sin_desglose_historico,
                "Desayuno total": d.desayuno_total,
            })
        else:
            c = analitica.coste_servicios_excluyentes(cursor, cursor, data=app)
            filas.append({
                "fecha": cursor,
                "Desayuno": c.desayuno_total,
                "Comida": c.comida_total,
                "Cena": c.cena_total,
                "Bebidas": c.bebidas_independientes,
            })
        cursor += timedelta(days=1)
    return filas


def evolucion_bebidas_por_origen(
    desde: date,
    hasta: date,
    *,
    data: AppData | None = None,
) -> list[dict]:
    """Serie diaria de coste de bebidas por origen (vista transversal)."""
    app = _data(data)
    if desde > hasta:
        desde, hasta = hasta, desde
    origenes = [
        ("En desayuno", analitica.BUCKET_BEBIDA_EN_DESAYUNO),
        ("En comida", analitica.BUCKET_BEBIDA_EN_COMIDA),
        ("En cena", analitica.BUCKET_BEBIDA_EN_CENA),
        ("Independiente", analitica.BUCKET_BEBIDA_INDEPENDIENTE),
    ]
    filas: list[dict] = []
    cursor = desde
    while cursor <= hasta:
        fila: dict = {"fecha": cursor}
        for nombre, bucket in origenes:
            fila[nombre] = analitica.coste_bucket_bebida(
                bucket, cursor, cursor, data=app,
            )
        filas.append(fila)
        cursor += timedelta(days=1)
    return filas


def evolucion_servicio(
    etiqueta: str,
    desde: date,
    hasta: date,
    *,
    data: AppData | None = None,
) -> list[dict]:
    """Serie diaria de una sola categoría Dashboard (Comida / Cena / Bebidas)."""
    evo = evolucion_por_categoria(desde, hasta, modo_desayuno=False, data=data)
    return [
        {"fecha": r["fecha"], etiqueta: float(r.get(etiqueta, 0) or 0)}
        for r in evo
    ]


def distribucion_categorias(
    desde: date,
    hasta: date,
    *,
    data: AppData | None = None,
) -> list[dict]:
    app = _data(data)
    actual = analitica.coste_servicios_excluyentes(desde, hasta, data=app)
    ant_desde, ant_hasta = analitica.periodo_anterior(desde, hasta)
    anterior = analitica.coste_servicios_excluyentes(ant_desde, ant_hasta, data=app)
    filas = [
        ("Desayuno", actual.desayuno_total, anterior.desayuno_total),
        ("Comida", actual.comida_total, anterior.comida_total),
        ("Cena", actual.cena_total, anterior.cena_total),
        ("Bebidas", actual.bebidas_independientes, anterior.bebidas_independientes),
    ]
    total = actual.coste_general or 1.0
    return [
        {
            "categoria": nombre,
            "importe": importe,
            "porcentaje": round((importe / total) * 100.0, 1) if actual.coste_general > 0 else 0.0,
            "variacion_pct": variacion_pct(importe, ant),
        }
        for nombre, importe, ant in filas
    ]


def consumo_vs_merma_naturaleza(
    desde: date,
    hasta: date,
    *,
    data: AppData | None = None,
) -> list[dict]:
    """Consumo por servicio excluyente + merma/expiración globales (sin atribución inventada)."""
    app = _data(data)
    repo = DataRepository(app)
    c = analitica.coste_servicios_excluyentes(desde, hasta, data=app)
    return [
        {"categoria": "Desayuno", "tipo": "Consumo", "importe": c.desayuno_total},
        {"categoria": "Comida", "tipo": "Consumo", "importe": c.comida_total},
        {"categoria": "Cena", "tipo": "Consumo", "importe": c.cena_total},
        {"categoria": "Bebidas", "tipo": "Consumo", "importe": c.bebidas_independientes},
        {"categoria": "Merma", "tipo": "Merma", "importe": repo.coste_merma_periodo(desde, hasta)},
        {"categoria": "Expiración", "tipo": "Expiración", "importe": repo.coste_expiracion_periodo(desde, hasta)},
    ]
