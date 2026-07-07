"""Formato profesional para exportaciones Excel."""

from __future__ import annotations

import re

from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

NAVY = "0B1F3A"
WHITE = "FFFFFF"


def _nombre_tabla_seguro(nombre: str) -> str:
    limpio = re.sub(r"[^A-Za-z0-9_]", "", nombre)
    if not limpio or limpio[0].isdigit():
        limpio = "T" + limpio
    return limpio[:240]


def ajustar_ancho_columnas(ws: Worksheet) -> None:
    for col_idx in range(1, ws.max_column + 1):
        max_len = 0
        col_letter = get_column_letter(col_idx)
        for row_idx in range(1, ws.max_row + 1):
            valor = ws.cell(row=row_idx, column=col_idx).value
            if valor is not None:
                max_len = max(max_len, len(str(valor)))
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 50)


def formatear_cabecera(ws: Worksheet) -> None:
    if ws.max_row < 1 or ws.max_column < 1:
        return
    fill = PatternFill("solid", fgColor=NAVY)
    font = Font(color=WHITE, bold=True)
    align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for col_idx in range(1, ws.max_column + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = fill
        cell.font = font
        cell.alignment = align


def aplicar_tabla_excel(ws: Worksheet, nombre_tabla: str) -> None:
    if ws.max_row < 2 or ws.max_column < 1:
        return
    nombre = _nombre_tabla_seguro(nombre_tabla)
    ref = f"A1:{get_column_letter(ws.max_column)}{ws.max_row}"
    if nombre in ws.tables:
        del ws.tables[nombre]
    tabla = Table(displayName=nombre, ref=ref)
    tabla.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(tabla)


def congelar_cabecera(ws: Worksheet) -> None:
    if ws.max_row >= 2:
        ws.freeze_panes = "A2"


def formatear_hoja_datos(ws: Worksheet, nombre_tabla: str) -> None:
    formatear_cabecera(ws)
    aplicar_tabla_excel(ws, nombre_tabla)
    ajustar_ancho_columnas(ws)
    congelar_cabecera(ws)


def formatear_hoja_info(ws: Worksheet) -> None:
    formatear_cabecera(ws)
    ajustar_ancho_columnas(ws)


def formatear_libro(writer, hojas: list[tuple[str, str, bool]]) -> None:
    """
    Aplica formato tras escribir DataFrames.
    hojas: [(nombre_hoja, nombre_tabla, es_datos), ...]
    """
    for nombre_hoja, nombre_tabla, es_datos in hojas:
        if nombre_hoja not in writer.sheets:
            continue
        ws = writer.sheets[nombre_hoja]
        if es_datos:
            formatear_hoja_datos(ws, nombre_tabla)
        else:
            formatear_hoja_info(ws)
