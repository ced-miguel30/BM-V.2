"""Servicio de KPIs — resúmenes y exportación."""

from datetime import date
from io import BytesIO

import pandas as pd

from app.core.repositories.data_repository import DataRepository
from app.core.services.data_service import get_repository
from app.core.services.excel_format import formatear_libro
from app.core.services.formatting import formato_fecha


def resumen_kpis(inicio: date, fin: date, huespedes: int) -> dict:
    repo = get_repository()
    consumo = repo.coste_consumo_periodo(inicio, fin)
    merma = repo.coste_merma_periodo(inicio, fin)
    expiracion = repo.coste_expiracion_periodo(inicio, fin)
    total = consumo + merma + expiracion
    coste_huesped = total / huespedes if huespedes > 0 else None

    return {
        "consumo": consumo,
        "merma": merma,
        "expiracion": expiracion,
        "total": total,
        "coste_huesped": coste_huesped,
        "n_expiracion": repo.registros_expiracion_periodo(inicio, fin),
        "consumo_fmt": repo.formato_precio(consumo),
        "merma_fmt": repo.formato_precio(merma),
        "expiracion_fmt": repo.formato_precio(expiracion),
        "total_fmt": repo.formato_precio(total),
        "coste_huesped_fmt": repo.formato_precio(coste_huesped) if coste_huesped else "—",
    }


def exportar_kpis_excel(inicio: date, fin: date, huespedes: int) -> bytes:
    repo: DataRepository = get_repository()
    kpis = resumen_kpis(inicio, fin, huespedes)
    evolucion = repo.evolucion_diaria(inicio, fin)

    resumen_df = pd.DataFrame([
        {"Indicador": "Periodo desde", "Valor": formato_fecha(inicio)},
        {"Indicador": "Periodo hasta", "Valor": formato_fecha(fin)},
        {"Indicador": "Huéspedes", "Valor": huespedes},
        {"Indicador": "Coste consumo", "Valor": kpis["consumo"]},
        {"Indicador": "Coste merma", "Valor": kpis["merma"]},
        {"Indicador": "Coste expiración", "Valor": kpis["expiracion"]},
        {"Indicador": "Coste total", "Valor": kpis["total"]},
        {"Indicador": "Coste por huésped", "Valor": kpis["coste_huesped"] or 0},
        {"Indicador": "Registros expiración", "Valor": kpis["n_expiracion"]},
    ])

    evol_df = pd.DataFrame([
        {
            "Fecha": formato_fecha(e["fecha"]),
            "Consumo": e["consumo"],
            "Merma": e["merma"],
            "Expiración": e["expiracion"],
            "Total": e["total"],
        }
        for e in evolucion
    ])

    top_df = pd.DataFrame(repo.top_productos_costosos_periodo(inicio, fin, 10))

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        resumen_df.to_excel(writer, sheet_name="Resumen", index=False)
        evol_df.to_excel(writer, sheet_name="Evolución", index=False)
        if not top_df.empty:
            top_df.to_excel(writer, sheet_name="Top productos", index=False)
        formatear_libro(writer, [
            ("Resumen", "TablaKPIResumen", True),
            ("Evolución", "TablaKPIEvolucion", True),
            ("Top productos", "TablaKPITop", True),
        ])

    return buffer.getvalue()
