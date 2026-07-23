"""Análisis — Consumo, Costes, Merma e inteligencia de negocio.

Los KPIs ejecutivos viven en el Dashboard (Fase 6).
"""

from __future__ import annotations

import streamlit as st

from app.ui.components import empty_state, page_header, render_sub_tabs, section_divider

# Nombres canónicos de pestaña (plan Fase 6).
TAB_CONSUMO = "Consumo"
TAB_COSTES = "Costes"
TAB_MERMA = "Merma"
TAB_BI = "BI"

_LEGACY_SUBTABS = {
    "KPIs": TAB_CONSUMO,
    "Gestor consumo": TAB_CONSUMO,
    "Gestor costes": TAB_COSTES,
    "Gestor merma": TAB_MERMA,
    "Business Intelligence": TAB_BI,
}


def _normalizar_subtab_session() -> None:
    """Migra valores antiguos de session_state tras el renombrado de pestañas."""
    actual = st.session_state.get("analisis_subtab")
    if actual in _LEGACY_SUBTABS:
        st.session_state["analisis_subtab"] = _LEGACY_SUBTABS[actual]
    elif actual is not None and actual not in (
        TAB_CONSUMO, TAB_COSTES, TAB_MERMA, TAB_BI,
    ):
        st.session_state["analisis_subtab"] = TAB_CONSUMO


def _render_gestor_consumo() -> None:
    from app.pages.analisis_consumo import render_gestor_consumo
    render_gestor_consumo()


def _render_gestor_costes() -> None:
    from app.pages.analisis_costes import render_gestor_costes
    render_gestor_costes()


def _render_gestor_merma() -> None:
    from app.pages.analisis_merma import render_gestor_merma
    render_gestor_merma()


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
    TAB_CONSUMO: _render_gestor_consumo,
    TAB_COSTES: _render_gestor_costes,
    TAB_MERMA: _render_gestor_merma,
    TAB_BI: _render_business_intelligence,
}


def render() -> None:
    page_header("Análisis", "Consumo, costes, merma e inteligencia operativa")
    _normalizar_subtab_session()
    selected = render_sub_tabs(list(_SUBTABS.keys()), key="analisis_subtab")
    _SUBTABS[selected]()
