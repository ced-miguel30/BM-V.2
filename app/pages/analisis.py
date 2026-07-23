"""Análisis — KPIs, consumo, costes e inteligencia de negocio."""

from datetime import date, datetime

import streamlit as st

from app.core.services.data_service import get_repository
from app.core.services.exportacion_semanal_service import exportar_semana_actual, limite_semana
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


def _boton_exportar_consumo() -> None:
    """Compatibilidad: la exportación vive en analisis_consumo."""
    from app.pages.analisis_consumo import _boton_exportar
    _boton_exportar()


def _tabla_ranking(filas: list[dict]):
    import pandas as pd

    return pd.DataFrame([
        {
            "#": i,
            "Nombre": f["nombre"],
            "Cantidad": f["cantidad_fmt"],
            "Usos": f["usos"],
            "Coste": f["coste_fmt"],
        }
        for i, f in enumerate(filas, 1)
    ])


def _render_ranking(titulo: str, filas: list[dict], icon: str) -> None:
    st.markdown(f"##### {titulo}")
    if filas:
        st.dataframe(_tabla_ranking(filas), use_container_width=True, hide_index=True)
    else:
        empty_state("Sin consumo registrado en el periodo.", icon=icon)


def _render_gestor_consumo() -> None:
    from app.pages.analisis_consumo import render_gestor_consumo
    render_gestor_consumo()


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
    from app.core.services.bi_service import (
        PREGUNTAS_SUGERIDAS,
        buscar_pregunta,
        responder_pregunta,
        resumen_automatico,
    )

    st.markdown("#### Business Intelligence")
    st.caption("Asistente interno basado en reglas sobre los datos del hotel.")

    st.markdown("##### Resumen automático")
    st.info(resumen_automatico())

    st.markdown("##### Respuesta")
    if st.session_state.get("bi_respuesta"):
        if st.session_state.get("bi_pregunta_texto"):
            st.caption(f"Pregunta: {st.session_state['bi_pregunta_texto']}")
        st.markdown(st.session_state["bi_respuesta"])
    else:
        empty_state(
            "Seleccione una pregunta sugerida o escriba una consulta.",
            icon="💬",
        )

    section_divider()

    consulta = st.text_input(
        "Escriba su pregunta",
        placeholder="Ej: ¿Qué debería revisar esta semana?",
        key="bi_consulta_libre",
    )
    if st.button("Consultar", key="bi_btn_consultar", type="primary"):
        pid = buscar_pregunta(consulta)
        if pid:
            st.session_state["bi_respuesta"] = responder_pregunta(pid)
            st.session_state["bi_pregunta_texto"] = consulta
        else:
            st.session_state["bi_respuesta"] = (
                "No he podido interpretar la pregunta. "
                "Pruebe con una de las sugeridas o use palabras como «merma», «caro» o «revisar»."
            )
            st.session_state["bi_pregunta_texto"] = consulta

    section_divider()
    st.markdown("##### Preguntas sugeridas")
    for pid, pregunta in PREGUNTAS_SUGERIDAS:
        if st.button(pregunta, key=f"bi_pregunta_{pid}", use_container_width=True):
            st.session_state["bi_respuesta"] = responder_pregunta(pid)
            st.session_state["bi_pregunta_texto"] = pregunta


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
