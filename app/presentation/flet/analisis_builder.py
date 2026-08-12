"""Construye AnalisisPanelVM desde servicios de dominio (solo Flet Admin)."""

from __future__ import annotations

from datetime import date

from app.core.auth.permissions import AuthorizationError, Permiso
from app.core.auth.session import session_tiene_permiso
from app.core.models import OrigenConsumo, TipoServicio
from app.core.services import analitica_consumo_service as analitica
from app.core.services import costes_service
from app.core.services import dashboard_service as dash
from app.core.services import merma_analisis_service as merma_an
from app.core.services import consumo_service
from app.core.services.data_service import get_repository
from app.presentation.flet.analisis_viewmodels import (
    COSTES_PESTANAS,
    CONSUMO_PESTANAS,
    MERMA_PESTANAS,
    AnalisisPanelVM,
    BarItemVM,
    ChartSeriesVM,
    MetricVM,
    RankingBlockVM,
    RankingRowVM,
)

_MERMA_PESTANA_A_AMBITO = {
    "Desayuno": "desayuno",
    "Comida": "comida",
    "Cena": "cena",
    "Bebidas": "bebidas",
    "Almacén / General": "general",
    "Sin desglose histórico": merma_an.BUCKET_SIN_DESGLOSE,
}


def _fmt_fecha_corta(f) -> str:
    if isinstance(f, date):
        return f.strftime("%d/%m")
    return str(f)


def _bars_from_dist(dist: list[dict], *, key_cat: str = "categoria") -> tuple[BarItemVM, ...]:
    repo = get_repository()
    out: list[BarItemVM] = []
    for d in dist:
        imp = float(d.get("importe") or 0)
        out.append(
            BarItemVM(
                categoria=str(d.get(key_cat) or ""),
                importe=imp,
                porcentaje=float(d.get("porcentaje") or 0),
                importe_fmt=repo.formato_precio(imp),
            )
        )
    return tuple(out)


def _chart_from_evo(
    titulo: str, evo: list[dict], series: list[str]
) -> ChartSeriesVM | None:
    puntos: list[dict[str, float | str]] = []
    for r in evo:
        row: dict[str, float | str] = {"fecha": _fmt_fecha_corta(r.get("fecha"))}
        any_v = False
        for s in series:
            v = float(r.get(s, 0) or 0)
            row[s] = v
            if v > 0:
                any_v = True
        if any_v:
            puntos.append(row)
    if not puntos:
        return None
    return ChartSeriesVM(titulo=titulo, series=tuple(series), puntos=tuple(puntos))


def _ranking_from_coste_rows(filas: list[dict]) -> tuple[RankingRowVM, ...]:
    out: list[RankingRowVM] = []
    for f in filas:
        out.append(
            RankingRowVM(
                nombre=str(f.get("nombre") or ""),
                cantidad_fmt=str(f.get("cantidad_fmt") or ""),
                usos=f.get("usos", ""),
                coste_fmt=str(f.get("coste_fmt") or ""),
                extra=str(f.get("porciones", "") or ""),
            )
        )
    return tuple(out)


def _ranking_from_analitico(filas: list[dict]) -> tuple[RankingRowVM, ...]:
    out: list[RankingRowVM] = []
    for f in filas:
        out.append(
            RankingRowVM(
                nombre=str(f.get("nombre") or ""),
                cantidad_fmt=str(f.get("cantidad_fmt") or ""),
                usos=f.get("usos", ""),
                coste_fmt=str(f.get("coste_fmt") or ""),
                tipo=str(f.get("tipo") or f.get("categoria_receta") or ""),
            )
        )
    return tuple(out)


def _ranking_from_merma(filas: list[dict]) -> tuple[RankingRowVM, ...]:
    out: list[RankingRowVM] = []
    for f in filas:
        out.append(
            RankingRowVM(
                nombre=str(f.get("nombre") or ""),
                cantidad_fmt=str(f.get("cantidad_fmt") or ""),
                usos=f.get("usos", ""),
                coste_fmt=str(f.get("coste_fmt") or ""),
                extra=str(f.get("motivos") or f.get("servicios") or ""),
            )
        )
    return tuple(out)


