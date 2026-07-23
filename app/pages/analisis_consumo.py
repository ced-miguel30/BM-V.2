"""Gestor de consumo — pestañas multi-categoría (Fase 3)."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from app.core.models import OrigenConsumo, TipoServicio
from app.core.services import analitica_consumo_service as analitica
from app.core.services import consumo_service
from app.core.services.data_service import get_repository
from app.core.services.exportacion_semanal_service import exportar_semana_actual, limite_semana
from app.core.services.formatting import formato_fecha
from app.ui.charts import chart_barras_horizontales, chart_lineas_categorias
from app.ui.components import (
    chart_placeholder,
    empty_state,
    metric_card,
    render_sub_tabs,
    section_divider,
)


def _periodo_ui(key_prefix: str) -> tuple[date, date] | None:
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)
    opciones = ["Esta semana", "Este mes", "Rango personalizado"]
    periodo_sel = st.radio(
        "Periodo", opciones, horizontal=True, key=f"{key_prefix}_periodo",
    )
    if periodo_sel == "Esta semana":
        return limite_semana(hoy)[0], hoy
    if periodo_sel == "Este mes":
        return inicio_mes, hoy
    c1, c2 = st.columns(2)
    with c1:
        desde = st.date_input("Desde", value=inicio_mes, key=f"{key_prefix}_desde")
    with c2:
        hasta = st.date_input("Hasta", value=hoy, max_value=hoy, key=f"{key_prefix}_hasta")
    if desde > hasta:
        st.error("La fecha «Desde» no puede ser posterior a «Hasta».")
        return None
    return desde, hasta


def _filtros_comunes(key_prefix: str) -> tuple[date, date, str, str] | None:
    periodo = _periodo_ui(key_prefix)
    if periodo is None:
        return None
    desde, hasta = periodo
    c1, c2 = st.columns(2)
    with c1:
        busqueda = st.text_input("Buscador", value="", key=f"{key_prefix}_busqueda")
    with c2:
        tipo = st.selectbox(
            "Tipo de consumo",
            ["Todos", "Recetas", "Productos y extras", "Bebidas"],
            key=f"{key_prefix}_tipo",
        )
    st.caption(f"Periodo activo: {formato_fecha(desde)} — {formato_fecha(hasta)}")
    return desde, hasta, busqueda, tipo


def _tabla_ranking(filas: list[dict], *, con_tipo: bool = False) -> None:
    if not filas:
        empty_state("Sin consumo registrado en el periodo.", icon="📊")
        return
    rows = []
    for i, f in enumerate(filas, 1):
        row = {
            "#": i,
            "Nombre": f["nombre"],
            "Cantidad": f["cantidad_fmt"],
            "Usos": f["usos"],
            "Coste": f["coste_fmt"],
        }
        if con_tipo:
            row["Tipo"] = f.get("tipo") or f.get("categoria_receta") or "—"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _par_rankings(
    titulo_mas: str,
    titulo_menos: str,
    filas_mas: list[dict],
    filas_menos: list[dict],
    *,
    con_tipo: bool = False,
) -> None:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"##### {titulo_mas}")
        _tabla_ranking(filas_mas, con_tipo=con_tipo)
    with c2:
        st.markdown(f"##### {titulo_menos}")
        _tabla_ranking(filas_menos, con_tipo=con_tipo)


def _boton_exportar() -> None:
    col_btn, _ = st.columns([1, 2])
    with col_btn:
        if st.button(
            "Exportar registro de consumo",
            use_container_width=True,
            key="consumo_exportar_semana",
        ):
            resultado = exportar_semana_actual(
                consumo_service.configuracion_exportacion(), datetime.now(),
            )
            if resultado.ok:
                st.session_state["consumo_export_dl"] = (
                    resultado.ruta.read_bytes(), resultado.nombre_archivo,
                )
                st.success(resultado.mensaje)
            else:
                st.error(resultado.mensaje)
    dl = st.session_state.get("consumo_export_dl")
    if dl:
        contenido, nombre = dl
        st.download_button(
            "Descargar Excel",
            data=contenido,
            file_name=nombre,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="consumo_descargar_excel",
        )


def _render_resumen(desde: date, hasta: date, busqueda: str, tipo: str) -> None:
    repo = get_repository()
    res = analitica.resumen_consumo(desde, hasta)
    var = res["variacion_pct"]
    var_txt = f"{var:+.1f}% vs periodo anterior" if var is not None else "Sin periodo anterior"

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        metric_card("Eventos de consumo", str(res["n_eventos_producto"]), "Líneas de detalle")
    with c2:
        metric_card("Coste de consumo", repo.formato_precio(res["coste_consumo"]), var_txt)
    with c3:
        metric_card("Registros", str(res["n_registros"]), "Todos los servicios")
    with c4:
        metric_card(
            "Mayor consumo",
            res["categoria_mayor"],
            repo.formato_precio(res["categoria_mayor_importe"]),
        )
    with c5:
        metric_card("Variación", var_txt if var is not None else "—", "Coste general")

    section_divider()
    dist = [
        {"categoria": k, "importe": v, "porcentaje": 0.0}
        for k, v in res["por_categoria"].items()
    ]
    total = res["coste_consumo"] or 1.0
    for d in dist:
        d["porcentaje"] = round((d["importe"] / total) * 100, 1) if res["coste_consumo"] else 0
    st.markdown("##### Comparación de consumo por categoría")
    if any(d["importe"] > 0 for d in dist):
        st.altair_chart(chart_barras_horizontales(dist), use_container_width=True)
    else:
        chart_placeholder("Sin consumo en el periodo.")

    section_divider()
    kw = busqueda or None
    if tipo in ("Todos", "Productos y extras"):
        _par_rankings(
            "Productos más consumidos (top 5)",
            "Productos menos consumidos (top 5)",
            consumo_service.ranking_analitico_productos(
                desde, hasta, limite=5, busqueda=kw, solo_consumo_bebida=False,
            ),
            consumo_service.ranking_analitico_productos(
                desde, hasta, limite=5, busqueda=kw, solo_consumo_bebida=False, ascendente=True,
            ),
            con_tipo=True,
        )
    if tipo in ("Todos", "Recetas"):
        _par_rankings(
            "Recetas más consumidas (top 5)",
            "Recetas menos consumidas (top 5)",
            consumo_service.ranking_analitico_recetas(desde, hasta, limite=5, busqueda=kw),
            consumo_service.ranking_analitico_recetas(
                desde, hasta, limite=5, busqueda=kw, ascendente=True,
            ),
        )


def _render_desayuno(desde: date, hasta: date, busqueda: str, tipo: str) -> None:
    repo = get_repository()
    d = analitica.desglose_desayuno(desde, hasta)
    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("Desayuno", repo.formato_precio(d.desayuno), "Sin bebidas")
    with c2:
        metric_card("Bebidas en desayuno", repo.formato_precio(d.bebida_en_desayuno), "")
    with c3:
        metric_card("Desayuno total", repo.formato_precio(d.desayuno_total), "")
    if d.sin_desglose_historico > 0:
        st.warning(
            f"Sin desglose histórico: {repo.formato_precio(d.sin_desglose_historico)}"
        )

    sub = render_sub_tabs(
        ["Recetas", "Extras", "Bebidas en desayuno"], key="consumo_desayuno_sub",
    )
    kw = busqueda or None
    ts = TipoServicio.DESAYUNO.value

    if sub == "Recetas" and tipo in ("Todos", "Recetas"):
        _par_rankings(
            "Recetas más consumidas",
            "Recetas menos consumidas",
            consumo_service.ranking_analitico_recetas(
                desde, hasta, tipo_servicio=ts, busqueda=kw, limite=15,
            ),
            consumo_service.ranking_analitico_recetas(
                desde, hasta, tipo_servicio=ts, busqueda=kw, limite=15, ascendente=True,
            ),
        )
    elif sub == "Extras" and tipo in ("Todos", "Productos y extras"):
        st.caption("Productos sueltos y extras de receta no bebida (sin ingredientes base).")
        extras_tipos = [
            OrigenConsumo.PRODUCTO_DIRECTO.value,
            OrigenConsumo.EXTRA_RECETA.value,
        ]
        _par_rankings(
            "Extras más consumidos",
            "Extras menos consumidos",
            consumo_service.ranking_analitico_productos(
                desde, hasta, tipo_servicio=ts, tipos_elemento=extras_tipos,
                solo_consumo_bebida=False, busqueda=kw, limite=15,
            ),
            consumo_service.ranking_analitico_productos(
                desde, hasta, tipo_servicio=ts, tipos_elemento=extras_tipos,
                solo_consumo_bebida=False, busqueda=kw, limite=15, ascendente=True,
            ),
            con_tipo=True,
        )
    elif sub == "Bebidas en desayuno" and tipo in ("Todos", "Bebidas"):
        st.caption("Directas, ingredientes bebida y recetas de categoría Bebidas.")
        _par_rankings(
            "Bebidas más consumidas en desayuno",
            "Bebidas menos consumidas en desayuno",
            consumo_service.ranking_analitico_productos(
                desde, hasta, bucket=analitica.BUCKET_BEBIDA_EN_DESAYUNO,
                busqueda=kw, limite=15,
            ),
            consumo_service.ranking_analitico_productos(
                desde, hasta, bucket=analitica.BUCKET_BEBIDA_EN_DESAYUNO,
                busqueda=kw, limite=15, ascendente=True,
            ),
            con_tipo=True,
        )
        _par_rankings(
            "Recetas de bebida más usadas",
            "Recetas de bebida menos usadas",
            consumo_service.ranking_analitico_recetas(
                desde, hasta, tipo_servicio=ts, categoria_receta="bebidas",
                busqueda=kw, limite=10,
            ),
            consumo_service.ranking_analitico_recetas(
                desde, hasta, tipo_servicio=ts, categoria_receta="bebidas",
                busqueda=kw, limite=10, ascendente=True,
            ),
        )
    else:
        empty_state("Nada que mostrar con el filtro de tipo actual.", icon="🔍")


def _render_servicio(
    etiqueta: str,
    tipo_servicio: str,
    desde: date,
    hasta: date,
    busqueda: str,
    tipo: str,
) -> None:
    sub = render_sub_tabs(
        ["Recetas", "Productos y extras", "Bebidas"],
        key=f"consumo_{tipo_servicio}_sub",
    )
    kw = busqueda or None
    bucket_bebida = {
        TipoServicio.COMIDA.value: analitica.BUCKET_BEBIDA_EN_COMIDA,
        TipoServicio.CENA.value: analitica.BUCKET_BEBIDA_EN_CENA,
    }.get(tipo_servicio)

    if sub == "Recetas" and tipo in ("Todos", "Recetas"):
        _par_rankings(
            f"Recetas más consumidas ({etiqueta})",
            f"Recetas menos consumidas ({etiqueta})",
            consumo_service.ranking_analitico_recetas(
                desde, hasta, tipo_servicio=tipo_servicio, busqueda=kw, limite=15,
            ),
            consumo_service.ranking_analitico_recetas(
                desde, hasta, tipo_servicio=tipo_servicio, busqueda=kw,
                limite=15, ascendente=True,
            ),
        )
    elif sub == "Productos y extras" and tipo in ("Todos", "Productos y extras"):
        tipos_el = [
            OrigenConsumo.PRODUCTO_DIRECTO.value,
            OrigenConsumo.EXTRA_RECETA.value,
        ]
        _par_rankings(
            "Productos y extras más consumidos",
            "Productos y extras menos consumidos",
            consumo_service.ranking_analitico_productos(
                desde, hasta, tipo_servicio=tipo_servicio, tipos_elemento=tipos_el,
                solo_consumo_bebida=False, busqueda=kw, limite=15,
            ),
            consumo_service.ranking_analitico_productos(
                desde, hasta, tipo_servicio=tipo_servicio, tipos_elemento=tipos_el,
                solo_consumo_bebida=False, busqueda=kw, limite=15, ascendente=True,
            ),
            con_tipo=True,
        )
    elif sub == "Bebidas" and tipo in ("Todos", "Bebidas") and bucket_bebida:
        _par_rankings(
            f"Bebidas en {etiqueta.lower()} (más)",
            f"Bebidas en {etiqueta.lower()} (menos)",
            consumo_service.ranking_analitico_productos(
                desde, hasta, bucket=bucket_bebida, busqueda=kw, limite=15,
            ),
            consumo_service.ranking_analitico_productos(
                desde, hasta, bucket=bucket_bebida, busqueda=kw, limite=15, ascendente=True,
            ),
            con_tipo=True,
        )
    else:
        empty_state("Nada que mostrar con el filtro de tipo actual.", icon="🔍")


def _render_bebidas(desde: date, hasta: date, busqueda: str, tipo: str) -> None:
    if tipo not in ("Todos", "Bebidas"):
        empty_state("Active el filtro «Bebidas» o «Todos».", icon="🔍")
        return
    sub = render_sub_tabs(
        ["Todas", "Desayuno", "Comida", "Cena", "Registro independiente"],
        key="consumo_bebidas_origen",
    )
    kw = busqueda or None
    bucket_map = {
        "Desayuno": analitica.BUCKET_BEBIDA_EN_DESAYUNO,
        "Comida": analitica.BUCKET_BEBIDA_EN_COMIDA,
        "Cena": analitica.BUCKET_BEBIDA_EN_CENA,
        "Registro independiente": analitica.BUCKET_BEBIDA_INDEPENDIENTE,
    }
    if sub == "Todas":
        st.caption("Análisis transversal: no suma como categoría del Dashboard.")
        coste = sum(
            analitica.coste_bucket_bebida(b, desde, hasta)
            for b in bucket_map.values()
        )
        metric_card("Coste total bebidas (transversal)", get_repository().formato_precio(coste), "")
        _par_rankings(
            "Bebidas más consumidas",
            "Bebidas menos consumidas",
            consumo_service.ranking_analitico_productos(
                desde, hasta, solo_consumo_bebida=True, busqueda=kw, limite=15,
            ),
            consumo_service.ranking_analitico_productos(
                desde, hasta, solo_consumo_bebida=True, busqueda=kw, limite=15, ascendente=True,
            ),
            con_tipo=True,
        )
        dist = [
            {
                "categoria": nombre,
                "importe": analitica.coste_bucket_bebida(bucket, desde, hasta),
                "porcentaje": 0.0,
            }
            for nombre, bucket in bucket_map.items()
        ]
        total = sum(d["importe"] for d in dist) or 1.0
        for d in dist:
            d["porcentaje"] = round((d["importe"] / total) * 100, 1)
        st.markdown("##### Distribución por origen")
        if any(d["importe"] > 0 for d in dist):
            st.altair_chart(chart_barras_horizontales(dist), use_container_width=True)
        else:
            chart_placeholder("Sin bebidas en el periodo.")
    else:
        bucket = bucket_map[sub]
        _par_rankings(
            f"Más consumidas — {sub}",
            f"Menos consumidas — {sub}",
            consumo_service.ranking_analitico_productos(
                desde, hasta, bucket=bucket, busqueda=kw, limite=15,
            ),
            consumo_service.ranking_analitico_productos(
                desde, hasta, bucket=bucket, busqueda=kw, limite=15, ascendente=True,
            ),
            con_tipo=True,
        )


def _grafico_evolucion(desde: date, hasta: date) -> None:
    from app.core.services import dashboard_service as dash

    evo = dash.evolucion_por_categoria(desde, hasta, modo_desayuno=False)
    st.markdown("##### Evolución del consumo en el tiempo")
    if any(sum(v for k, v in row.items() if k != "fecha") > 0 for row in evo):
        st.altair_chart(
            chart_lineas_categorias(
                evo, ["Desayuno", "Comida", "Cena", "Bebidas"],
                titulo="Evolución del coste de consumo",
            ),
            use_container_width=True,
        )
    else:
        chart_placeholder("Sin evolución en el periodo.")


def render_gestor_consumo() -> None:
    st.markdown("#### Gestor de consumo")
    st.caption(
        "Análisis por servicio y origen. Los rankings «menos» solo incluyen "
        "elementos con consumo > 0. Las cantidades se agregan por unidad normalizada."
    )

    filtros = _filtros_comunes("consumo")
    if filtros is None:
        return
    desde, hasta, busqueda, tipo = filtros

    section_divider()
    pestana = render_sub_tabs(
        ["Resumen", "Desayuno", "Comida", "Cena", "Bebidas"],
        key="consumo_pestana",
    )

    if pestana == "Resumen":
        _render_resumen(desde, hasta, busqueda, tipo)
        section_divider()
        _grafico_evolucion(desde, hasta)
        top5 = consumo_service.ranking_analitico_productos(desde, hasta, limite=5)
        st.markdown("##### Top 5 elementos más consumidos (por coste)")
        _tabla_ranking(top5, con_tipo=True)
    elif pestana == "Desayuno":
        _render_desayuno(desde, hasta, busqueda, tipo)
    elif pestana == "Comida":
        _render_servicio("Comida", TipoServicio.COMIDA.value, desde, hasta, busqueda, tipo)
    elif pestana == "Cena":
        _render_servicio("Cena", TipoServicio.CENA.value, desde, hasta, busqueda, tipo)
    else:
        _render_bebidas(desde, hasta, busqueda, tipo)

    section_divider()
    st.markdown("##### Exportar registro de consumo")
    st.caption(
        "Exporta el detalle histórico (desayuno + comida + cena + bebidas), "
        "no solo los rankings, desde el lunes de la semana actual."
    )
    _boton_exportar()
