"""Gestor de merma — agrupación por tipo_servicio_snapshot."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app.core.models import MotivoMerma, OrigenServicioMerma, TURNO_MERMA_LABEL, TurnoMerma
from app.core.services import merma_analisis_service as merma_an
from app.core.services.data_service import get_repository
from app.core.services.formatting import formato_fecha
from app.ui.charts import chart_barras_horizontales, chart_lineas_categorias
from app.ui.components import (
    chart_placeholder,
    empty_state,
    metric_card,
    periodo_filtro_analisis,
    render_explicacion_calculo,
    render_sub_tabs,
    section_divider,
)

_PESTANAS = [
    "Resumen",
    "Desayuno",
    "Comida",
    "Cena",
    "Bebidas",
    "Almacén / General",
    "Sin desglose histórico",
]

_PESTANA_A_AMBITO = {
    "Desayuno": OrigenServicioMerma.DESAYUNO.value,
    "Comida": OrigenServicioMerma.COMIDA.value,
    "Cena": OrigenServicioMerma.CENA.value,
    "Bebidas": OrigenServicioMerma.BEBIDAS.value,
    "Almacén / General": OrigenServicioMerma.GENERAL.value,
    "Sin desglose histórico": merma_an.BUCKET_SIN_DESGLOSE,
}

_SIN_TURNO = "__sin_turno__"


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


def _filtros_merma_extra(key: str) -> tuple[list[str] | None, list[str] | None]:
    """Turno y responsable. None = sin filtrar."""
    repo = get_repository()
    etiquetas_turno = [TURNO_MERMA_LABEL[t] for t in TurnoMerma] + ["Sin turno (histórico)"]
    valor_turno = {TURNO_MERMA_LABEL[t]: t.value for t in TurnoMerma}
    valor_turno["Sin turno (histórico)"] = _SIN_TURNO

    c1, c2 = st.columns(2)
    with c1:
        turnos_sel = st.multiselect(
            "Turno",
            etiquetas_turno,
            default=etiquetas_turno,
            key=f"{key}_turnos",
        )
    with c2:
        responsables = [r for r in repo.data.responsables_merma if r.activo] or list(
            repo.data.responsables_merma
        )
        opts_resp = ["(Sin responsable histórico)"] + [r.nombre for r in responsables]
        id_por_nombre = {r.nombre: r.id for r in responsables}
        resp_sel = st.multiselect(
            "Responsable",
            opts_resp,
            default=opts_resp,
            key=f"{key}_responsables",
        )

    turnos: list[str] | None
    if not turnos_sel or len(turnos_sel) == len(etiquetas_turno):
        turnos = None
    else:
        turnos = []
        for e in turnos_sel:
            v = valor_turno[e]
            turnos.append("" if v == _SIN_TURNO else v)

    responsables_ids: list[str] | None
    if not resp_sel or len(resp_sel) == len(opts_resp):
        responsables_ids = None
    else:
        responsables_ids = []
        for nombre in resp_sel:
            if nombre == "(Sin responsable histórico)":
                responsables_ids.append("")
            else:
                responsables_ids.append(id_por_nombre.get(nombre, ""))

    return turnos, responsables_ids


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
    turnos, responsables = _filtros_merma_extra(key)
    busqueda = st.text_input("Buscador producto/receta", value="", key=f"{key}_busqueda")
    mas = merma_an.ranking_productos_merma(
        desde,
        hasta,
        ambito=ambito,
        motivos=motivos,
        turnos=turnos,
        responsables=responsables,
        busqueda=busqueda or None,
        limite=15,
    )
    menos = merma_an.ranking_productos_merma(
        desde,
        hasta,
        ambito=ambito,
        motivos=motivos,
        turnos=turnos,
        responsables=responsables,
        busqueda=busqueda or None,
        ascendente=True,
        limite=15,
    )
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Más merma (por coste)")
        _tabla(mas, ["nombre", "cantidad_fmt", "usos", "motivos", "servicios", "coste_fmt"])
    with c2:
        st.markdown("##### Menos merma (uso > 0)")
        _tabla(menos, ["nombre", "cantidad_fmt", "usos", "motivos", "servicios", "coste_fmt"])


def _render_resumen(desde: date, hasta: date) -> None:
    res = merma_an.resumen_merma(desde, hasta)
    por = res["por_grupo"]
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        metric_card("Merma total", res["total_fmt"], f"{res['n_registros']} registros")
    with c2:
        metric_card("Merma (sin expiración)", res["merma_fmt"], "")
    with c3:
        metric_card("Expiración", res["expiracion_fmt"], "")
    with c4:
        metric_card(
            "Suma por servicio",
            res["suma_grupos_fmt"],
            "Debe coincidir con el total",
        )
    with c5:
        sin = por.get(merma_an.BUCKET_SIN_DESGLOSE, 0.0)
        metric_card(
            "Sin desglose histórico",
            get_repository().formato_precio(sin),
            "Registros antiguos",
        )

    st.caption(
        "La merma se agrupa por el servicio guardado al registrar "
        "(`tipo_servicio_snapshot`). Los registros antiguos sin ese campo "
        "aparecen en «Sin desglose histórico»."
    )

    section_divider()
    st.markdown("##### Por servicio / área")
    dist = merma_an.distribucion_servicio(desde, hasta)
    if any(d["importe"] > 0 for d in dist):
        st.altair_chart(
            chart_barras_horizontales(dist, "Servicio"),
            use_container_width=True,
        )
    else:
        chart_placeholder("Sin merma en el periodo.")

    section_divider()
    st.markdown("##### Por motivo")
    motivos = merma_an.coste_por_motivo(desde, hasta)
    if any(m["importe"] > 0 for m in motivos):
        st.altair_chart(
            chart_barras_horizontales(motivos, "Motivo"),
            use_container_width=True,
        )
    else:
        chart_placeholder("Sin datos de motivo.")

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
        "Agrupación por el servicio indicado al registrar la merma. "
        "«Sin desglose histórico» son líneas antiguas sin `tipo_servicio_snapshot`."
    )
    render_explicacion_calculo()

    periodo = periodo_filtro_analisis("merma")
    if periodo is None:
        return
    desde, hasta = periodo
    st.caption(f"Periodo: {formato_fecha(desde)} — {formato_fecha(hasta)}")

    hist = merma_an.resumen_historico_merma(desde, hasta)
    if hist["hay_aviso"]:
        st.warning(
            f"Histórico incompleto en merma: {hist['n_sin_servicio']} sin servicio, "
            f"{hist['n_sin_turno']} sin turno, {hist['n_sin_responsable']} sin responsable "
            f"(de {hist['n_lineas']} líneas)."
        )

    pestana = render_sub_tabs(_PESTANAS, key="merma_pestana")
    section_divider()

    if pestana == "Resumen":
        _render_resumen(desde, hasta)
    else:
        ambito = _PESTANA_A_AMBITO[pestana]
        _render_ambito(
            pestana,
            f"Líneas con servicio «{pestana}».",
            ambito,
            desde,
            hasta,
            f"merma_{ambito}",
        )