def build_analisis_panel(
    *,
    hub: str,
    pestana: str,
    subtab: str,
    desde: date,
    hasta: date,
    busqueda: str,
    tipo_filtro: str,
    cmp_a_desde: date,
    cmp_a_hasta: date,
    cmp_b_desde: date,
    cmp_b_hasta: date,
    export_mensaje: str = "",
) -> AnalisisPanelVM:
    if not session_tiene_permiso(Permiso.CONSULTAR_COSTES):
        return AnalisisPanelVM(
            hub=hub,
            pestana=pestana,
            desde=desde.isoformat(),
            hasta=hasta.isoformat(),
            puede_consultar=False,
            aviso="Sin permiso CONSULTAR_COSTES.",
        )

    try:
        if hub == "consumo":
            return _build_consumo(
                pestana=pestana,
                subtab=subtab,
                desde=desde,
                hasta=hasta,
                busqueda=busqueda,
                tipo_filtro=tipo_filtro,
                export_mensaje=export_mensaje,
            )
        if hub == "merma":
            return _build_merma(
                pestana=pestana,
                desde=desde,
                hasta=hasta,
                export_mensaje=export_mensaje,
            )
        return _build_costes(
            pestana=pestana,
            subtab=subtab,
            desde=desde,
            hasta=hasta,
            cmp_a_desde=cmp_a_desde,
            cmp_a_hasta=cmp_a_hasta,
            cmp_b_desde=cmp_b_desde,
            cmp_b_hasta=cmp_b_hasta,
            export_mensaje=export_mensaje,
        )
    except AuthorizationError as exc:
        return AnalisisPanelVM(
            hub=hub,
            pestana=pestana,
            desde=desde.isoformat(),
            hasta=hasta.isoformat(),
            puede_consultar=False,
            aviso=str(exc) or "Acceso denegado a costes.",
        )


