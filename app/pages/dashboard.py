"""Dashboard — vista principal."""

import streamlit as st

from app.ui.components import (
    badge_warning,
    chart_placeholder,
    empty_state,
    metric_card,
    page_header,
    section_divider,
)


def render() -> None:
    page_header("Dashboard", "Vista general del desayuno y operaciones del hotel")

    st.markdown("### Bienvenido, Usuario")
    st.caption("Resumen operativo del mes en curso")

    section_divider()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        metric_card("Coste consumo", "0,00 €", "Mes actual", "🍽️")
    with col2:
        metric_card("Coste merma", "0,00 €", "Mes actual", "📉")
    with col3:
        metric_card("Coste expiración", "0,00 €", "Mes actual", "⏳")
    with col4:
        metric_card("Coste total", "0,00 €", "Mes actual", "💰")

    section_divider()

    st.markdown("#### Evolución mensual")
    chart_placeholder("Gráfico mensual — disponible en Fase 3 (Consumo · Merma · Expiración)")

    section_divider()

    st.markdown("#### Alertas del día")
    badge_warning("Desayuno de hoy no registrado")
    st.markdown("")
    st.caption("Registre el desayuno diario para mantener el control de consumo y costes.")

    section_divider()

    st.markdown("#### Alertas operativas")
    empty_state(
        "No hay alertas operativas activas. "
        "Aquí aparecerán avisos de stock bajo, expiraciones y mermas elevadas.",
        icon="🔔",
    )

    placeholder_items = [
        "Stock bajo",
        "Producto próximo a expirar",
        "Merma superior al mes anterior",
        "Producto expirado",
    ]
    with st.expander("Tipos de alertas que se mostrarán"):
        for item in placeholder_items:
            st.markdown(f"- {item}")
