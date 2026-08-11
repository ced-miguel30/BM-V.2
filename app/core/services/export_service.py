"""Exportación de informes para cliente y actividad."""

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import os

import pandas as pd

from app.core.services.data_service import get_repository
from app.core.services.excel_format import formatear_libro
from app.core.services.formatting import formato_fecha, formato_fecha_hora
from app.core.services.kpi_service import resumen_kpis
from app.core.services.settings_service import nombre_hotel_sidebar
from app.core.storage.instance_paths import assert_hotel_not_writing_repo_exports, get_exports_root


def _exports_dir() -> Path:
    return get_exports_root(for_write=True)


def __getattr__(name: str):
    if name == "EXPORTS_DIR":
        return get_exports_root(for_write=False)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _guardar_en_exports(nombre: str, contenido: bytes) -> Path:
    exports = _exports_dir()
    exports.mkdir(parents=True, exist_ok=True)
    assert_hotel_not_writing_repo_exports(exports)
    safe = Path(nombre).name
    ruta = exports / safe
    if ruta.exists():
        stem, suf = ruta.stem, ruta.suffix
        n = 1
        while True:
            cand = exports / f"{stem}_{n}{suf}"
            if not cand.exists():
                ruta = cand
                break
            n += 1
    tmp = ruta.with_suffix(ruta.suffix + f".tmp.{os.getpid()}")
    tmp.write_bytes(contenido)
    os.replace(str(tmp), str(ruta))
    return ruta


def exportar_actividad_hoy() -> tuple[bytes, str]:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.ACCEDER_CONFIGURACION, deny_terminal=True)

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
        formatear_libro(writer, [
            ("Info", "TablaActividadInfo", False),
            ("Actividad", "TablaActividad", True),
        ])

    contenido = buffer.getvalue()
    nombre = f"actividad_{hoy.isoformat()}.xlsx"
    _guardar_en_exports(nombre, contenido)
    return contenido, nombre


def formato_fecha_hoy_str() -> str:
    return date.today().strftime("%d/%m/%Y")


def exportar_informe_cliente(desde: date, hasta: date, huespedes: int = 30) -> tuple[bytes, str]:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES, deny_terminal=True)

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

    recetas_desayuno_filas = []
    productos_desayuno_filas = []
    for d in desayunos:
        for rr in d.registros_recetas:
            extras_txt = ", ".join(
                f"{repo.get_nombre_producto(e.producto_id)} {e.cantidad:g}"
                for e in rr.extras
            ) or "—"
            omisiones_txt = ", ".join(
                repo.get_nombre_producto(o.producto_id)
                for o in rr.omisiones
            ) or "—"
            recetas_desayuno_filas.append({
                "Fecha": formato_fecha(d.fecha),
                "Receta": rr.nombre_receta,
                "Porciones": rr.porciones,
                "Extras": extras_txt,
                "Sin ingrediente": omisiones_txt,
            })
        for ln in d.lineas:
            producto = repo.get_producto(ln.producto_id)
            productos_desayuno_filas.append({
                "Fecha": formato_fecha(d.fecha),
                "Producto": repo.get_nombre_producto(ln.producto_id),
                "Cantidad": ln.cantidad,
                "Unidad": producto.unidad.value if producto else "",
                "Coste": ln.coste,
                "Notas": "[extra]" if ln.es_extra else "",
            })

    recetas_desayuno_df = pd.DataFrame(recetas_desayuno_filas)
    productos_desayuno_df = pd.DataFrame(productos_desayuno_filas)

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
        if not recetas_desayuno_df.empty:
            recetas_desayuno_df.to_excel(writer, sheet_name="Recetas desayuno", index=False)
        if not productos_desayuno_df.empty:
            productos_desayuno_df.to_excel(writer, sheet_name="Productos desayuno", index=False)
        if not merma_df.empty:
            merma_df.to_excel(writer, sheet_name="Mermas", index=False)
        inv_df.to_excel(writer, sheet_name="Inventario", index=False)
        if not alertas_df.empty:
            alertas_df.to_excel(writer, sheet_name="Alertas", index=False)
        formatear_libro(writer, [
            ("Resumen", "TablaInformeResumen", False),
            ("Evolución", "TablaInformeEvolucion", True),
            ("Desayunos", "TablaInformeDesayunos", True),
            ("Recetas desayuno", "TablaInformeRecetasDesayuno", True),
            ("Productos desayuno", "TablaInformeProductosDesayuno", True),
            ("Mermas", "TablaInformeMermas", True),
            ("Inventario", "TablaInformeInventario", True),
            ("Alertas", "TablaInformeAlertas", True),
        ])

    contenido = buffer.getvalue()
    nombre = f"informe_cliente_{desde.isoformat()}_{hasta.isoformat()}.xlsx"
    _guardar_en_exports(nombre, contenido)
    return contenido, nombre