def _build_costes(
    *,
    pestana: str,
    subtab: str,
    desde: date,
    hasta: date,
    cmp_a_desde: date,
    cmp_a_hasta: date,
    cmp_b_desde: date,
    cmp_b_hasta: date,
    export_mensaje: str,
) -> AnalisisPanelVM:
    repo = get_repository()
    pestana = pestana if pestana in COSTES_PESTANAS else "Resumen"
    metrics: list[MetricVM] = []
    chart_barras: list[tuple[str, tuple[BarItemVM, ...]]] = []
    chart_lineas: list[ChartSeriesVM] = []
    rankings: list[RankingBlockVM] = []
    cmp_metrics: list[MetricVM] = []
    cmp_barras: list[BarItemVM] = []
    aviso = ""

    hist = analitica.resumen_historico_incompleto(desde, hasta)
    if hist.get("hay_aviso"):
        aviso = (
            f"Histórico incompleto: {hist['n_sin_detalle']} registro(s) sin detalle "
            f"({repo.formato_precio(hist['coste_sin_detalle'])})."
        )

    if pestana == "Resumen":
        res = costes_service.resumen_ejecutivo_costes(desde, hasta)
        var = res.get("variacion_pct")
        var_txt = f"{var:+.1f}% vs periodo anterior" if var is not None else "Sin periodo anterior"
        metrics = [
            MetricVM("Coste total", res["total_fmt"], var_txt),
            MetricVM(
                "Coste medio / registro",
                res["coste_medio_registro_fmt"],
                f"{res['n_registros']} registros",
            ),
            MetricVM(
                "Coste/huésped (Desayuno)",
                res.get("coste_huesped_desayuno_fmt") or "—",
                "Solo Desayuno con huéspedes",
            ),
            MetricVM(
                "Mayor coste (servicio)",
                res["categoria_mayor"],
                repo.formato_precio(res["categoria_mayor_importe"]),
            ),
            MetricVM(
                "Merma + Expiración",
                repo.formato_precio(res["naturaleza"]["Merma"] + res["naturaleza"]["Expiración"]),
                f"Merma {repo.formato_precio(res['naturaleza']['Merma'])}",
            ),
        ]
        nat_dist = [
            {
                "categoria": k,
                "importe": v,
                "porcentaje": round((v / (res["total"] or 1)) * 100, 1) if res["total"] else 0,
            }
            for k, v in res["naturaleza"].items()
        ]
        chart_barras.append(("Naturaleza del coste", _bars_from_dist(nat_dist)))
        serv_dist = [
            {
                "categoria": k,
                "importe": v,
                "porcentaje": round((v / (res["consumo"] or 1)) * 100, 1)
                if res["consumo"]
                else 0,
            }
            for k, v in res["servicios_consumo"].items()
            if k != "Total"
        ]
        chart_barras.append(("Consumo por servicio", _bars_from_dist(serv_dist)))
        evo = costes_service.evolucion_coste_naturaleza(desde, hasta)
        ch = _chart_from_evo(
            "Evolución del coste por naturaleza",
            evo,
            ["Consumo", "Merma", "Expiración"],
        )
        if ch:
            chart_lineas.append(ch)
        rankings.append(
            RankingBlockVM(
                "Principales generadores de coste (productos)",
                _ranking_from_coste_rows(
                    costes_service.top_generadores_coste(desde, hasta, limite=8)
                ),
            )
        )
        # Comparación A/B
        naturales = list(costes_service.NATURALEZAS)
        comparacion = costes_service.comparar_periodos(
            cmp_a_desde, cmp_a_hasta, cmp_b_desde, cmp_b_hasta, naturales
        )
        for cat in naturales:
            va = comparacion["periodo_a"]["costes"].get(cat, 0)
            var_c = comparacion["variaciones"].get(cat, 0)
            cmp_metrics.append(
                MetricVM(cat, repo.formato_precio(va), f"vs B: {var_c:+.1f}%")
            )
        cmp_metrics.append(
            MetricVM(
                "Total A",
                comparacion["periodo_a"]["total_fmt"],
                comparacion["variacion_total_fmt"],
            )
        )
        grafico = costes_service.datos_grafico_comparacion(comparacion)
        # Flatten: show Periodo A and B as separate bars with labels
        for g in grafico:
            cmp_barras.append(
                BarItemVM(
                    categoria=f"{g['categoria']} ({g['periodo']})",
                    importe=float(g["coste"]),
                    importe_fmt=repo.formato_precio(g["coste"]),
                )
            )

    elif pestana == "Desayuno":
        d = costes_service.desglose_costes_desayuno(desde, hasta)
        metrics = [
            MetricVM("Desayuno", repo.formato_precio(d["Desayuno"]), "Sin bebidas"),
            MetricVM(
                "Bebidas en desayuno",
                repo.formato_precio(d["Bebidas en desayuno"]),
                "",
            ),
            MetricVM(
                "Desayuno total",
                repo.formato_precio(d["Desayuno total"]),
                "",
            ),
        ]
        if d.get("Sin desglose histórico", 0) > 0:
            aviso = (
                (aviso + " " if aviso else "")
                + f"Sin desglose histórico: {repo.formato_precio(d['Sin desglose histórico'])}."
            )
        evo = dash.evolucion_por_categoria(desde, hasta, modo_desayuno=True)
        series = ["Desayuno", "Bebidas en desayuno", "Desayuno total"]
        if any(r.get("Sin desglose histórico", 0) > 0 for r in evo):
            series = [
                "Desayuno",
                "Bebidas en desayuno",
                "Sin desglose histórico",
                "Desayuno total",
            ]
        ch = _chart_from_evo("Evolución del desglose", evo, series)
        if ch:
            chart_lineas.append(ch)
        sub = subtab or "Recetas"
        ts = TipoServicio.DESAYUNO.value
        if sub == "Extras":
            filas = analitica.ranking_productos(
                desde,
                hasta,
                tipo_servicio=ts,
                solo_consumo_bebida=False,
                tipos_elemento=["producto_directo", "extra_receta"],
                limite=15,
            )
            top = [
                {
                    "nombre": f["nombre"],
                    "coste_fmt": repo.formato_precio(f["coste"]),
                    "usos": f["usos"],
                    "cantidad_fmt": f"{f['cantidad_normalizada']:g} {f['unidad_normalizada']}",
                }
                for f in filas
            ]
            rankings.append(RankingBlockVM("Extras", _ranking_from_coste_rows(top)))
        elif sub == "Bebidas en desayuno":
            rankings.append(
                RankingBlockVM(
                    "Bebidas en desayuno",
                    _ranking_from_coste_rows(
                        costes_service.top_generadores_coste(
                            desde,
                            hasta,
                            bucket=analitica.BUCKET_BEBIDA_EN_DESAYUNO,
                            limite=15,
                        )
                    ),
                )
            )
        else:
            rankings.append(
                RankingBlockVM(
                    "Recetas",
                    _ranking_from_coste_rows(
                        costes_service.top_recetas_coste(
                            desde, hasta, tipo_servicio=ts, limite=15
                        )
                    ),
                )
            )

    elif pestana in ("Comida", "Cena"):
        etiqueta = pestana
        tipo_servicio = (
            TipoServicio.COMIDA.value if pestana == "Comida" else TipoServicio.CENA.value
        )
        serv = costes_service.costes_consumo_por_servicio(desde, hasta)
        metrics = [
            MetricVM(
                f"Coste {etiqueta}",
                repo.formato_precio(serv.get(etiqueta, 0)),
                "Solo consumo de este servicio",
            )
        ]
        evo = dash.evolucion_servicio(etiqueta, desde, hasta)
        ch = _chart_from_evo(f"Evolución del coste — {etiqueta}", evo, [etiqueta])
        if ch:
            chart_lineas.append(ch)
        sub = subtab or "Recetas"
        bucket = {
            TipoServicio.COMIDA.value: analitica.BUCKET_BEBIDA_EN_COMIDA,
            TipoServicio.CENA.value: analitica.BUCKET_BEBIDA_EN_CENA,
        }.get(tipo_servicio)
        if sub == "Productos y extras":
            filas = analitica.ranking_productos(
                desde,
                hasta,
                tipo_servicio=tipo_servicio,
                solo_consumo_bebida=False,
                tipos_elemento=["producto_directo", "extra_receta"],
                limite=15,
            )
            top = [
                {
                    "nombre": f["nombre"],
                    "coste_fmt": repo.formato_precio(f["coste"]),
                    "usos": f["usos"],
                    "cantidad_fmt": f"{f['cantidad_normalizada']:g} {f['unidad_normalizada']}",
                }
                for f in filas
            ]
            rankings.append(
                RankingBlockVM("Productos y extras", _ranking_from_coste_rows(top))
            )
        elif sub == "Bebidas" and bucket:
            rankings.append(
                RankingBlockVM(
                    "Bebidas",
                    _ranking_from_coste_rows(
                        costes_service.top_generadores_coste(
                            desde, hasta, bucket=bucket
                        )
                    ),
                )
            )
        else:
            rankings.append(
                RankingBlockVM(
                    "Recetas",
                    _ranking_from_coste_rows(
                        costes_service.top_recetas_coste(
                            desde, hasta, tipo_servicio=tipo_servicio
                        )
                    ),
                )
            )

    else:  # Bebidas
        mapa = analitica.MAPA_ORIGEN_BEBIDA
        sub = subtab or "Todas"
        if sub == "Todas":
            dist = [
                {
                    "categoria": n,
                    "importe": analitica.coste_bucket_bebida(b, desde, hasta),
                    "porcentaje": 0.0,
                }
                for n, b in mapa.items()
            ]
            tot = sum(d["importe"] for d in dist) or 1.0
            for d in dist:
                d["porcentaje"] = round((d["importe"] / tot) * 100, 1)
            indep_svc = costes_service.costes_consumo_por_servicio(desde, hasta).get(
                "Bebidas", 0.0
            )
            metrics = [
                MetricVM(
                    "Coste bebidas transversal",
                    repo.formato_precio(sum(d["importe"] for d in dist)),
                    f"Servicio independiente: {repo.formato_precio(indep_svc)}",
                )
            ]
            chart_barras.append(("Origen de bebidas", _bars_from_dist(dist)))
            evo = dash.evolucion_bebidas_por_origen(desde, hasta)
            if not any(sum(v for k, v in r.items() if k != "fecha") > 0 for r in evo):
                evo_svc = dash.evolucion_servicio("Bebidas", desde, hasta)
                ch = _chart_from_evo(
                    "Evolución — servicio Bebidas", evo_svc, ["Bebidas"]
                )
            else:
                ch = _chart_from_evo(
                    "Evolución de bebidas por origen",
                    evo,
                    ["En desayuno", "En comida", "En cena", "Independiente"],
                )
            if ch:
                chart_lineas.append(ch)
            filas = analitica.ranking_productos(
                desde, hasta, solo_consumo_bebida=True, limite=15
            )
            top = [
                {
                    "nombre": f["nombre"],
                    "coste_fmt": repo.formato_precio(f["coste"]),
                    "usos": f["usos"],
                    "cantidad_fmt": f"{f['cantidad_normalizada']:g} {f['unidad_normalizada']}",
                }
                for f in filas
            ]
            rankings.append(RankingBlockVM("Top bebidas", _ranking_from_coste_rows(top)))
        else:
            bucket = mapa[sub]
            coste_bucket = analitica.coste_bucket_bebida(bucket, desde, hasta)
            metrics = [MetricVM(f"Coste — {sub}", repo.formato_precio(coste_bucket), "")]
            if sub == "Registro independiente":
                evo = dash.evolucion_servicio("Bebidas", desde, hasta)
                ch = _chart_from_evo("Evolución — servicio Bebidas", evo, ["Bebidas"])
            else:
                etiqueta_evo = {
                    "Desayuno": "En desayuno",
                    "Comida": "En comida",
                    "Cena": "En cena",
                }[sub]
                evo_full = dash.evolucion_bebidas_por_origen(desde, hasta)
                evo = [
                    {"fecha": r["fecha"], etiqueta_evo: r.get(etiqueta_evo, 0.0)}
                    for r in evo_full
                ]
                ch = _chart_from_evo(f"Evolución — {sub}", evo, [etiqueta_evo])
            if ch:
                chart_lineas.append(ch)
            rankings.append(
                RankingBlockVM(
                    sub,
                    _ranking_from_coste_rows(
                        costes_service.top_generadores_coste(
                            desde, hasta, bucket=bucket
                        )
                    ),
                )
            )

    return AnalisisPanelVM(
        hub="costes",
        pestana=pestana,
        subtab=subtab,
        desde=desde.isoformat(),
        hasta=hasta.isoformat(),
        aviso=aviso,
        metrics=tuple(metrics),
        chart_barras=tuple(chart_barras),
        chart_lineas=tuple(chart_lineas),
        rankings=tuple(rankings),
        cmp_a_desde=cmp_a_desde.isoformat(),
        cmp_a_hasta=cmp_a_hasta.isoformat(),
        cmp_b_desde=cmp_b_desde.isoformat(),
        cmp_b_hasta=cmp_b_hasta.isoformat(),
        cmp_metrics=tuple(cmp_metrics),
        cmp_barras=tuple(cmp_barras),
        export_mensaje=export_mensaje,
        puede_consultar=True,
    )


