"""Dashboard — vista ejecutiva multi-categoría."""

from __future__ import annotations

from datetime import date

import streamlit as st

from app.core.models import TipoAlerta
from app.core.services import analitica_consumo_service as analitica
from app.core.services import dashboard_service as dash
from app.core.services.data_service import get_repository
from app.core.services.formatting import formato_fecha, formato_moneda
from app.ui.charts import (
    chart_barras_horizontales,
    chart_consumo_merma_naturaleza,
    chart_lineas_categorias,
)
from app.ui.components import (
    badge_info,
    badge_warning,
    chart_placeholder,
    empty_state,
    metric_card,
    page_header,
    section_divider,
)

_PERIODOS = ["Hoy", "Esta semana", "Este mes", "Rango personalizado"]
_CATEGORIAS = ["Todas", "Desayuno", "Comida", "Cena", "Bebidas"]
_DESGLOSE_DESAYUNO = ["Desayuno total", "Desayuno", "Bebidas en desayuno"]


def _fmt_var(pct: float | None) -> str:
    if pct is None:
        return "Sin periodo anterior"
    signo = "+" if pct > 0 else ""
    return f"{signo}{pct:.1f}% vs periodo anterior"


def _ir_analisis(subtab: str = "Gestor consumo") -> None:
    st.session_state["nav_section"] = "Análisis"
    st.session_state["analisis_subtab"] = subtab
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
        _ir_analisis()


