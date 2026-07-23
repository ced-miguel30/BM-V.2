"""Gestor de merma — Resumen / servicios deshabilitados / Bebidas / General (Fase 5)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app.core.models import MotivoMerma
from app.core.services import merma_analisis_service as merma_an
from app.core.services.exportacion_semanal_service import limite_semana
from app.core.services.formatting import formato_fecha
from app.ui.charts import chart_barras_horizontales, chart_lineas_categorias
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
        empty_state("Sin merma registrada en el periodo.", icon="🗑️")
        return
    st.dataframe(pd.DataFrame(filas)[columnas], use_container_width=True, hide_index=True)


def _filtro_motivo(key: str) -> list[str] | None:
    opciones = [m.value for m in MotivoMerma]
    sel = st.multiselect(
        "Motivos",
        opciones,
        default=opciones,
        key=f"{key}_motivos",
    )
    if not sel:
        st.warning("Seleccione al menos un motivo.")
        return None
    return sel


def _aviso_servicio_deshabilitado(nombre: str) -> None:
    st.info(
        f"**{nombre}** — pestaña deshabilitada.\n\n"
        + merma_an.MSG_SERVICIO_SIN_VINCULO
    )


def _bloque_rankings(
    desde: date,
    hasta: date,
    *,
    ambito: str,
    key: str,
) -> None:
    motivos = _filtro_motivo(key)
    if motivos is None:
        return
    busqueda = st.text_input("Buscador", value="", key=f"{key}_busqueda")
    mas = merma_an.ranking_productos_merma(
        desde, hasta, ambito=ambito, motivos=motivos,
        busqueda=busqueda or None, limite=15,
    )
    menos = merma_an.ranking_productos_merma(
        desde, hasta, ambito=ambito, motivos=motivos,
        busqueda=busqueda or None, ascendente=True, limite=15,
    )
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Más merma (por coste)")
        _tabla(mas, ["nombre", "cantidad_fmt", "usos", "motivos", "coste_fmt"])
    with c2:
        st.markdown("##### Menos merma (uso > 0)")
        _tabla(menos, ["nombre", "cantidad_fmt", "usos", "motivos", "coste_fmt"])


def _render_resumen(desde: date, hasta: date) -> None:
    res = merma_an.resumen_merma(desde, hasta)
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        metric_card("Merma total", res["total_fmt"], f"{res['n_registros']} registros")
    with c2:
        metric_card("Merma (sin expiración)", res["merma_fmt"], "")
    with c3:
        metric_card("Expiración", res["expiracion_fmt"], "")
    with c4:
        metric_card("Productos bebida", res["bebida_fmt"], "Catálogo es_bebida")
    with c5:
        metric_card("General", res["general_fmt"], "No bebida")

    st.caption(
        "La merma no se reparte entre Desayuno/Comida/Cena: no hay vínculo de servicio. "
        "«Productos bebida» usa el catálogo (`es_bebida`), no el servicio Bebidas."
    )

    section_divider()
    st.markdown("##### Por motivo")
    motivos = merma_an.coste_por_motivo(desde, hasta)
    if any(m["importe"] > 0 for m in motivos):
        st.altair_chart(
            chart_barras_horizontales(motivos, "Motivo"),
            use_container_width=True,
        )
    else:
        chart_placeholder("Sin merma en el periodo.")

    section_divider()
    st.markdown("##### Bebida vs general")
    dist = merma_an.distribucion_ambito(desde, hasta)
    if any(d["importe"] > 0 for d in dist):
        st.altair_chart(
            chart_barras_horizontales(dist, "Ámbito"),
            use_container_width=True,
        )
    else:
        chart_placeholder("Sin datos.")

    section_divider()
    st.markdown("##### Evolución")
    evo = merma_an.evolucion_merma(desde, hasta)
    if any(sum(v for k, v in r.items() if k != "fecha") > 0 for r in evo):
        st.altair_chart(
            chart_lineas_categorias(
                evo, ["Merma", "Expiración", "Otros"],
                titulo="Evolución de merma",
            ),
            use_container_width=True,
        )
    else:
        chart_placeholder("Sin evolución.")

    section_divider()
    st.markdown("##### Ranking global")
    _bloque_rankings(desde, hasta, ambito=merma_an.AMBITO_TODO, key="merma_res")


def _render_ambito(
    titulo: str,
    caption: str,
    ambito: str,
    desde: date,
    hasta: date,
    key: str,
) -> None:
    st.markdown(f"##### {titulo}")
    st.caption(caption)
    res = merma_an.resumen_merma(desde, hasta, ambito=ambito)
    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("Total", res["total_fmt"], f"{res['n_lineas']} líneas")
    with c2:
        metric_card("Merma", res["merma_fmt"], "Sin expiración")
    with c3:
        metric_card("Expiración", res["expiracion_fmt"], "")

    section_divider()
    motivos = merma_an.coste_por_motivo(desde, hasta, ambito=ambito)
    if any(m["importe"] > 0 for m in motivos):
        st.altair_chart(
            chart_barras_horizontales(motivos, "Motivo"),
            use_container_width=True,
        )

    evo = merma_an.evolucion_merma(desde, hasta, ambito=ambito)
    if any(sum(v for k, v in r.items() if k != "fecha") > 0 for r in evo):
        st.altair_chart(
            chart_lineas_categorias(
                evo, ["Merma", "Expiración", "Otros"],
                titulo=f"Evolución — {titulo}",
            ),
            use_container_width=True,
        )

    section_divider()
    _bloque_rankings(desde, hasta, ambito=ambito, key=key)


def render_gestor_merma() -> None:
    st.markdown("#### Gestor de merma")
    st.caption(
        "La merma es global: no se atribuye a Desayuno, Comida ni Cena. "
        "La pestaña **Bebidas** muestra merma de **productos bebida** del catálogo, "
        "no merma del servicio Bebidas."
    )

    periodo = _periodo_simple("merma")
    if periodo is None:
        return
    desde, hasta = periodo
    st.caption(f"Periodo: {formato_fecha(desde)} — {formato_fecha(hasta)}")

    pestana = render_sub_tabs(
        ["Resumen", "Desayuno", "Comida", "Cena", "Bebidas", "General"],
        key="merma_pestana",
    )
    section_divider()

    if pestana == "Resumen":
        _render_resumen(desde, hasta)
    elif pestana in ("Desayuno", "Comida", "Cena"):
        _aviso_servicio_deshabilitado(pestana)
    elif pestana == "Bebidas":
        _render_ambito(
            "Merma de productos bebida",
            "Productos del catálogo con es_bebida. No es el servicio independiente Bebidas.",
            merma_an.AMBITO_BEBIDA,
            desde,
            hasta,
            "merma_beb",
        )
    else:
        _render_ambito(
            "Merma general",
            "Productos no clasificados como bebida en el catálogo.",
            merma_an.AMBITO_GENERAL,
            desde,
            hasta,
            "merma_gen",
        )