def _build_consumo(
    *,
    pestana: str,
    subtab: str,
    desde: date,
    hasta: date,
    busqueda: str,
    tipo_filtro: str,
    export_mensaje: str,
) -> AnalisisPanelVM:
    repo = get_repository()
    pestana = pestana if pestana in CONSUMO_PESTANAS else "Resumen"
    metrics: list[MetricVM] = []
    chart_barras: list[tuple[str, tuple[BarItemVM, ...]]] = []
    chart_lineas: list[ChartSeriesVM] = []
    rankings: list[RankingBlockVM] = []
    aviso = ""
    kw = busqueda or None
    tipo = tipo_filtro or "Todos"

    hist = analitica.resumen_historico_incompleto(desde, hasta)
    if hist.get("hay_aviso"):
        partes = []
        if hist["n_sin_detalle"]:
            partes.append(
                f"{hist['n_sin_detalle']} sin detalle "
                f"({repo.formato_precio(hist['coste_sin_detalle'])})"
            )
        if hist.get("n_divergencias_detalle_total"):
            partes.append(
                f"{hist['n_divergencias_detalle_total']} divergencias detalle≠total"
            )
        aviso = "Histórico incompleto: " + "; ".join(partes) + "."

    if pestana == "Resumen":
        res = analitica.resumen_consumo(desde, hasta)
        var = res.get("variacion_pct")
        var_txt = f"{var:+.1f}% vs periodo anterior" if var is not None else "Sin periodo anterior"
        metrics = [
            MetricVM("Eventos de consumo", str(res["n_eventos_producto"]), "Líneas"),
            MetricVM(
                "Coste de consumo",
                repo.formato_precio(res["coste_consumo"]),
                var_txt,
            ),
            MetricVM("Registros", str(res["n_registros"]), "Todos los servicios"),
            MetricVM(
                "Mayor consumo",
                res["categoria_mayor"],
                repo.formato_precio(res["categoria_mayor_importe"]),
            ),
        ]
        dist = [
            {
                "categoria": k,
                "importe": v,
                "porcentaje": round((v / (res["coste_consumo"] or 1)) * 100, 1)
                if res["coste_consumo"]
                else 0,
            }
            for k, v in res["por_categoria"].items()
        ]
        chart_barras.append(("Consumo por categoría", _bars_from_dist(dist)))
        evo = dash.evolucion_por_categoria(desde, hasta, modo_desayuno=False)
        ch = _chart_from_evo(
            "Evolución del coste de consumo",
            evo,
            ["Desayuno", "Comida", "Cena", "Bebidas"],
        )
        if ch:
            chart_lineas.append(ch)
        rankings.append(
            RankingBlockVM(
                "Top 5 por coste",
                _ranking_from_analitico(
                    consumo_service.ranking_analitico_productos(
                        desde, hasta, limite=5, busqueda=kw
                    )
                ),
            )
        )
    elif pestana == "Desayuno":
        ts = TipoServicio.DESAYUNO.value
        sub = subtab or "Recetas"
        if sub == "Extras" and tipo in ("Todos", "Productos y extras"):
            extras = [
                OrigenConsumo.PRODUCTO_DIRECTO.value,
                OrigenConsumo.EXTRA_RECETA.value,
            ]
            rankings.append(
                RankingBlockVM(
                    "Extras más",
                    _ranking_from_analitico(
                        consumo_service.ranking_analitico_productos(
                            desde,
                            hasta,
                            tipo_servicio=ts,
                            tipos_elemento=extras,
                            solo_consumo_bebida=False,
                            busqueda=kw,
                            limite=15,
                        )
                    ),
                )
            )
        elif sub == "Bebidas en desayuno" and tipo in ("Todos", "Bebidas"):
            rankings.append(
                RankingBlockVM(
                    "Bebidas en desayuno",
                    _ranking_from_analitico(
                        consumo_service.ranking_analitico_productos(
                            desde,
                            hasta,
                            bucket=analitica.BUCKET_BEBIDA_EN_DESAYUNO,
                            busqueda=kw,
                            limite=15,
                        )
                    ),
                )
            )
        elif tipo in ("Todos", "Recetas"):
            rankings.append(
                RankingBlockVM(
                    "Recetas más",
                    _ranking_from_analitico(
                        consumo_service.ranking_analitico_recetas(
                            desde, hasta, tipo_servicio=ts, busqueda=kw, limite=15
                        )
                    ),
                )
            )
            rankings.append(
                RankingBlockVM(
                    "Recetas menos",
                    _ranking_from_analitico(
                        consumo_service.ranking_analitico_recetas(
                            desde,
                            hasta,
                            tipo_servicio=ts,
                            busqueda=kw,
                            limite=15,
                            ascendente=True,
                        )
                    ),
                )
            )
    elif pestana in ("Comida", "Cena"):
        etiqueta = pestana
        tipo_servicio = (
            TipoServicio.COMIDA.value if pestana == "Comida" else TipoServicio.CENA.value
        )
        sub = subtab or "Recetas"
        bucket_bebida = {
            TipoServicio.COMIDA.value: analitica.BUCKET_BEBIDA_EN_COMIDA,
            TipoServicio.CENA.value: analitica.BUCKET_BEBIDA_EN_CENA,
        }.get(tipo_servicio)
        if sub == "Productos y extras" and tipo in ("Todos", "Productos y extras"):
            tipos_el = [
                OrigenConsumo.PRODUCTO_DIRECTO.value,
                OrigenConsumo.EXTRA_RECETA.value,
            ]
            rankings.append(
                RankingBlockVM(
                    "Productos y extras",
                    _ranking_from_analitico(
                        consumo_service.ranking_analitico_productos(
                            desde,
                            hasta,
                            tipo_servicio=tipo_servicio,
                            tipos_elemento=tipos_el,
                            solo_consumo_bebida=False,
                            busqueda=kw,
                            limite=15,
                        )
                    ),
                )
            )
        elif sub == "Bebidas" and tipo in ("Todos", "Bebidas") and bucket_bebida:
            rankings.append(
                RankingBlockVM(
                    f"Bebidas en {etiqueta}",
                    _ranking_from_analitico(
                        consumo_service.ranking_analitico_productos(
                            desde,
                            hasta,
                            bucket=bucket_bebida,
                            busqueda=kw,
                            limite=15,
                        )
                    ),
                )
            )
        elif tipo in ("Todos", "Recetas"):
            rankings.append(
                RankingBlockVM(
                    f"Recetas {etiqueta}",
                    _ranking_from_analitico(
                        consumo_service.ranking_analitico_recetas(
                            desde,
                            hasta,
                            tipo_servicio=tipo_servicio,
                            busqueda=kw,
                            limite=15,
                        )
                    ),
                )
            )
    else:  # Bebidas
        if tipo not in ("Todos", "Bebidas"):
            aviso = (aviso + " " if aviso else "") + "Active filtro Bebidas o Todos."
        else:
            sub = subtab or "Todas"
            bucket_map = analitica.MAPA_ORIGEN_BEBIDA
            if sub == "Todas":
                coste = sum(
                    analitica.coste_bucket_bebida(b, desde, hasta)
                    for b in bucket_map.values()
                )
                metrics = [
                    MetricVM(
                        "Coste total bebidas",
                        repo.formato_precio(coste),
                        "Transversal",
                    )
                ]
                dist = [
                    {
                        "categoria": n,
                        "importe": analitica.coste_bucket_bebida(b, desde, hasta),
                        "porcentaje": 0.0,
                    }
                    for n, b in bucket_map.items()
                ]
                tot = sum(d["importe"] for d in dist) or 1.0
                for d in dist:
                    d["porcentaje"] = round((d["importe"] / tot) * 100, 1)
                chart_barras.append(("Por origen", _bars_from_dist(dist)))
                rankings.append(
                    RankingBlockVM(
                        "Bebidas más",
                        _ranking_from_analitico(
                            consumo_service.ranking_analitico_productos(
                                desde,
                                hasta,
                                solo_consumo_bebida=True,
                                busqueda=kw,
                                limite=15,
                            )
                        ),
                    )
                )
            else:
                bucket = bucket_map[sub]
                rankings.append(
                    RankingBlockVM(
                        f"Más — {sub}",
                        _ranking_from_analitico(
                            consumo_service.ranking_analitico_productos(
                                desde, hasta, bucket=bucket, busqueda=kw, limite=15
                            )
                        ),
                    )
                )

    return AnalisisPanelVM(
        hub="consumo",
        pestana=pestana,
        subtab=subtab,
        desde=desde.isoformat(),
        hasta=hasta.isoformat(),
        busqueda=busqueda,
        tipo_filtro=tipo,
        aviso=aviso,
        metrics=tuple(metrics),
        chart_barras=tuple(chart_barras),
        chart_lineas=tuple(chart_lineas),
        rankings=tuple(rankings),
        export_mensaje=export_mensaje,
        puede_consultar=True,
    )


