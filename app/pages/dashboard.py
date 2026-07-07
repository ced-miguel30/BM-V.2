"""Dashboard — vista principal."""

import streamlit as st

from app.core.models import TipoAlerta
from app.core.services.data_service import get_repository
from app.core.services.formatting import formato_fecha
from app.ui.components import (
    badge_info,
    badge_warning,
    chart_placeholder,
    empty_state,
    metric_card,
    page_header,
    section_divider,
)


def render() -> None:
    repo = get_repository()
    usuario = repo.get_usuario_actual()
    nombre = usuario.nombre if usuario else "Usuario"

    page_header("Dashboard", "Vista general del desayuno y operaciones del hotel")

    st.markdown(f"### Bienvenido, {nombre}")
    st.caption("Resumen operativo del mes en curso")

    section_divider()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        metric_card("Coste consumo", repo.formato_precio(repo.coste_consumo_mes()), "Mes actual", "🍽️")
    with col2:
        metric_card("Coste merma", repo.formato_precio(repo.coste_merma_mes()), "Mes actual", "📉")
    with col3:
        metric_card("Coste expiración", repo.formato_precio(repo.coste_expiracion_mes()), "Mes actual", "⏳")
    with col4:
        metric_card("Coste total", repo.formato_precio(repo.coste_total_mes()), "Mes actual", "💰")

    section_divider()

    st.markdown("#### Evolución mensual")
    chart_placeholder("Gráfico mensual — disponible en Fase 3 (Consumo · Merma · Expiración)")

    section_divider()

    st.markdown("#### Alertas del día")
    if repo.desayuno_registrado_hoy():
        badge_info("Desayuno de hoy registrado")
    else:
        badge_warning("Desayuno de hoy no registrado")
        st.caption("Registre el desayuno diario para mantener el control de consumo y costes.")

    section_divider()

    st.markdown("#### Alertas operativas")
    alertas = [
        a for a in repo.alertas_activas()
        if a.tipo != TipoAlerta.DESAYUNO_NO_REGISTRADO
    ]

    if alertas:
        for alerta in alertas:
            st.markdown(
                f"**{alerta.titulo}** — {alerta.mensaje} "
                f"*( {formato_fecha(alerta.fecha)} )*"
            )
    else:
        empty_state(
            "No hay alertas operativas activas.",
            icon="🔔",
        )
