"""Exportación de informes para cliente y actividad."""

from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import pandas as pd

from app.core.services.data_service import get_repository
from app.core.services.formatting import formato_fecha, formato_fecha_hora
from app.core.services.kpi_service import resumen_kpis
from app.core.services.settings_service import nombre_hotel_sidebar

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
EXPORTS_DIR = PROJECT_ROOT / "exports"


def _guardar_en_exports(nombre: str, contenido: bytes) -> Path:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ruta = EXPORTS_DIR / nombre
    ruta.write_bytes(contenido)
    return ruta


def exportar_actividad_hoy() -> tuple[bytes, str]:
    repo = get_repository()
    hoy = date.today()
    inicio = datetime.combine(hoy, datetime.min.time())

    filtradas = [a for a in repo.data.actividades if a.fecha_hora >= inicio]
    filtradas.sort(key=lambda a: a.fecha_hora, reverse=True)

    df = pd.DataFrame([
        {
            "Fecha y hora": formato_fecha_hora(a.fecha_hora),
            "Usuario": a.usuario,
            "Acción": a.accion,
            "Detalle": a.detalle,
        }
        for a in filtradas
    ])

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        meta = pd.DataFrame([
            {"Campo": "Hotel", "Valor": nombre_hotel_sidebar()},
            {"Campo": "Fecha exportación", "Valor": formato_fecha_hoy_str()},
            {"Campo": "Registros", "Valor": len(filtradas)},
        ])
        meta.to_excel(writer, sheet_name="Info", index=False)
        df.to_excel(writer, sheet_name="Actividad", index=False)

    contenido = buffer.getvalue()
    nombre = f"actividad_{hoy.isoformat()}.xlsx"
    _guardar_en_exports(nombre, contenido)
    return contenido, nombre


def formato_fecha_hoy_str() -> str:
    return date.today().strftime("%d/%m/%Y")


def exportar_informe_cliente(desde: date, hasta: date, huespedes: int = 30) -> tuple[bytes, str]:
    repo = get_repository()
    hotel = nombre_hotel_sidebar()
    kpis = resumen_kpis(desde, hasta, huespedes)
    evolucion = repo.evolucion_diaria(desde, hasta)

    portada = pd.DataFrame([
        {"Campo": "Establecimiento", "Valor": hotel},
        {"Campo": "Informe", "Valor": "Resumen operativo de desayuno"},
        {"Campo": "Periodo desde", "Valor": formato_fecha(desde)},
        {"Campo": "Periodo hasta", "Valor": formato_fecha(hasta)},
        {"Campo": "Generado", "Valor": datetime.now().strftime("%d/%m/%Y %H:%M")},
        {"Campo": "Coste total", "Valor": kpis["total"]},
        {"Campo": "Coste consumo", "Valor": kpis["consumo"]},
        {"Campo": "Coste merma", "Valor": kpis["merma"]},
        {"Campo": "Coste expiración", "Valor": kpis["expiracion"]},
        {"Campo": "Coste por huésped", "Valor": kpis["coste_huesped"] or 0},
    ])

    evol_df = pd.DataFrame([
        {
            "Fecha": formato_fecha(e["fecha"]),
            "Consumo": e["consumo"],
            "Merma": e["merma"],
            "Expiración": e["expiracion"],
            "Total": e["total"],
        }
        for e in evolucion if e["total"] > 0
    ])

    desayunos = [
        d for d in repo.desayunos_ordenados() if desde <= d.fecha <= hasta
    ]
    desay_df = pd.DataFrame([
        {
            "Fecha": formato_fecha(d.fecha),
            "Huéspedes": d.num_huespedes,
            "Coste": d.coste_total,
            "Registrado por": d.registrado_por,
        }
        for d in desayunos
    ])

    mermas = [m for m in repo.mermas_ordenadas() if desde <= m.fecha <= hasta]
    merma_df = pd.DataFrame([
        {
            "Fecha": formato_fecha(m.fecha),
            "Coste": m.coste_total,
            "Registrado por": m.registrado_por,
        }
        for m in mermas
    ])

    inventario = []
    for p in sorted(repo.data.productos, key=lambda x: x.nombre):
        stock = repo.stock_total_producto(p.id)
        inventario.append({
            "Producto": p.nombre,
            "Unidad": p.unidad.value,
            "Stock": stock,
            "Stock mínimo": p.stock_minimo if p.stock_minimo is not None else "—",
        })
    inv_df = pd.DataFrame(inventario)

    alertas_df = pd.DataFrame([
        {
            "Título": a.titulo,
            "Mensaje": a.mensaje,
            "Tipo": a.tipo.value,
            "Fecha": formato_fecha(a.fecha),
        }
        for a in repo.alertas_activas()
    ])

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        portada.to_excel(writer, sheet_name="Resumen", index=False)
        if not evol_df.empty:
            evol_df.to_excel(writer, sheet_name="Evolución", index=False)
        if not desay_df.empty:
            desay_df.to_excel(writer, sheet_name="Desayunos", index=False)
        if not merma_df.empty:
            merma_df.to_excel(writer, sheet_name="Mermas", index=False)
        inv_df.to_excel(writer, sheet_name="Inventario", index=False)
        if not alertas_df.empty:
            alertas_df.to_excel(writer, sheet_name="Alertas", index=False)

    contenido = buffer.getvalue()
    nombre = f"informe_cliente_{desde.isoformat()}_{hasta.isoformat()}.xlsx"
    _guardar_en_exports(nombre, contenido)
    return contenido, nombre
