"""Análisis — KPIs, consumo, costes e inteligencia de negocio."""

import streamlit as st

from app.ui.components import (
    chart_placeholder,
    empty_state,
    metric_card,
    page_header,
    placeholder_panel,
    render_sub_tabs,
    section_divider,
)


def _render_kpis() -> None:
    st.markdown("#### Indicadores clave")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        st.date_input("Desde", disabled=True, key="kpi_desde")
    with col_f2:
        st.date_input("Hasta", disabled=True, key="kpi_hasta")

    section_divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        metric_card("Coste total", "0,00 €", "Periodo seleccionado")
    with col2:
        metric_card("Coste por huésped", "0,00 €", "Estimación")
    with col3:
        metric_card("Merma total", "0,00 €", "Periodo seleccionado")

    col4, col5 = st.columns(2)
    with col4:
        metric_card("Productos expirados", "0", "Este mes")
    with col5:
        st.button("Exportar Excel", disabled=True, use_container_width=True, key="kpi_exportar_excel")

    section_divider()
    chart_placeholder("Gráfica de evolución diaria / mensual — Fase 8")

    section_divider()
    col_top1, col_top2 = st.columns(2)
    with col_top1:
        st.markdown("##### Top 5 — Más costosos")
        empty_state("Sin datos disponibles.", icon="📊")
    with col_top2:
        st.markdown("##### Top 5 — Menos costosos")
        empty_state("Sin datos disponibles.", icon="📊")


def _render_gestor_consumo() -> None:
    st.markdown("#### Gestor de consumo")
    st.caption("Analice el consumo por producto y obtenga estimaciones según huéspedes esperados.")

    st.number_input(
        "Número esperado de huéspedes",
        min_value=0,
        value=0,
        disabled=True,
        key="consumo_huespedes",
    )

    section_divider()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Consumo por producto")
        empty_state("Sin datos de consumo.", icon="🍽️")
    with col2:
        st.markdown("##### Consumo medio diario")
        empty_state("Sin datos calculados.", icon="📈")

    section_divider()
    placeholder_panel(
        "Predicción de necesidades",
        "En Fase 9 se mostrarán productos estimados, coste previsto y recomendaciones.",
        [
            "Productos estimados necesarios",
            "Coste estimado del desayuno",
            "Recomendación operativa en lenguaje claro",
        ],
    )


def _render_gestor_costes() -> None:
    st.markdown("#### Gestor de costes")
    st.caption("Analice consumo, merma y expiración de forma conjunta o por categoría.")

    st.multiselect(
        "Categorías a analizar",
        ["Consumo", "Merma", "Expiración"],
        default=["Consumo", "Merma", "Expiración"],
        disabled=True,
        key="costes_categorias",
    )

    col1, col2 = st.columns(2)
    with col1:
        st.date_input("Periodo A — desde", disabled=True, key="costes_a_desde")
        st.date_input("Periodo A — hasta", disabled=True, key="costes_a_hasta")
    with col2:
        st.date_input("Periodo B — desde", disabled=True, key="costes_b_desde")
        st.date_input("Periodo B — hasta", disabled=True, key="costes_b_hasta")

    section_divider()
    empty_state(
        "Seleccione categorías y periodos para ver el análisis comparativo. "
        "Disponible en Fase 10.",
        icon="💶",
    )

    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        st.button("Exportar PDF", disabled=True, use_container_width=True, key="costes_exportar_pdf")
    with col_exp2:
        st.button("Exportar Excel", disabled=True, use_container_width=True, key="costes_exportar_excel")


def _render_business_intelligence() -> None:
    st.markdown("#### Business Intelligence")
    st.caption("Asistente interno basado en reglas sobre los datos del hotel.")

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
