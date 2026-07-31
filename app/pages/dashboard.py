"""Dashboard — vista operativa (Fase 13)."""

from __future__ import annotations

from datetime import date

import streamlit as st

from app.core.models import ESTADO_ALERTA_LABEL, EstadoAlerta, TipoAlerta
from app.core.services import analitica_consumo_service as analitica
from app.core.services import dashboard_service as dash
from app.core.services.alert_service import (
    alertas_operativas_abiertas,
    sincronizar_alertas,
)
from app.core.services.data_service import get_repository
from app.core.services.formatting import formato_fecha
from app.ui.components import (
    badge_info,
    badge_warning,
    empty_state,
    metric_card,
    page_header,
    section_divider,
)

_PERIODOS = ["Hoy", "Esta semana", "Este mes", "Rango personalizado"]


def _fmt_var(pct: float | None) -> str:
    if pct is None:
        return "Sin periodo anterior"
    signo = "+" if pct > 0 else ""
    return f"{signo}{pct:.1f}% vs periodo anterior"


def _ir_analisis(
    subtab: str = "Consumo",
    *,
    consumo_pestana: str | None = None,
    costes_pestana: str | None = None,
    merma_pestana: str | None = None,
) -> None:
    """Deep-link a Análisis (pestaña + subpestaña del gestor)."""
    # No tocar nav_section aquí: el radio del sidebar ya está instanciado.
    # Se aplica en render_sidebar() antes de crear el widget.
    st.session_state["nav_section_pending"] = "Análisis"
    st.session_state["analisis_subtab"] = subtab
    if consumo_pestana:
        st.session_state["consumo_pestana"] = consumo_pestana
    if costes_pestana:
        st.session_state["costes_pestana"] = costes_pestana
    if merma_pestana:
        st.session_state["merma_pestana"] = merma_pestana
    st.rerun()


def _ir_stock(subtab: str = "Inventario") -> None:
    st.session_state["nav_section_pending"] = "Stock"
    st.session_state["stock_subtab"] = subtab
    st.rerun()


def _ir_registros(subtab: str = "Desayuno") -> None:
    st.session_state["nav_section_pending"] = "Registros"
    st.session_state["registros_subtab"] = subtab
    st.rerun()


def _tarjeta_categoria(
    titulo: str,
    coste: float,
    n_reg: int,
    coste_ant: float,
    *,
    desglose: analitica.DesgloseDesayuno | None = None,
    merma_txt: str = "Sin asignación a servicio",
) -> None:
    repo = get_repository()
    medio = coste / n_reg if n_reg > 0 else 0.0
    var = dash.variacion_pct(coste, coste_ant)
    st.markdown(f"##### {titulo}")
    st.markdown(f"**{repo.formato_precio(coste)}**")
    st.caption(
        f"{n_reg} registro(s) · Media {repo.formato_precio(medio)} · {_fmt_var(var)}"
    )
    st.caption(f"Merma: {merma_txt}")
    if desglose is not None:
        st.markdown(
            f"- Desayuno total: **{repo.formato_precio(desglose.desayuno_total)}**  \n"
            f"- Desayuno: {repo.formato_precio(desglose.desayuno)}  \n"
            f"- Bebidas en desayuno: {repo.formato_precio(desglose.bebida_en_desayuno)}"
        )
        if desglose.sin_desglose_historico > 0:
            st.warning(
                f"Sin desglose histórico: {repo.formato_precio(desglose.sin_desglose_historico)} "
                "(registros antiguos sin detalle de origen)."
            )
    if st.button("Ver análisis", key=f"dash_ver_{titulo}", use_container_width=True):
        _ir_analisis("Consumo", consumo_pestana=titulo)