def _build_merma(
    *,
    pestana: str,
    desde: date,
    hasta: date,
    export_mensaje: str,
) -> AnalisisPanelVM:
    repo = get_repository()
    pestana = pestana if pestana in MERMA_PESTANAS else "Resumen"
    metrics: list[MetricVM] = []
    chart_barras: list[tuple[str, tuple[BarItemVM, ...]]] = []
    chart_lineas: list[ChartSeriesVM] = []
    rankings: list[RankingBlockVM] = []
    aviso = ""

    hist = merma_an.resumen_historico_merma(desde, hasta)
    if hist.get("hay_aviso"):
        aviso = (
            f"Histórico incompleto: {hist['n_sin_servicio']} sin servicio, "
            f"{hist['n_sin_turno']} sin turno, {hist['n_sin_responsable']} sin responsable "
            f"(de {hist['n_lineas']} líneas)."
        )

    if pestana == "Resumen":
        res = merma_an.resumen_merma(desde, hasta)
        por = res["por_grupo"]
        metrics = [
            MetricVM("Merma total", res["total_fmt"], f"{res['n_registros']} registros"),
            MetricVM("Merma (sin expiración)", res["merma_fmt"], ""),
            MetricVM("Expiración", res["expiracion_fmt"], ""),
            MetricVM("Suma por servicio", res["suma_grupos_fmt"], "Debe = total"),
            MetricVM(
                "Sin desglose histórico",
                repo.formato_precio(por.get(merma_an.BUCKET_SIN_DESGLOSE, 0.0)),
                "Registros antiguos",
            ),
        ]
        dist = merma_an.distribucion_servicio(desde, hasta)
        chart_barras.append(("Por servicio / área", _bars_from_dist(dist)))
        motivos = merma_an.coste_por_motivo(desde, hasta)
        chart_barras.append(("Por motivo", _bars_from_dist(motivos, key_cat="categoria")))
        # coste_por_motivo may use "motivo" key - check
        if motivos and "motivo" in motivos[0] and "categoria" not in motivos[0]:
            chart_barras[-1] = (
                "Por motivo",
                _bars_from_dist(
                    [
                        {
                            "categoria": m.get("motivo") or m.get("categoria"),
                            "importe": m["importe"],
                            "porcentaje": m.get("porcentaje", 0),
                        }
                        for m in motivos
                    ]
                ),
            )
        evo = merma_an.evolucion_merma(desde, hasta)
        ch = _chart_from_evo(
            "Evolución de merma", evo, ["Merma", "Expiración", "Otros"]
        )
        if ch:
            chart_lineas.append(ch)
        rankings.append(
            RankingBlockVM(
                "Más merma (por coste)",
                _ranking_from_merma(
                    merma_an.ranking_productos_merma(
                        desde, hasta, ambito=merma_an.AMBITO_TODO, limite=10
                    )
                ),
            )
        )
    else:
        ambito = _MERMA_PESTANA_A_AMBITO.get(pestana, merma_an.AMBITO_TODO)
        res = merma_an.resumen_merma(desde, hasta, ambito=ambito)
        metrics = [
            MetricVM("Total", res["total_fmt"], f"{res['n_lineas']} líneas"),
            MetricVM("Merma", res["merma_fmt"], "Sin expiración"),
            MetricVM("Expiración", res["expiracion_fmt"], ""),
        ]
        motivos = merma_an.coste_por_motivo(desde, hasta, ambito=ambito)
        if motivos:
            key = "categoria" if "categoria" in motivos[0] else "motivo"
            chart_barras.append(
                (
                    "Por motivo",
                    _bars_from_dist(
                        [
                            {
                                "categoria": m.get(key),
                                "importe": m["importe"],
                                "porcentaje": m.get("porcentaje", 0),
                            }
                            for m in motivos
                        ]
                    ),
                )
            )
        evo = merma_an.evolucion_merma(desde, hasta, ambito=ambito)
        ch = _chart_from_evo(
            f"Evolución — {pestana}", evo, ["Merma", "Expiración", "Otros"]
        )
        if ch:
            chart_lineas.append(ch)
        rankings.append(
            RankingBlockVM(
                "Ranking",
                _ranking_from_merma(
                    merma_an.ranking_productos_merma(
                        desde, hasta, ambito=ambito, limite=10
                    )
                ),
            )
        )

    return AnalisisPanelVM(
        hub="merma",
        pestana=pestana,
        desde=desde.isoformat(),
        hasta=hasta.isoformat(),
        aviso=aviso,
        metrics=tuple(metrics),
        chart_barras=tuple(chart_barras),
        chart_lineas=tuple(chart_lineas),
        rankings=tuple(rankings),
        export_mensaje=export_mensaje,
        puede_consultar=True,
    )
