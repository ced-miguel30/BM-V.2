"""Gestor de costes — naturaleza × servicio (Fase 4)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app.core.models import TipoServicio
from app.core.services import analitica_consumo_service as analitica
from app.core.services import costes_service
from app.core.services import dashboard_service as dash
from app.core.services.data_service import get_repository
from app.core.services.exportacion_semanal_service import limite_semana
from app.core.services.formatting import formato_fecha
from app.ui.charts import (
    chart_barras_horizontales,
    chart_comparacion_periodos,
    chart_lineas_categorias,
)
from app.ui.components import (
    chart_placeholder,
    empty_state,
    metric_card,
    render_sub_tabs,
    section_divider,
)


def _periodo_simple(key: str) -> tuple[date, date] | None:
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)
    op = st.radio(
        "Periodo",
        ["Esta semana", "Este mes", "Rango personalizado"],
        horizontal=True,
        key=f"{key}_periodo",
    )
    if op == "Esta semana":
        return limite_semana(hoy)[0], hoy
    if op == "Este mes":
        return inicio_mes, hoy
    c1, c2 = st.columns(2)
    with c1:
        desde = st.date_input("Desde", value=inicio_mes, key=f"{key}_desde")
    with c2:
        hasta = st.date_input("Hasta", value=hoy, max_value=hoy, key=f"{key}_hasta")
    if desde > hasta:
        st.error("Revise las fechas.")
        return None
    return desde, hasta


def _tabla(filas: list[dict], columnas: list[str]) -> None:
    if not filas:
        empty_state("Sin datos de coste en el periodo.", icon="💶")
        return
    st.dataframe(pd.DataFrame(filas)[columnas], use_container_width=True, hide_index=True)


def _render_resumen(desde: date, hasta: date) -> None:
    repo = get_repository()
    res = costes_service.resumen_ejecutivo_costes(desde, hasta)
    var = res["variacion_pct"]
    var_txt = f"{var:+.1f}% vs periodo anterior" if var is not None else "Sin periodo anterior"

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        metric_card("Coste total", res["total_fmt"], var_txt)
    with c2:
        metric_card("Coste medio / registro", res["coste_medio_registro_fmt"], f"{res['n_registros']} registros")
    with c3:
        if res["coste_huesped_desayuno_fmt"]:
            metric_card(
                "Coste/huésped (solo Desayuno)",
                res["coste_huesped_desayuno_fmt"],
                "No aplica como KPI general",
            )
        else:
            metric_card("Coste/huésped", "—", "Solo Desayuno con huéspedes")
    with c4:
        metric_card(
            "Mayor coste (servicio)",
            res["categoria_mayor"],
            repo.formato_precio(res["categoria_mayor_importe"]),
        )
    with c5:
        nat = res["naturaleza"]
        metric_card(
            "Merma + Expiración",
            repo.formato_precio(nat["Merma"] + nat["Expiración"]),
            f"Merma {repo.formato_precio(nat['Merma'])}",
        )

    section_divider()
    st.markdown("##### Naturaleza del coste")
    st.caption("Eje independiente del servicio. Consumo ya incluye todos los servicios.")
    nat_dist = [
        {"categoria": k, "importe": v, "porcentaje": 0.0}
        for k, v in res["naturaleza"].items()
    ]
    tot = res["total"] or 1.0
    for d in nat_dist:
        d["porcentaje"] = round((d["importe"] / tot) * 100, 1) if res["total"] else 0
    if any(d["importe"] > 0 for d in nat_dist):
        st.altair_chart(chart_barras_horizontales(nat_dist, "Naturaleza"), use_container_width=True)
    else:
        chart_placeholder("Sin costes en el periodo.")

    section_divider()
    st.markdown("##### Consumo por servicio (categorías excluyentes)")
    serv_dist = [
        {"categoria": k, "importe": v, "porcentaje": 0.0}
        for k, v in res["servicios_consumo"].items()
        if k != "Total"
    ]
    tot_c = res["consumo"] or 1.0
    for d in serv_dist:
        d["porcentaje"] = round((d["importe"] / tot_c) * 100, 1) if res["consumo"] else 0
    if any(d["importe"] > 0 for d in serv_dist):
        st.altair_chart(
            chart_barras_horizontales(serv_dist, "Consumo por servicio"),
            use_container_width=True,
        )
    else:
        chart_placeholder("Sin consumo por servicio.")

    section_divider()
    st.markdown("##### Evolución (naturaleza)")
    evo = costes_service.evolucion_coste_naturaleza(desde, hasta)
    if any(sum(v for k, v in r.items() if k != "fecha") > 0 for r in evo):
        st.altair_chart(
            chart_lineas_categorias(
                evo, ["Consumo", "Merma", "Expiración"],
                titulo="Evolución del coste por naturaleza",
            ),
            use_container_width=True,
        )
    else:
        chart_placeholder("Sin evolución.")

    section_divider()
    st.markdown("##### Principales generadores de coste (productos)")
    top = costes_service.top_generadores_coste(desde, hasta, limite=8)
    _tabla(top, ["nombre", "cantidad_fmt", "usos", "coste_fmt"])


def _bloque_comparacion() -> None:
    st.markdown("##### Comparación con periodo anterior / Periodo B")
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)
    naturalezas = st.multiselect(
        "Naturalezas",
        costes_service.NATURALEZAS,
        default=costes_service.NATURALEZAS,
        key="costes_naturalezas",
    )
    if not naturalezas:
        st.warning("Seleccione al menos una naturaleza.")
        return
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Periodo A**")
        a_desde = st.date_input("Desde", value=inicio_mes, key="costes_a_desde")
        a_hasta = st.date_input("Hasta", value=hoy, max_value=hoy, key="costes_a_hasta")
    with col2:
        st.markdown("**Periodo B**")
        b_inicio = (
            inicio_mes.replace(year=inicio_mes.year - 1, month=12, day=1)
            if inicio_mes.month == 1
            else inicio_mes.replace(month=inicio_mes.month - 1, day=1)
        )
        b_desde = st.date_input("Desde", value=b_inicio, key="costes_b_desde")
        b_hasta = st.date_input("Hasta", value=a_hasta, max_value=hoy, key="costes_b_hasta")
    if a_desde > a_hasta or b_desde > b_hasta:
        st.error("Revise las fechas.")
        return

    comparacion = costes_service.comparar_periodos(
        a_desde, a_hasta, b_desde, b_hasta, naturalezas,
    )
    repo = get_repository()
    cols = st.columns(len(naturalezas) + 1)
    for i, cat in enumerate(naturalezas):
        with cols[i]:
            va = comparacion["periodo_a"]["costes"].get(cat, 0)
            var = comparacion["variaciones"].get(cat, 0)
            metric_card(cat, repo.formato_precio(va), f"vs B: {var:+.1f}%")
    with cols[-1]:
        metric_card(
            "Total A",
            comparacion["periodo_a"]["total_fmt"],
            comparacion["variacion_total_fmt"],
        )
    grafico = costes_service.datos_grafico_comparacion(comparacion)
    if any(g["coste"] > 0 for g in grafico):
        st.altair_chart(chart_comparacion_periodos(grafico), use_container_width=True)

    nombre = f"costes_{a_desde.isoformat()}_{b_hasta.isoformat()}.xlsx"
    st.download_button(
        "Exportar Excel",
        data=costes_service.exportar_costes_excel(
            a_desde, a_hasta, b_desde, b_hasta, naturalezas,
        ),
        file_name=nombre,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="costes_exportar_excel",
    )


def _render_desayuno(desde: date, hasta: date) -> None:
    repo = get_repository()
    d = costes_service.desglose_costes_desayuno(desde, hasta)
    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("Desayuno", repo.formato_precio(d["Desayuno"]), "Sin bebidas")
    with c2:
        metric_card("Bebidas en desayuno", repo.formato_precio(d["Bebidas en desayuno"]), "")
    with c3:
        metric_card("Desayuno total", repo.formato_precio(d["Desayuno total"]), "")
    if d["Sin desglose histórico"] > 0:
        st.warning(
            f"Sin desglose histórico: {repo.formato_precio(d['Sin desglose histórico'])}"
        )

    sub = render_sub_tabs(["Recetas", "Extras", "Bebidas en desayuno"], key="costes_des_sub")
    ts = TipoServicio.DESAYUNO.value
    if sub == "Recetas":
        top = costes_service.top_recetas_coste(desde, hasta, tipo_servicio=ts, limite=15)
        _tabla(top, ["nombre", "porciones", "usos", "coste_fmt"])
    elif sub == "Extras":
        top = costes_service.top_generadores_coste(
            desde, hasta, tipo_servicio=ts, limite=15,
        )
        # Filtrar no bebida vía analitica bucket desayuno (comida)
        filas = analitica.ranking_productos(
            desde, hasta, tipo_servicio=ts, solo_consumo_bebida=False,
            tipos_elemento=["producto_directo", "extra_receta"], limite=15,
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
        _tabla(top, ["nombre", "cantidad_fmt", "usos", "coste_fmt"])
    else:
        top = costes_service.top_generadores_coste(
            desde, hasta, bucket=analitica.BUCKET_BEBIDA_EN_DESAYUNO, limite=15,
        )
        _tabla(top, ["nombre", "cantidad_fmt", "usos", "coste_fmt"])

    evo = dash.evolucion_por_categoria(desde, hasta, modo_desayuno=True)
    st.markdown("##### Evolución del desglose")
    if any(sum(v for k, v in r.items() if k != "fecha") > 0 for r in evo):
        st.altair_chart(
            chart_lineas_categorias(
                evo, ["Desayuno", "Bebidas en desayuno", "Desayuno total"],
            ),
            use_container_width=True,
        )


def _render_servicio(etiqueta: str, tipo_servicio: str, desde: date, hasta: date) -> None:
    repo = get_repository()
    serv = costes_service.costes_consumo_por_servicio(desde, hasta)
    metric_card(
        f"Coste {etiqueta}",
        repo.formato_precio(serv.get(etiqueta, 0)),
        "Solo consumo de este servicio",
    )
    sub = render_sub_tabs(
        ["Recetas", "Productos y extras", "Bebidas"],
        key=f"costes_{tipo_servicio}_sub",
    )
    bucket = {
        TipoServicio.COMIDA.value: analitica.BUCKET_BEBIDA_EN_COMIDA,
        TipoServicio.CENA.value: analitica.BUCKET_BEBIDA_EN_CENA,
    }.get(tipo_servicio)
    if sub == "Recetas":
        _tabla(
            costes_service.top_recetas_coste(desde, hasta, tipo_servicio=tipo_servicio),
            ["nombre", "porciones", "usos", "coste_fmt"],
        )
    elif sub == "Productos y extras":
        filas = analitica.ranking_productos(
            desde, hasta, tipo_servicio=tipo_servicio, solo_consumo_bebida=False,
            tipos_elemento=["producto_directo", "extra_receta"], limite=15,
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
        _tabla(top, ["nombre", "cantidad_fmt", "usos", "coste_fmt"])
    elif bucket:
        _tabla(
            costes_service.top_generadores_coste(desde, hasta, bucket=bucket),
            ["nombre", "cantidad_fmt", "usos", "coste_fmt"],
        )


def _render_bebidas(desde: date, hasta: date) -> None:
    repo = get_repository()
    sub = render_sub_tabs(
        ["Todas", "Desayuno", "Comida", "Cena", "Registro independiente"],
        key="costes_bebidas_sub",
    )
    mapa = {
        "Desayuno": analitica.BUCKET_BEBIDA_EN_DESAYUNO,
        "Comida": analitica.BUCKET_BEBIDA_EN_COMIDA,
        "Cena": analitica.BUCKET_BEBIDA_EN_CENA,
        "Registro independiente": analitica.BUCKET_BEBIDA_INDEPENDIENTE,
    }
    if sub == "Todas":
        st.caption("Vista transversal de coste de bebidas (no es categoría Dashboard).")
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
        metric_card(
            "Coste bebidas transversal",
            repo.formato_precio(sum(d["importe"] for d in dist)),
            "",
        )
        if any(d["importe"] > 0 for d in dist):
            st.altair_chart(chart_barras_horizontales(dist), use_container_width=True)
        top = costes_service.top_generadores_coste(desde, hasta, limite=15)
        # Filtrar solo consumo_bebida
        filas = analitica.ranking_productos(
            desde, hasta, solo_consumo_bebida=True, limite=15,
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
        _tabla(top, ["nombre", "cantidad_fmt", "usos", "coste_fmt"])
    else:
        bucket = mapa[sub]
        metric_card(
            f"Coste — {sub}",
            repo.formato_precio(analitica.coste_bucket_bebida(bucket, desde, hasta)),
            "",
        )
        _tabla(
            costes_service.top_generadores_coste(desde, hasta, bucket=bucket),
            ["nombre", "cantidad_fmt", "usos", "coste_fmt"],
        )


def render_gestor_costes() -> None:
    st.markdown("#### Gestor de costes")
    st.caption(
        "Dos ejes: **naturaleza** (Consumo / Merma / Expiración) y **servicio** "
        "(solo para Consumo). Merma y expiración no se asignan a Desayuno/Comida/Cena "
        "sin vínculo fiable. Las métricas son monetarias."
    )

    periodo = _periodo_simple("costes")
    if periodo is None:
        return
    desde, hasta = periodo
    st.caption(f"Periodo: {formato_fecha(desde)} — {formato_fecha(hasta)}")

    pestana = render_sub_tabs(
        ["Resumen", "Desayuno", "Comida", "Cena", "Bebidas"],
        key="costes_pestana",
    )
    section_divider()

    if pestana == "Resumen":
        _render_resumen(desde, hasta)
        section_divider()
        _bloque_comparacion()
    elif pestana == "Desayuno":
        _render_desayuno(desde, hasta)
    elif pestana == "Comida":
        _render_servicio("Comida", TipoServicio.COMIDA.value, desde, hasta)
    elif pestana == "Cena":
        _render_servicio("Cena", TipoServicio.CENA.value, desde, hasta)
    else:
        _render_bebidas(desde, hasta)
