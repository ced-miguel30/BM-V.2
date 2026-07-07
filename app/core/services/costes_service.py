"""Servicio de análisis comparativo de costes."""

from datetime import date
from io import BytesIO

import pandas as pd

from app.core.services.data_service import get_repository
from app.core.services.excel_format import formatear_libro
from app.core.services.formatting import formato_fecha


CATEGORIAS = ["Consumo", "Merma", "Expiración"]


def _costes_categoria(repo, inicio: date, fin: date, categorias: list[str]) -> dict[str, float]:
    resultado = {
        "Consumo": 0.0,
        "Merma": 0.0,
        "Expiración": 0.0,
    }
    if "Consumo" in categorias:
        resultado["Consumo"] = repo.coste_consumo_periodo(inicio, fin)
    if "Merma" in categorias:
        resultado["Merma"] = repo.coste_merma_periodo(inicio, fin)
    if "Expiración" in categorias:
        resultado["Expiración"] = repo.coste_expiracion_periodo(inicio, fin)
    return {k: v for k, v in resultado.items() if k in categorias}


def resumen_periodo(inicio: date, fin: date, categorias: list[str]) -> dict:
    repo = get_repository()
    costes = _costes_categoria(repo, inicio, fin, categorias)
    total = sum(costes.values())
    return {
        "costes": costes,
        "total": total,
        "total_fmt": repo.formato_precio(total),
        "desde": inicio,
        "hasta": fin,
    }


def comparar_periodos(
    a_desde: date,
    a_hasta: date,
    b_desde: date,
    b_hasta: date,
    categorias: list[str],
) -> dict:
    repo = get_repository()
    periodo_a = resumen_periodo(a_desde, a_hasta, categorias)
    periodo_b = resumen_periodo(b_desde, b_hasta, categorias)

    variaciones = {}
    for cat in categorias:
        va = periodo_a["costes"].get(cat, 0)
        vb = periodo_b["costes"].get(cat, 0)
        if vb > 0:
            pct = ((va - vb) / vb) * 100
            variaciones[cat] = round(pct, 1)
        elif va > 0:
            variaciones[cat] = 100.0
        else:
            variaciones[cat] = 0.0

    ta, tb = periodo_a["total"], periodo_b["total"]
    if tb > 0:
        var_total = round(((ta - tb) / tb) * 100, 1)
    elif ta > 0:
        var_total = 100.0
    else:
        var_total = 0.0

    return {
        "periodo_a": periodo_a,
        "periodo_b": periodo_b,
        "variaciones": variaciones,
        "variacion_total": var_total,
        "variacion_total_fmt": f"{var_total:+.1f}%",
    }


def datos_grafico_comparacion(comparacion: dict) -> list[dict]:
    filas = []
    for cat, valor_a in comparacion["periodo_a"]["costes"].items():
        filas.append({"periodo": "Periodo A", "categoria": cat, "coste": valor_a})
    for cat, valor_b in comparacion["periodo_b"]["costes"].items():
        filas.append({"periodo": "Periodo B", "categoria": cat, "coste": valor_b})
    return filas


def exportar_costes_excel(
    a_desde: date,
    a_hasta: date,
    b_desde: date,
    b_hasta: date,
    categorias: list[str],
) -> bytes:
    comparacion = comparar_periodos(a_desde, a_hasta, b_desde, b_hasta, categorias)
    pa = comparacion["periodo_a"]
    pb = comparacion["periodo_b"]

    resumen_df = pd.DataFrame([
        {
            "Categoría": cat,
            "Periodo A": pa["costes"].get(cat, 0),
            "Periodo B": pb["costes"].get(cat, 0),
            "Variación %": comparacion["variaciones"].get(cat, 0),
        }
        for cat in categorias
    ])
    resumen_df.loc[len(resumen_df)] = {
        "Categoría": "TOTAL",
        "Periodo A": pa["total"],
        "Periodo B": pb["total"],
        "Variación %": comparacion["variacion_total"],
    }

    meta_df = pd.DataFrame([
        {"Campo": "Periodo A desde", "Valor": formato_fecha(a_desde)},
        {"Campo": "Periodo A hasta", "Valor": formato_fecha(a_hasta)},
        {"Campo": "Periodo B desde", "Valor": formato_fecha(b_desde)},
        {"Campo": "Periodo B hasta", "Valor": formato_fecha(b_hasta)},
        {"Campo": "Categorías", "Valor": ", ".join(categorias)},
    ])

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        meta_df.to_excel(writer, sheet_name="Periodos", index=False)
        resumen_df.to_excel(writer, sheet_name="Comparación", index=False)
        formatear_libro(writer, [
            ("Periodos", "TablaCostesPeriodos", False),
            ("Comparación", "TablaCostesComparacion", True),
        ])

    return buffer.getvalue()
