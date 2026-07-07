"""Análisis — KPIs, consumo, costes e inteligencia de negocio."""

from datetime import date

import streamlit as st

from app.core.services.data_service import get_repository
from app.core.services.formatting import formato_fecha
from app.core.services.kpi_service import exportar_kpis_excel, resumen_kpis
from app.ui.charts import chart_evolucion_costes
from app.ui.components import (
    chart_placeholder,
    empty_state,
    metric_card,
    page_header,
    render_sub_tabs,
    section_divider,
)


def _render_kpis() -> None:
    repo = get_repository()
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)

    st.markdown("#### Indicadores clave")
    col_f1, col_f2, col_h = st.columns([2, 2, 1])
    with col_f1:
        desde = st.date_input("Desde", value=inicio_mes, key="kpi_desde")
    with col_f2:
        hasta = st.date_input("Hasta", value=hoy, max_value=hoy, key="kpi_hasta")
    with col_h:
        huespedes = st.number_input(
            "Huéspedes",
            min_value=0,
            value=30,
            step=1,
            help="Para calcular el coste por huésped en el periodo.",
            key="kpi_huespedes",
        )

    if desde > hasta:
        st.error("La fecha «Desde» no puede ser posterior a «Hasta».")
        return

    kpis = resumen_kpis(desde, hasta, huespedes)
    periodo_txt = f"{formato_fecha(desde)} — {formato_fecha(hasta)}"

    section_divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        metric_card("Coste total", kpis["total_fmt"], periodo_txt)
    with col2:
        metric_card("Coste por huésped", kpis["coste_huesped_fmt"], periodo_txt if huespedes > 0 else "Indique huéspedes")
    with col3:
        metric_card("Merma total", kpis["merma_fmt"], periodo_txt)

    col4, col5, col6 = st.columns(3)
    with col4:
        metric_card("Consumo", kpis["consumo_fmt"], periodo_txt)
    with col5:
        metric_card("Expiración", kpis["expiracion_fmt"], periodo_txt)
    with col6:
        metric_card("Registros expiración", str(kpis["n_expiracion"]), periodo_txt)

    col_exp, _ = st.columns([1, 2])
    with col_exp:
        nombre_archivo = f"kpis_{desde.isoformat()}_{hasta.isoformat()}.xlsx"
        st.download_button(
            "Exportar Excel",
            data=exportar_kpis_excel(desde, hasta, huespedes),
            file_name=nombre_archivo,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="kpi_exportar_excel",
        )

    section_divider()
    st.markdown("##### Evolución diaria del periodo")
    evolucion = repo.evolucion_diaria(desde, hasta)
    if any(e["total"] > 0 for e in evolucion):
        st.altair_chart(
            chart_evolucion_costes(evolucion, "Consumo · Merma · Expiración"),
            use_container_width=True,
        )
    else:
        chart_placeholder("Sin datos de costes en el periodo seleccionado.")

    section_divider()
    col_top1, col_top2 = st.columns(2)
    with col_top1:
        st.markdown("##### Top 5 — Más costosos")
        top = repo.top_productos_costosos_periodo(desde, hasta, 5)
        if top:
            for i, item in enumerate(top, 1):
                st.markdown(f"{i}. **{item['producto']}** — {item['coste_fmt']}")
        else:
            empty_state("Sin datos en el periodo.", icon="📊")

    with col_top2:
        st.markdown("##### Top 5 — Menos costosos")
        bottom = repo.top_productos_menos_costosos_periodo(desde, hasta, 5)
        if bottom:
            for i, item in enumerate(bottom, 1):
                st.markdown(f"{i}. **{item['producto']}** — {item['coste_fmt']}")
        else:
            empty_state("Sin datos en el periodo.", icon="📊")


