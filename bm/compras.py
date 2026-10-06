"""Compras: documentos de BC (albaranes, facturas, devoluciones), adjuntos y proveedores.
BC es quien registra; aquí solo se consultan, se enlazan y se completan (foto del papel, contacto, días de reparto)."""

from __future__ import annotations

import re
import shutil
import sqlite3
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from bm import bc, db

DIAS = ["L", "M", "X", "J", "V", "S", "D"]


def _estado(tipo_doc: str, lineas: int, sin_coste: int) -> str:
    if "devoluci" in (tipo_doc or "").lower():
        return "devolucion"
    if (tipo_doc or "").lower().startswith("factura"):
        return "factura"
    if sin_coste == 0:
        return "facturado"
    return "pendiente" if sin_coste == lineas else "parcial"


def documentos(con: sqlite3.Connection, desde: str, hasta: str, proveedor: str | None = None) -> list[dict]:
    sql = """SELECT m.documento, MIN(m.fecha) fecha, m.tipo_doc, m.proveedor, COUNT(*) lineas,
               ROUND(SUM(m.coste_total), 2) importe, SUM(m.coste_total = 0) sin_coste,
               (SELECT COUNT(*) FROM adjuntos a WHERE a.documento=m.documento) adjuntos,
               (SELECT GROUP_CONCAT(f.factura) FROM factura_albaran f WHERE f.albaran=m.documento) facturas,
               (SELECT GROUP_CONCAT(f.albaran) FROM factura_albaran f WHERE f.factura=m.documento) albaranes
             FROM bc_movs m WHERE m.tipo='Compra' AND m.fecha>=? AND m.fecha<=?"""
    args = [desde, hasta]
    if proveedor:
        sql += " AND m.proveedor=?"
        args.append(proveedor)
    out = []
    for r in con.execute(sql + " GROUP BY m.documento ORDER BY fecha DESC, m.documento DESC", args):
        d = dict(r)
        d["estado"] = _estado(d["tipo_doc"], d["lineas"], d["sin_coste"])
        out.append(d)
    return out


def documento(con: sqlite3.Connection, doc: str) -> dict | None:
    lineas = [dict(x) for x in con.execute(
        """SELECT m.n_mov, m.fecha, m.producto, p.nombre, p.unidad, m.almacen, m.cantidad, m.coste_total,
             CASE WHEN m.cantidad<>0 AND m.coste_total<>0 THEN ABS(m.coste_total/m.cantidad) END precio
           FROM bc_movs m LEFT JOIN productos p ON p.codigo=m.producto WHERE m.documento=? AND m.tipo='Compra'
           ORDER BY p.nombre""", (doc,))]
    if not lineas:
        return None
    cab = con.execute("SELECT MIN(fecha) fecha, tipo_doc, proveedor FROM bc_movs WHERE documento=? AND tipo='Compra'", (doc,)).fetchone()
    return {"documento": doc, **dict(cab), "lineas": lineas,
            "importe": round(sum(l["coste_total"] or 0 for l in lineas), 2),
            "facturas": [r[0] for r in con.execute("SELECT factura FROM factura_albaran WHERE albaran=?", (doc,))],
            "albaranes": [r[0] for r in con.execute("SELECT albaran FROM factura_albaran WHERE factura=?", (doc,))],
            "adjuntos": [dict(a) for a in con.execute("SELECT id, nombre, tipo, subido, usuario FROM adjuntos WHERE documento=? ORDER BY id", (doc,))]}


def importar_facturas(con: sqlite3.Connection, path) -> int:
    """Export de BC "Líneas factura compra registradas": columnas Nº documento (factura) y Nº albarán."""
    filas = bc._filas(path)
    if not filas:
        return 0
    cols = list(filas[0])
    col_fac = next((c for c in cols if c in ("n documento", "no documento", "n factura", "no factura")), None)
    col_alb = next((c for c in cols if "albaran" in c or "recepcion" in c), None)
    if not col_fac or not col_alb:
        raise KeyError("El Excel debe tener las columnas 'Nº documento' y 'Nº albarán' (Líneas factura compra registradas)")
    pares = {(str(f[col_fac]).strip(), str(f[col_alb]).strip()) for f in filas if f.get(col_fac) and f.get(col_alb)}
    con.executemany("INSERT OR IGNORE INTO factura_albaran VALUES(?, ?)", sorted(pares))
    con.commit()
    return len(pares)


