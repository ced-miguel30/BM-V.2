"""Exportación y archivo semanal del historial de compras."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd

from app.core.services.data_service import get_repository
from app.core.services.excel_format import formatear_libro
from app.core.services.formatting import formato_fecha, formato_moneda

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
HISTORIAL_DIR = PROJECT_ROOT / "exports" / "historial_compras"
META_FILE = HISTORIAL_DIR / "_meta.json"


def _ultimo_lunes(fecha: date) -> date:
    return fecha - timedelta(days=fecha.weekday())


def _leer_meta() -> dict:
    if not META_FILE.exists():
        return {}
    return json.loads(META_FILE.read_text(encoding="utf-8"))


def _guardar_meta(meta: dict) -> None:
    HISTORIAL_DIR.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def ultimo_archivo_semanal() -> date | None:
    meta = _leer_meta()
    valor = meta.get("ultimo_archivo_semanal")
    return date.fromisoformat(valor) if valor else None


def debe_archivar_semanal() -> bool:
    lunes_actual = _ultimo_lunes(date.today())
    ultimo = ultimo_archivo_semanal()
    return ultimo is None or ultimo < lunes_actual


def _filas_lotes(fecha_hasta: date | None = None, es_bebida: bool | None = None) -> list[dict]:
    """Filas de lotes hasta `fecha_hasta`. Si `es_bebida` no es `None`, se
    restringe a solo productos o solo bebidas (para que cada exportación —
    productos o bebidas— contenga únicamente lo que corresponde a su
    sección, igual que ya se filtra la tabla en pantalla)."""
    repo = get_repository()
    simbolo = repo.get_simbolo_moneda()
    filas = []

    for lote in repo.data.lotes:
        if fecha_hasta and lote.fecha_compra and lote.fecha_compra > fecha_hasta:
            continue
        if es_bebida is not None:
            producto = repo.get_producto(lote.producto_id)
            if not producto or producto.es_bebida != es_bebida:
                continue
        filas.append({
            "Producto": repo.get_nombre_producto(lote.producto_id),
            "Lote": lote.id,
            "Fecha compra": lote.fecha_compra,
            "Fecha compra txt": formato_fecha(lote.fecha_compra),
            "Expiración": formato_fecha(lote.fecha_expiracion),
            "Cantidad": lote.cantidad,
            "Restante": lote.cantidad_restante,
            "Precio total": lote.precio_total,
            "Precio total txt": formato_moneda(lote.precio_total, simbolo),
            "Proveedor": lote.marca_proveedor or "—",
        })
    return filas


def _ordenar_filas(filas: list[dict], orden: str) -> list[dict]:
    if orden == "nombre":
        return sorted(filas, key=lambda f: (f["Producto"].lower(), f["Lote"]))
    return sorted(
        filas,
        key=lambda f: (f["Fecha compra"] or date.min, f["Lote"]),
        reverse=True,
    )


def _generar_excel_bytes(
    filas: list[dict],
    titulo: str,
    criterio: str,
    etiqueta_columna: str = "Producto",
) -> bytes:
    export = [
        {
            etiqueta_columna: f["Producto"],
            "Lote": f["Lote"],
            "Fecha compra": f["Fecha compra txt"],
            "Expiración": f["Expiración"],
            "Cantidad": f["Cantidad"],
            "Restante": f["Restante"],
            "Precio total": f["Precio total txt"],
            "Proveedor": f["Proveedor"],
        }
        for f in filas
    ]

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        meta = pd.DataFrame([
            {"Campo": "Informe", "Valor": titulo},
            {"Campo": "Generado", "Valor": datetime.now().strftime("%d/%m/%Y %H:%M")},
            {"Campo": "Criterio", "Valor": criterio},
            {"Campo": "Registros", "Valor": len(export)},
        ])
        meta.to_excel(writer, sheet_name="Info", index=False)

        df = pd.DataFrame(export)
        df.to_excel(writer, sheet_name="Historial", index=False)
        formatear_libro(writer, [
            ("Info", "TablaHistorialInfo", False),
            ("Historial", "TablaHistorialCompras", True),
        ])

    return buffer.getvalue()


def archivar_historial_semanal() -> Path | None:
    if not debe_archivar_semanal():
        return None

    lunes = _ultimo_lunes(date.today())
    filas = _ordenar_filas(_filas_lotes(), "fecha")
    nombre = f"historial_compras_{lunes.isoformat()}.xlsx"
    contenido = _generar_excel_bytes(
        filas,
        "Archivo semanal de compras",
        f"Snapshot automático del lunes {formato_fecha(lunes)}",
    )

    HISTORIAL_DIR.mkdir(parents=True, exist_ok=True)
    ruta = HISTORIAL_DIR / nombre
    ruta.write_bytes(contenido)

    meta = _leer_meta()
    meta["ultimo_archivo_semanal"] = lunes.isoformat()
    meta["ultimo_archivo"] = nombre
    _guardar_meta(meta)
    return ruta


def exportar_historial_hasta(fecha_hasta: date, orden: str, es_bebida: bool = False) -> tuple[bytes, str]:
    """Exporta el historial de compras hasta `fecha_hasta`, restringido a
    productos o a bebidas según `es_bebida` — con el mismo formato, columnas
    y estilo para ambas secciones."""
    filas = _ordenar_filas(_filas_lotes(fecha_hasta, es_bebida=es_bebida), orden)
    orden_txt = "nombre (A→Z)" if orden == "nombre" else "fecha de compra (reciente primero)"
    etiqueta = "Bebida" if es_bebida else "Producto"
    contenido = _generar_excel_bytes(
        filas,
        f"Historial de compras — {'bebidas' if es_bebida else 'productos'}",
        f"Hasta {formato_fecha(fecha_hasta)} — orden: {orden_txt}",
        etiqueta_columna=etiqueta,
    )
    sufijo = "bebidas" if es_bebida else "productos"
    nombre = f"historial_compras_{sufijo}_hasta_{fecha_hasta.isoformat()}.xlsx"
    HISTORIAL_DIR.mkdir(parents=True, exist_ok=True)
    (HISTORIAL_DIR / nombre).write_bytes(contenido)
    return contenido, nombre