def render() -> None:
    repo = get_repository()
    data = repo.data
    usuario = repo.get_usuario_actual()
    nombre = usuario.nombre if usuario else "Usuario"

    page_header("Dashboard", "Vista ejecutiva de consumo por servicio")
    st.markdown(f"### Bienvenido, {nombre}")

    # --- Filtros ---
    f1, f2, f3 = st.columns([1.2, 1.2, 1.6])
    with f1:
        periodo_op = st.selectbox("Periodo", _PERIODOS, index=2, key="dash_periodo")
    with f2:
        categoria = st.selectbox("Categoría", _CATEGORIAS, index=0, key="dash_categoria")
    desglose_sel = None
    with f3:
        if categoria == "Desayuno":
            desglose_sel = st.selectbox(
                "Desglose desayuno", _DESGLOSE_DESAYUNO, index=0, key="dash_desglose",
            )
        else:
            st.caption("Desglose interno solo al filtrar Desayuno")

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

    # --- Datos ---
    costes = analitica.coste_servicios_excluyentes(desde, hasta, data=data)
    costes_ant = analitica.coste_servicios_excluyentes(ant_desde, ant_hasta, data=data)
    desglose = analitica.desglose_desayuno(desde, hasta, data=data)
    coste_vista = dash.coste_filtrado(
        desde, hasta, categoria=categoria, desglose_desayuno=desglose_sel, data=data,
    )
    coste_vista_ant = dash.coste_filtrado(
        ant_desde, ant_hasta, categoria=categoria, desglose_desayuno=desglose_sel, data=data,
    )
    n_reg = dash.registros_filtrados(desde, hasta, categoria=categoria, data=data)
    n_reg_ant = dash.registros_filtrados(ant_desde, ant_hasta, categoria=categoria, data=data)
    merma = repo.coste_merma_periodo(desde, hasta)
    expiracion = repo.coste_expiracion_periodo(desde, hasta)
    merma_total = merma + expiracion
    consumo_ref = costes.coste_general
    pct_merma = round((merma_total / consumo_ref) * 100.0, 1) if consumo_ref > 0 else 0.0
    cat_mayor, imp_mayor, pct_mayor = dash.categoria_mayor_coste(desde, hasta, data=data)

    # Coste por huésped solo Desayuno; resto medio/registro
    if categoria == "Desayuno":
        huespedes = dash.huespedes_desayuno(desde, hasta, data=data)
        if huespedes > 0:
            kpi2_label = "Coste por huésped"
            kpi2_value = repo.formato_precio(coste_vista / huespedes)
            kpi2_delta = f"{huespedes} huésped(es)"
        else:
            kpi2_label = "Coste medio por registro"
            kpi2_value = repo.formato_precio(coste_vista / n_reg) if n_reg else formato_moneda(0)
            kpi2_delta = "Sin huéspedes en el periodo"
    else:
        kpi2_label = "Coste medio por registro"
        kpi2_value = repo.formato_precio(coste_vista / n_reg) if n_reg else formato_moneda(0)
        kpi2_delta = "No se usa coste/huésped fuera de Desayuno"

    section_divider()

    # --- Fila KPIs ---
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        metric_card(
            "Coste total",
            repo.formato_precio(coste_vista),
            _fmt_var(dash.variacion_pct(coste_vista, coste_vista_ant)),
        )
    with k2:
        metric_card(kpi2_label, kpi2_value, kpi2_delta)
    with k3:
        metric_card(
            "Servicios registrados",
            str(n_reg),
            _fmt_var(dash.variacion_pct(float(n_reg), float(n_reg_ant))),
        )
    with k4:
        metric_card(
            "Merma total",
            repo.formato_precio(merma_total),
            f"{pct_merma}% del consumo · merma {repo.formato_precio(merma)} + exp. {repo.formato_precio(expiracion)}",
        )
    with k5:
        metric_card(
            "Mayor coste",
            cat_mayor,
            f"{repo.formato_precio(imp_mayor)} ({pct_mayor}%)",
        )

    section_divider()

    # --- Tarjetas por categoría ---
    st.markdown("#### Coste por categoría")
    cont = dash.contar_servicios(desde, hasta, data=data)
    cont_ant = dash.contar_servicios(ant_desde, ant_hasta, data=data)
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

    section_divider()

    # --- Gráficos ---
    modo_des = categoria == "Desayuno"
    series = (
        ["Desayuno", "Bebidas en desayuno", "Desayuno total"]
        if modo_des
        else ["Desayuno", "Comida", "Cena", "Bebidas"]
    )
    evo = dash.evolucion_por_categoria(desde, hasta, modo_desayuno=modo_des, data=data)
    st.markdown("#### Evolución del coste por categoría")
    if any(sum(v for k, v in row.items() if k != "fecha") > 0 for row in evo):
        st.altair_chart(
            chart_lineas_categorias(evo, series),
            use_container_width=True,
        )
    else:
        chart_placeholder("Sin datos de evolución en el periodo.")

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        st.markdown("#### Distribución del coste")
        dist = dash.distribucion_categorias(desde, hasta, data=data)
        if modo_des:
            # Detalle desayuno: A y B como barras; total solo referencia (caption)
            dist_des = [
                {
                    "categoria": "Desayuno",
                    "importe": desglose.desayuno,
                    "porcentaje": round(
                        (desglose.desayuno / desglose.desayuno_total) * 100, 1,
                    ) if desglose.desayuno_total else 0,
                },
                {
                    "categoria": "Bebidas en desayuno",
                    "importe": desglose.bebida_en_desayuno,
                    "porcentaje": round(
                        (desglose.bebida_en_desayuno / desglose.desayuno_total) * 100, 1,
                    ) if desglose.desayuno_total else 0,
                },
            ]
            if desglose.sin_desglose_historico > 0:
                dist_des.append({
                    "categoria": "Sin desglose histórico",
                    "importe": desglose.sin_desglose_historico,
                    "porcentaje": round(
                        (desglose.sin_desglose_historico / desglose.desayuno_total) * 100, 1,
                    ) if desglose.desayuno_total else 0,
                })
            st.caption(
                f"Desayuno total (referencia): {repo.formato_precio(desglose.desayuno_total)}"
            )
            if any(x["importe"] > 0 for x in dist_des):
                st.altair_chart(chart_barras_horizontales(dist_des), use_container_width=True)
            else:
                chart_placeholder("Sin distribución de desayuno.")
        elif any(x["importe"] > 0 for x in dist):
            st.altair_chart(chart_barras_horizontales(dist), use_container_width=True)
        else:
            chart_placeholder("Sin distribución en el periodo.")

    with col_g2:
        st.markdown("#### Consumo frente a merma")
        st.caption(
            "La merma y la expiración no se atribuyen a Desayuno/Comida/Cena "
            "porque no hay vínculo fiable con el servicio."
        )
        cm = dash.consumo_vs_merma_naturaleza(desde, hasta, data=data)
        if any(x["importe"] > 0 for x in cm):
            st.altair_chart(chart_consumo_merma_naturaleza(cm), use_container_width=True)
        else:
            chart_placeholder("Sin datos de consumo/merma.")

    section_divider()

    # --- Alertas ---
    st.markdown("#### Alertas accionables")
    if repo.desayuno_registrado_hoy():
        badge_info("Desayuno de hoy registrado")
    else:
        badge_warning("Falta registro de desayuno hoy")
        st.caption("Acción: vaya a Registros → Desayuno.")

    var_coste = dash.variacion_pct(costes.coste_general, costes_ant.coste_general)
    if var_coste is not None and var_coste >= 20:
        badge_warning(
            f"Incremento relevante de coste ({var_coste:+.1f}% vs periodo anterior)"
        )
        st.caption(f"Categoría líder: {cat_mayor}. Revisar Gestor de costes.")

    merma_ant = repo.coste_merma_periodo(ant_desde, ant_hasta) + repo.coste_expiracion_periodo(
        ant_desde, ant_hasta,
    )
    var_merma = dash.variacion_pct(merma_total, merma_ant)
    if var_merma is not None and var_merma >= 20:
        badge_warning(
            f"Incremento relevante de merma ({var_merma:+.1f}% vs periodo anterior)"
        )

    for nombre, actual, ant in [
        ("Desayuno", costes.desayuno_total, costes_ant.desayuno_total),
        ("Comida", costes.comida_total, costes_ant.comida_total),
        ("Cena", costes.cena_total, costes_ant.cena_total),
        ("Bebidas", costes.bebidas_independientes, costes_ant.bebidas_independientes),
    ]:
        v = dash.variacion_pct(actual, ant)
        if v is not None and abs(v) >= 25 and actual > 0:
            badge_warning(f"Desviación en {nombre}: {v:+.1f}% vs periodo anterior")

    alertas = [
        a for a in repo.alertas_activas()
        if a.tipo != TipoAlerta.DESAYUNO_NO_REGISTRADO
    ]
    if alertas:
        st.markdown("##### Alertas de stock / caducidad")
        for alerta in alertas:
            st.markdown(
                f"**{alerta.titulo}** — {alerta.mensaje} "
                f"*({formato_fecha(alerta.fecha)})* · Acción: Stock"
            )
    elif not any([
        not repo.desayuno_registrado_hoy(),
        var_coste is not None and var_coste >= 20,
        var_merma is not None and var_merma >= 20,
    ]):
        empty_state("No hay alertas accionables en este momento.", icon="🔔")