def render() -> None:
    repo = get_repository()
    data = repo.data
    usuario = repo.get_usuario_actual()
    nombre = usuario.nombre if usuario else "Usuario"

    page_header("Dashboard", "Resumen operativo del periodo")
    st.markdown(f"### Bienvenido, {nombre}")

    periodo_op = st.selectbox("Periodo", _PERIODOS, index=2, key="dash_periodo")
    desde_c = hasta_c = None
    if periodo_op == "Rango personalizado":
        c_a, c_b = st.columns(2)
        with c_a:
            desde_c = st.date_input("Desde", value=date.today().replace(day=1), key="dash_desde")
        with c_b:
            hasta_c = st.date_input("Hasta", value=date.today(), key="dash_hasta")

    periodo = dash.resolver_periodo(
        periodo_op, desde_custom=desde_c, hasta_custom=hasta_c,
    )
    desde, hasta = periodo.desde, periodo.hasta
    ant_desde, ant_hasta = analitica.periodo_anterior(desde, hasta)

    st.caption(f"Periodo: {formato_fecha(desde)} — {formato_fecha(hasta)}")

    sincronizar_alertas()
    repo = get_repository()
    data = repo.data

    costes = analitica.coste_servicios_excluyentes(desde, hasta, data=data)
    costes_ant = analitica.coste_servicios_excluyentes(ant_desde, ant_hasta, data=data)
    desglose = analitica.desglose_desayuno(desde, hasta, data=data)
    coste_vista = costes.coste_general
    coste_vista_ant = costes_ant.coste_general
    n_reg = dash.total_registros(desde, hasta, data=data)
    n_reg_ant = dash.total_registros(ant_desde, ant_hasta, data=data)
    merma = repo.coste_merma_periodo(desde, hasta)
    expiracion = repo.coste_expiracion_periodo(desde, hasta)
    merma_total = merma + expiracion
    pct_merma = round((merma_total / coste_vista) * 100.0, 1) if coste_vista > 0 else 0.0
    alertas = alertas_operativas_abiertas(data)
    n_pendientes = sum(
        1 for a in alertas
        if (getattr(a, "estado", None) or EstadoAlerta.PENDIENTE.value)
        == EstadoAlerta.PENDIENTE.value
    )

    section_divider()

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        metric_card(
            "Coste total",
            repo.formato_precio(coste_vista),
            _fmt_var(dash.variacion_pct(coste_vista, coste_vista_ant)),
        )
    with k2:
        metric_card(
            "Servicios registrados",
            str(n_reg),
            _fmt_var(dash.variacion_pct(float(n_reg), float(n_reg_ant))),
        )
    with k3:
        metric_card(
            "Merma total",
            repo.formato_precio(merma_total),
            f"{pct_merma}% del consumo",
        )
    with k4:
        metric_card(
            "Alertas abiertas",
            str(len(alertas)),
            f"{n_pendientes} pendiente(s)",
        )

    section_divider()

    st.markdown("#### Coste por categoría")
    st.caption("Detalle y gráficos en Análisis.")
    cont = dash.contar_servicios(desde, hasta, data=data)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _tarjeta_categoria(
            "Desayuno",
            costes.desayuno_total,
            cont["desayuno"],
            costes_ant.desayuno_total,
            desglose=desglose,
        )
    with c2:
        _tarjeta_categoria(
            "Comida", costes.comida_total, cont["comida"], costes_ant.comida_total,
        )
    with c3:
        _tarjeta_categoria(
            "Cena", costes.cena_total, cont["cena"], costes_ant.cena_total,
        )
    with c4:
        _tarjeta_categoria(
            "Bebidas",
            costes.bebidas_independientes,
            cont["bebidas"],
            costes_ant.bebidas_independientes,
        )

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("Ir a Análisis · Consumo", key="dash_goto_consumo", use_container_width=True):
            _ir_analisis("Consumo")
    with b2:
        if st.button("Ir a Análisis · Costes", key="dash_goto_costes", use_container_width=True):
            _ir_analisis("Costes", costes_pestana="Resumen")
    with b3:
        if st.button("Ir a Análisis · Merma", key="dash_goto_merma", use_container_width=True):
            _ir_analisis("Merma", merma_pestana="Resumen")

    section_divider()

    st.markdown("#### Alertas operativas")
    if repo.desayuno_registrado_hoy():
        badge_info("Desayuno de hoy registrado")
    else:
        badge_warning("Falta registro de desayuno hoy")
        if st.button("Ir a Registros · Desayuno", key="dash_goto_desayuno"):
            _ir_registros("Desayuno")

    var_coste = dash.variacion_pct(costes.coste_general, costes_ant.coste_general)
    if var_coste is not None and var_coste >= 20:
        badge_warning(
            f"Incremento relevante de coste ({var_coste:+.1f}% vs periodo anterior)"
        )

    alertas_lista = [
        a for a in alertas if a.tipo != TipoAlerta.DESAYUNO_NO_REGISTRADO
    ]
    if alertas_lista:
        for alerta in alertas_lista[:8]:
            try:
                estado = EstadoAlerta(getattr(alerta, "estado", None) or "pendiente")
            except ValueError:
                estado = EstadoAlerta.PENDIENTE
            etiqueta = ESTADO_ALERTA_LABEL[estado]
            st.markdown(
                f"**{alerta.titulo}** `{etiqueta}` — {alerta.mensaje} "
                f"*({formato_fecha(alerta.fecha)})*"
            )
        if len(alertas_lista) > 8:
            st.caption(f"+{len(alertas_lista) - 8} alerta(s) más en Stock.")
        if st.button("Gestionar alertas en Stock", key="dash_goto_alertas", use_container_width=True):
            _ir_stock("Inventario")
    elif repo.desayuno_registrado_hoy() and not (
        var_coste is not None and var_coste >= 20
    ):
        empty_state("No hay alertas operativas abiertas.", icon="🔔")
