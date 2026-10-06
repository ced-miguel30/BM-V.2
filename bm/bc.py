"""Importación de exportaciones Excel de Business Central ("Abrir en Excel").

- Productos.xlsx           -> productos (maestro)
- Movs. productos.xlsx     -> bc_movs (compras, ajustes de inventario, transferencias)

Ambas son idempotentes: la clave es la de BC (Nº producto / Nº mov.).
"""

from __future__ import annotations

import sqlite3
import unicodedata
from datetime import date, datetime

import openpyxl


def _norm(s) -> str:
    s = str(s or "").replace("º", "").replace("°", "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def _filas(path) -> list[dict]:
    """Filas como dicts con cabeceras normalizadas (sin tildes/º: BC cambia la codificación)."""
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
    it = ws.iter_rows(values_only=True)
    cab = [_norm(c) for c in next(it)]
    return [dict(zip(cab, f)) for f in it if any(v not in (None, "") for v in f)]


def _col(fila: dict, *nombres):
    for n in nombres:
        if n in fila:
            return fila[n]
    raise KeyError(f"Falta la columna {nombres[0]!r} en el Excel de BC")


def _bool(v) -> bool:
    return str(v).strip().upper() in ("=TRUE()", "TRUE", "SI", "SÍ", "1")


def _fecha(v) -> str:
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    d, m, y = str(v).strip().split("/")
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def _num(v) -> float:
    if v in (None, ""):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).replace(".", "").replace(",", "."))


def importar_productos(con: sqlite3.Connection, path) -> int:
    filas = _filas(path)
    con.executemany(
        """INSERT INTO productos(codigo, nombre, unidad, categoria, es_tpv, activo, coste_ref, origen)
           VALUES(?,?,?,?,?,?,?,'bc')
           ON CONFLICT(codigo) DO UPDATE SET nombre=excluded.nombre, unidad=excluded.unidad,
             categoria=excluded.categoria, es_tpv=excluded.es_tpv, activo=excluded.activo,
             coste_ref=excluded.coste_ref, origen='bc'""",
        [
            (
                str(_col(f, "n", "no")).strip(),
                str(_col(f, "descripcion") or "").strip(),
                str(_col(f, "unidad medida base") or "").strip().upper(),
                str(f.get("cod. categoria producto") or "").strip(),
                int(_bool(f.get("articulo de tpv"))),
                int(not _bool(f.get("bloqueado"))),
                _num(f.get("coste unitario")) or None,
            )
            for f in filas
            if _col(f, "n", "no")
        ],
    )
    # Artículos de TPV (PV...) disponibles para asignar a receta/producto.
    con.execute(
        """INSERT INTO tpv_articulos(codigo, nombre, categoria, servicio)
           SELECT codigo, nombre, categoria, CASE WHEN categoria LIKE '104%' THEN 'bebidas' ELSE 'comida' END
           FROM productos WHERE es_tpv=1 AND origen='bc'
           ON CONFLICT(codigo) DO UPDATE SET nombre=excluded.nombre"""
    )
    con.commit()
    return len(filas)


def importar_movimientos(con: sqlite3.Connection, path) -> int:
    filas = _filas(path)
    datos = []
    for f in filas:
        datos.append(
            (
                int(_col(f, "n mov.", "no mov.")),
                _fecha(_col(f, "fecha registro")),
                str(_col(f, "tipo movimiento")).strip(),
                str(f.get("tipo documento") or "").strip(),
                str(f.get("n documento") or "").strip(),
                str(_col(f, "n producto")).strip(),
                str(f.get("proveedor/cliente") or "").strip(),
                str(f.get("cod. almacen") or "").strip(),
                _num(_col(f, "cantidad")),
                _num(f.get("coste unitario")),
                _num(f.get("importe coste (real)")),
            )
        )
    # Productos que aparecen en movimientos pero no en el maestro exportado.
    con.executemany(
        "INSERT OR IGNORE INTO productos(codigo, nombre, origen) VALUES(?, ?, 'bc')",
        {(d[5], str(f.get("descripcion") or d[5]).strip()) for d, f in zip(datos, filas)},
    )
    con.executemany(
        """INSERT INTO bc_movs(n_mov, fecha, tipo, tipo_doc, documento, producto, proveedor, almacen,
                               cantidad, coste_unit, coste_total)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(n_mov) DO UPDATE SET fecha=excluded.fecha, tipo=excluded.tipo,
             tipo_doc=excluded.tipo_doc, documento=excluded.documento, producto=excluded.producto,
             proveedor=excluded.proveedor, almacen=excluded.almacen, cantidad=excluded.cantidad,
             coste_unit=excluded.coste_unit, coste_total=excluded.coste_total""",
        datos,
    )
    con.commit()
    return len(datos)
