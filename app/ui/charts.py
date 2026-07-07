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