def _render_gestor_consumo() -> None:
    import pandas as pd

    from app.core.services.consumo_service import prediccion_necesidades

    repo = get_repository()
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)

    st.markdown("#### Gestor de consumo")
    st.caption("Analice el consumo y estime necesidades según huéspedes esperados.")

    col_h1, col_h2 = st.columns(2)
    with col_h1:
        huespedes = st.number_input(
            "Número esperado de huéspedes",
            min_value=0,
            value=30,
            step=1,
            key="consumo_huespedes",
        )
    with col_h2:
        referencia = st.number_input(
            "Referencia histórica (huéspedes)",
            min_value=1,
            value=30,
            step=1,
            help="Ocupación de referencia para escalar el consumo medio.",
            key="consumo_referencia",
        )

    section_divider()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Consumo por producto (histórico)")
        consumo = repo.consumo_por_producto()
        if consumo:
            st.dataframe(pd.DataFrame(consumo), use_container_width=True, hide_index=True)
        else:
            empty_state("Sin datos de consumo.", icon="🍽️")

    with col2:
        st.markdown("##### Consumo medio diario")
        n_dias = len({d.fecha for d in repo.data.desayunos}) or 1
        media = sum(d.coste_total for d in repo.data.desayunos) / n_dias
        metric_card("Media diaria", repo.formato_precio(media), f"Basado en {n_dias} días")

    section_divider()
    st.markdown("##### Predicción de necesidades")

    pred = prediccion_necesidades(huespedes, referencia)

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        metric_card("Coste estimado", pred["coste_estimado_fmt"], f"{huespedes} huéspedes")
    with col_p2:
        metric_card(
            "Factor de escala",
            f"{pred['factor']:.2f}x" if pred["factor"] else "—",
            f"Ref. {referencia} huéspedes",
        )

    if pred["productos"]:
        st.dataframe(
            pd.DataFrame([
                {
                    "Producto": p["producto"],
                    "Estimado": f"{p['cantidad_estimada']:g} {p['unidad']}",
                    "Stock actual": f"{p['stock_actual']:g} {p['unidad']}",
                    "Coste est.": p["coste_estimado_fmt"],
                }
                for p in pred["productos"]
            ]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        empty_state("Sin estimaciones disponibles.", icon="📋")

    st.markdown("##### Recomendación operativa")
    for rec in pred["recomendaciones"]:
        st.markdown(f"- {rec}")


def _render_gestor_costes() -> None:
    from app.core.services.costes_service import (
        CATEGORIAS,
        comparar_periodos,
        datos_grafico_comparacion,
        exportar_costes_excel,
    )
    from app.ui.charts import chart_comparacion_periodos

    repo = get_repository()
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)

    st.markdown("#### Gestor de costes")
    st.caption("Compare periodos y analice consumo, merma y expiración por categoría.")

    categorias = st.multiselect(
        "Categorías a analizar",
        CATEGORIAS,
        default=CATEGORIAS,
        key="costes_categorias",
    )
    if not categorias:
        st.warning("Seleccione al menos una categoría.")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Periodo A**")
        a_desde = st.date_input("Desde", value=inicio_mes, key="costes_a_desde")
        a_hasta = st.date_input("Hasta", value=hoy, max_value=hoy, key="costes_a_hasta")
    with col2:
        st.markdown("**Periodo B**")
        b_inicio = inicio_mes.replace(year=inicio_mes.year - 1, month=12, day=1) if inicio_mes.month == 1 else inicio_mes.replace(month=inicio_mes.month - 1, day=1)
        b_desde = st.date_input("Desde", value=b_inicio, key="costes_b_desde")
        b_hasta = st.date_input("Hasta", value=a_hasta, max_value=hoy, key="costes_b_hasta")

    if a_desde > a_hasta or b_desde > b_hasta:
        st.error("Revise las fechas de los periodos.")
        return

    comparacion = comparar_periodos(a_desde, a_hasta, b_desde, b_hasta, categorias)

    section_divider()
    st.markdown("##### Comparación de periodos")

    cols = st.columns(len(categorias) + 1)
    for i, cat in enumerate(categorias):
        with cols[i]:
            va = comparacion["periodo_a"]["costes"].get(cat, 0)
            vb = comparacion["periodo_b"]["costes"].get(cat, 0)
            var = comparacion["variaciones"].get(cat, 0)
            metric_card(cat, repo.formato_precio(va), f"vs B: {var:+.1f}%")
    with cols[-1]:
        metric_card(
            "Total A",
            comparacion["periodo_a"]["total_fmt"],
            comparacion["variacion_total_fmt"],
        )

    grafico = datos_grafico_comparacion(comparacion)
    if any(g["coste"] > 0 for g in grafico):
        st.altair_chart(chart_comparacion_periodos(grafico), use_container_width=True)

    section_divider()
    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        st.caption("Exportación PDF — disponible en fase posterior.")
        st.button("Exportar PDF", disabled=True, use_container_width=True, key="costes_exportar_pdf")
    with col_exp2:
        nombre = f"costes_{a_desde.isoformat()}_{b_hasta.isoformat()}.xlsx"
        st.download_button(
            "Exportar Excel",
            data=exportar_costes_excel(a_desde, a_hasta, b_desde, b_hasta, categorias),
            file_name=nombre,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="costes_exportar_excel",
        )


def _render_business_intelligence() -> None:
    repo = get_repository()

    st.markdown("#### Business Intelligence")
    st.caption("Asistente interno basado en reglas sobre los datos del hotel.")

    st.markdown("##### Resumen automático (datos mock)")
    top = repo.top_productos_costosos(1)
    stock_bajo = repo.productos_stock_bajo()
    resumen = (
        f"Coste total del mes: **{repo.formato_precio(repo.coste_total_mes())}**. "
        f"Producto más costoso: **{top[0]['producto']}** ({top[0]['coste_fmt']}). "
        f"Alertas activas: **{len(repo.alertas_activas())}**. "
        f"Productos con stock bajo: **{len(stock_bajo)}**."
    )
    st.info(resumen)

    st.markdown("##### Preguntas sugeridas")
    preguntas = [
        "¿Hay alguna anomalía de costes?",
        "¿Qué es lo más caro de este mes?",
        "¿Qué producto ha generado más merma?",
        "¿Qué productos están subiendo de coste?",
        "¿Qué debería revisar esta semana?",
    ]

    for i, pregunta in enumerate(preguntas):
        st.button(pregunta, disabled=True, key=f"bi_pregunta_{i}", use_container_width=True)

    section_divider()
    st.markdown("##### Respuesta")
    empty_state(
        "Seleccione una pregunta sugerida para obtener una respuesta. "
        "El chatbox con reglas estará activo en Fase 11.",
        icon="💬",
    )


_SUBTABS = {
    "KPIs": _render_kpis,
    "Gestor consumo": _render_gestor_consumo,
    "Gestor costes": _render_gestor_costes,
    "Business Intelligence": _render_business_intelligence,
}


def render() -> None:
    page_header("Análisis", "KPIs, consumo, costes e inteligencia operativa")

    selected = render_sub_tabs(list(_SUBTABS.keys()), key="analisis_subtab")
    _SUBTABS[selected]()
