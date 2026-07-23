"""Gráficos Altair reutilizables."""

from datetime import date

import altair as alt
import pandas as pd


def _df_evolucion(datos: list[dict]) -> pd.DataFrame:
    filas = []
    for item in datos:
        f = item["fecha"]
        fecha_str = f.strftime("%d/%m") if isinstance(f, date) else str(f)
        for categoria, valor in [
            ("Consumo", item.get("consumo", 0)),
            ("Merma", item.get("merma", 0)),
            ("Expiración", item.get("expiracion", 0)),
        ]:
            filas.append({"fecha": fecha_str, "categoria": categoria, "coste": valor})
    return pd.DataFrame(filas)


def chart_evolucion_costes(datos: list[dict], titulo: str = "Evolución de costes") -> alt.Chart:
    df = _df_evolucion(datos)
    if df.empty or df["coste"].sum() == 0:
        return alt.Chart(pd.DataFrame({"msg": ["Sin datos en el periodo"]})).mark_text().encode(text="msg")

    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("fecha:N", title="Fecha", sort=None),
            y=alt.Y("coste:Q", title="Coste (€)", stack="zero"),
            color=alt.Color(
                "categoria:N",
                title="Tipo",
                scale=alt.Scale(
                    domain=["Consumo", "Merma", "Expiración"],
                    range=["#3A6EA5", "#B8860B", "#C0392B"],
                ),
            ),
            tooltip=["fecha", "categoria", alt.Tooltip("coste:Q", format=".2f")],
        )
        .properties(title=titulo, height=320)
        .configure_axis(labelFontSize=11, titleFontSize=12)
    )


def chart_comparacion_periodos(datos: list[dict], titulo: str = "Comparación de costes") -> alt.Chart:
    df = pd.DataFrame(datos)
    if df.empty or df["coste"].sum() == 0:
        return alt.Chart(pd.DataFrame({"msg": ["Sin datos"]})).mark_text().encode(text="msg")

    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("categoria:N", title="Categoría"),
            y=alt.Y("coste:Q", title="Coste (€)"),
            color=alt.Color("periodo:N", title="Periodo"),
            xOffset="periodo:N",
            tooltip=["periodo", "categoria", alt.Tooltip("coste:Q", format=".2f")],
        )
        .properties(title=titulo, height=300)
    )


def chart_lineas_categorias(
    datos: list[dict],
    series: list[str],
    titulo: str = "Evolución del coste por categoría",
) -> alt.Chart:
    """Líneas por categoría a partir de filas {fecha, Serie1, Serie2, ...}."""
    filas = []
    orden_fechas: list[str] = []
    for item in datos:
        f = item["fecha"]
        fecha_str = f.strftime("%d/%m") if isinstance(f, date) else str(f)
        if fecha_str not in orden_fechas:
            orden_fechas.append(fecha_str)
        for serie in series:
            filas.append({
                "fecha": fecha_str,
                "categoria": serie,
                "coste": float(item.get(serie, 0) or 0),
            })
    df = pd.DataFrame(filas)
    if df.empty or df["coste"].sum() == 0:
        return alt.Chart(pd.DataFrame({"msg": ["Sin datos en el periodo"]})).mark_text().encode(text="msg")

    return (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X("fecha:N", title="Fecha", sort=orden_fechas),
            y=alt.Y("coste:Q", title="Coste (€)", scale=alt.Scale(zero=True)),
            color=alt.Color("categoria:N", title="Categoría"),
            tooltip=["fecha", "categoria", alt.Tooltip("coste:Q", format=".2f")],
        )
        .properties(title=titulo, height=320)
        .configure_axis(labelFontSize=11, titleFontSize=12)
    )


def chart_barras_horizontales(
    datos: list[dict],
    titulo: str = "Distribución del coste",
) -> alt.Chart:
    """Barras horizontales: datos con categoria, importe, porcentaje."""
    df = pd.DataFrame(datos)
    if df.empty or df["importe"].sum() == 0:
        return alt.Chart(pd.DataFrame({"msg": ["Sin datos"]})).mark_text().encode(text="msg")

    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            y=alt.Y("categoria:N", title=None, sort="-x"),
            x=alt.X("importe:Q", title="Coste (€)"),
            tooltip=[
                "categoria",
                alt.Tooltip("importe:Q", format=".2f"),
                alt.Tooltip("porcentaje:Q", title="%"),
            ],
            color=alt.value("#3A6EA5"),
        )
        .properties(title=titulo, height=280)
    )


def chart_consumo_merma_naturaleza(
    datos: list[dict],
    titulo: str = "Consumo frente a merma",
) -> alt.Chart:
    """Consumo por servicio + merma/expiración globales (sin atribución inventada)."""
    df = pd.DataFrame(datos)
    if df.empty or df["importe"].sum() == 0:
        return alt.Chart(pd.DataFrame({"msg": ["Sin datos"]})).mark_text().encode(text="msg")

    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("categoria:N", title=None, sort=None),
            y=alt.Y("importe:Q", title="Coste (€)"),
            color=alt.Color(
                "tipo:N",
                title="Naturaleza",
                scale=alt.Scale(
                    domain=["Consumo", "Merma", "Expiración"],
                    range=["#3A6EA5", "#B8860B", "#C0392B"],
                ),
            ),
            tooltip=["categoria", "tipo", alt.Tooltip("importe:Q", format=".2f")],
        )
        .properties(title=titulo, height=300)
    )
