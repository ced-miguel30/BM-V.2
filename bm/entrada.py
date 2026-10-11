"""Carpeta de entrada: lo que se deja ahí lo importa BM solo (cada pocos minutos).

- PDF "Ventas TPV por categoría" de BC          -> ventas TPV
- Excel de BC: Movimientos de producto, Productos o Líneas factura compra (se reconoce por sus columnas)

Lo importado pasa a `importados/`, lo que falla a `con_error/` (con aviso). Así administración solo guarda el
fichero en la carpeta compartida y BM hace el resto.
"""

from __future__ import annotations

import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import openpyxl

from bm import bc, compras, costing, db, inventario, pedidos, tpv

ESPERA = 60  # segundos sin cambios antes de tocar un fichero (por si aún se está copiando)


def carpeta(con: sqlite3.Connection) -> Path:
    d = Path(inventario.ajuste(con, "carpeta_entrada") or Path(db.DB_PATH).parent / "entrada")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tipo_excel(path: Path) -> str:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        cab = {bc._norm(c) for c in next(wb.active.iter_rows(max_row=1, values_only=True))}
    finally:
        wb.close()
    if cab & {"n mov.", "no mov."}:
        return "movimientos"
    if "unidad medida base" in cab:
        return "productos"
    if any("albaran" in c or "recepcion" in c for c in cab):
        return "facturas"
    raise ValueError("Excel no reconocido: se esperan Movimientos de producto, Productos o Líneas factura compra de BC")


def _importar(con, f: Path) -> tuple[str, str]:
    if f.suffix.lower() == ".pdf":
        r = tpv.importar_pdf(con, f)
        return "ventas TPV", f"{len(r['dias'])} días, {r['importe']:.2f} €"
    tipo = _tipo_excel(f)
    fn = {"movimientos": bc.importar_movimientos, "productos": bc.importar_productos, "facturas": compras.importar_facturas}[tipo]
    return tipo, f"{fn(con, f)} filas"


def _mover(f: Path, sub: str) -> None:
    d = f.parent / sub
    d.mkdir(exist_ok=True)
    shutil.move(str(f), d / f"{datetime.now():%Y%m%d_%H%M%S}_{f.name}")


def procesar(con: sqlite3.Connection, ahora: float | None = None) -> list[dict]:
    """Importa los ficheros listos de la carpeta. Devuelve lo hecho (también queda en entrada_log)."""
    ahora = ahora or time.time()
    hechos = []
    for f in sorted(carpeta(con).iterdir(), key=lambda x: x.stat().st_mtime):
        if not f.is_file() or f.suffix.lower() not in (".pdf", ".xlsx") or ahora - f.stat().st_mtime < ESPERA:
            continue
        try:
            tipo, detalle = _importar(con, f)
            ok = 1
        except Exception as e:  # noqa: BLE001 - cualquier fallo del fichero se apunta y se aparta, no para el servidor
            con.rollback()
            tipo, detalle, ok = "?", str(e)[:300], 0
        _mover(f, "importados" if ok else "con_error")
        con.execute("INSERT INTO entrada_log(fichero, tipo, detalle, ok) VALUES(?,?,?,?)", (f.name, tipo, detalle, ok))
        con.commit()
        hechos.append({"fichero": f.name, "tipo": tipo, "detalle": detalle, "ok": bool(ok)})
    if any(h["ok"] for h in hechos):
        inventario.sembrar(con)
        costing.valorar(con)
        pedidos.conciliar(con)
    return hechos