def carpeta_adjuntos(doc: str) -> Path:
    d = Path(db.DB_PATH).parent / "adjuntos" / re.sub(r"[^A-Za-z0-9_-]", "_", doc)
    d.mkdir(parents=True, exist_ok=True)
    return d


def guardar_adjunto(con, doc: str, nombre: str, origen: Path, tipo: str | None, usuario: str | None) -> int:
    if not con.execute("SELECT 1 FROM bc_movs WHERE documento=? LIMIT 1", (doc,)).fetchone():
        raise ValueError("Ese documento no existe en los movimientos importados de BC")
    nombre = Path(nombre).name or "adjunto"
    destino = carpeta_adjuntos(doc) / f"{date.today():%Y%m%d}_{nombre}"
    shutil.copyfile(origen, destino)
    aid = con.execute("INSERT INTO adjuntos(documento, nombre, fichero, tipo, usuario) VALUES(?,?,?,?,?)",
                      (doc, nombre, str(destino), tipo, usuario)).lastrowid
    con.commit()
    return aid


def dias_reparto_deducidos(con, proveedor: str, dias: int = 180) -> list[int]:
    """Días de la semana en que suele llegar (>= 15 % de sus entregas de los últimos 6 meses)."""
    desde = (date.today() - timedelta(days=dias)).isoformat()
    fechas = [r[0] for r in con.execute(
        "SELECT DISTINCT fecha FROM bc_movs WHERE tipo='Compra' AND proveedor=? AND fecha>=? AND fecha<=?",
        (proveedor, desde, date.today().isoformat()))]
    if len(fechas) < 3:
        return []
    c = Counter(date.fromisoformat(f).weekday() for f in fechas)
    return sorted(d for d, n in c.items() if n / len(fechas) >= 0.15)


def dias_reparto(con, p) -> list[int]:
    """Los días indicados a mano mandan; si no hay, los deducidos del histórico."""
    if p["dias_reparto"]:
        return [int(x) for x in str(p["dias_reparto"]).split(",") if x.strip().isdigit()]
    return dias_reparto_deducidos(con, p["nombre"])


def proveedores(con: sqlite3.Connection) -> list[dict]:
    hoy = date.today().isoformat()
    hace90 = (date.today() - timedelta(days=90)).isoformat()
    stats = {r["proveedor"]: dict(r) for r in con.execute(
        """SELECT proveedor, COUNT(DISTINCT documento) documentos_90d, ROUND(SUM(coste_total), 2) gasto_90d,
             MAX(fecha) ultimo, COUNT(DISTINCT producto) productos_90d
           FROM bc_movs WHERE tipo='Compra' AND fecha>=? AND fecha<=? GROUP BY proveedor""", (hace90, hoy))}
    out = []
    for p in con.execute("SELECT * FROM proveedores ORDER BY nombre"):
        s = stats.get(p["nombre"], {})
        out.append({**dict(p), "documentos_90d": s.get("documentos_90d", 0), "gasto_90d": s.get("gasto_90d", 0),
                    "ultimo": s.get("ultimo"), "productos_90d": s.get("productos_90d", 0),
                    "dias": dias_reparto(con, p), "dias_deducidos": dias_reparto_deducidos(con, p["nombre"])})
    return sorted(out, key=lambda x: -(x["gasto_90d"] or 0))


def proveedor_habitual(con, producto: str) -> str | None:
    r = con.execute("""SELECT proveedor FROM bc_movs WHERE producto=? AND tipo='Compra' AND cantidad>0 AND proveedor<>''
                       ORDER BY fecha DESC, n_mov DESC LIMIT 1""", (producto,)).fetchone()
    return r[0] if r else None


def proxima_entrega(con, proveedor: str, desde: date | None = None) -> date | None:
    """Primer día de reparto del proveedor si se pide hoy, respetando su plazo (1 día si no se sabe)."""
    p = con.execute("SELECT * FROM proveedores WHERE nombre=?", (proveedor,)).fetchone()
    if not p:
        return None
    dias = dias_reparto(con, p)
    if not dias:
        return None
    d = (desde or date.today()) + timedelta(days=max(1, p["plazo_dias"] or 1))
    for _ in range(14):
        if d.weekday() in dias:
            return d
        d += timedelta(days=1)
    return None
