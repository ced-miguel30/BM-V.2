"""Ventas TPV (Business Central, informe "Ventas TPV por categoría").

1. importar_pdf(): lee el texto del PDF (sin OCR), suma por día y artículo PV y SUSTITUYE esos días.
   Subir dos veces el mismo día, o PDFs que se solapan, nunca duplica.
2. Cada artículo PV se asigna una vez a una receta o a un producto (tabla tpv_articulos).
   Lo no asignado queda pendiente y no bloquea la importación.
3. regenerar(): convierte ventas x asignación en consumos (uno por día y servicio). Cambiar una
   asignación y regenerar corrige todo el histórico sin tocar nada a mano.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict

import pymupdf

from bm.consumos import receta_real

_LINEA = re.compile(r"^(\d{2})/(\d{2})/(\d{4})\s+(PV\d+)\s*$")
_IMPORTE = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{1,2}$")  # BC omite el cero final: "18,7"
_CATEGORIA = re.compile(r"Categor.a Producto:\s*(\S+)")


def _euros(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def leer_pdf(path) -> list[dict]:
    """-> [{'fecha','codigo','nombre','categoria','importe'}] una por línea de ticket."""
    texto = "\n".join(p.get_text() for p in pymupdf.open(path))
    if "PV" not in texto:
        raise ValueError("El PDF no contiene texto de ventas TPV (¿es el informe 'Ventas TPV por categoría'?)")
    filas, categoria, actual, nombre = [], None, None, []
    for raw in texto.splitlines():
        s = raw.strip()
        if m := _CATEGORIA.search(s):
            categoria, actual = m.group(1), None
        elif m := _LINEA.match(s):
            d, mth, y, codigo = m.groups()
            actual, nombre = {"fecha": f"{y}-{mth}-{d}", "codigo": codigo, "categoria": categoria}, []
        elif actual and _IMPORTE.match(s):
            filas.append({**actual, "nombre": " ".join(nombre).strip(), "importe": _euros(s)})
            actual = None
        elif actual:
            nombre.append(s)
    if not filas:
        raise ValueError("No se encontraron líneas de venta en el PDF")
    return filas


def _precio_habitual(importes: list[float]) -> float | None:
    """PVP unitario = importe positivo más repetido (empate: el menor). 13,08 de 4 Heineken no gana a 3,27."""
    c = Counter(round(i, 2) for i in importes if i > 0)
    if not c:
        return None
    top = max(c.values())
    return min(v for v, n in c.items() if n == top)


def _servicio_por_categoria(categoria: str | None) -> str:
    return "bebidas" if (categoria or "").startswith("104") else "comida"


def importar_lineas(con: sqlite3.Connection, filas: list[dict]) -> dict:
    """Sustituye las ventas de los días presentes en `filas`. Devuelve un resumen."""
    por_articulo = defaultdict(list)
    for f in filas:
        por_articulo[f["codigo"]].append(f)
    for codigo, fs in por_articulo.items():
        precio = _precio_habitual([f["importe"] for f in fs])
        con.execute(
            """INSERT INTO tpv_articulos(codigo, nombre, categoria, servicio, precio) VALUES(?,?,?,?,?)
               ON CONFLICT(codigo) DO UPDATE SET
                 categoria=COALESCE(tpv_articulos.categoria, excluded.categoria),
                 precio=COALESCE(tpv_articulos.precio, excluded.precio)""",
            (codigo, fs[0]["nombre"], fs[0]["categoria"], _servicio_por_categoria(fs[0]["categoria"]), precio),
        )
    fechas = sorted({f["fecha"] for f in filas})
    con.executemany("DELETE FROM tpv_ventas WHERE fecha=?", [(f,) for f in fechas])
    totales = defaultdict(float)
    for f in filas:
        totales[(f["fecha"], f["codigo"])] += f["importe"]
    con.executemany(
        "INSERT INTO tpv_ventas(fecha, codigo, importe) VALUES(?,?,?)",
        [(fe, co, round(i, 2)) for (fe, co), i in totales.items() if abs(i) > 0.004],
    )
    con.commit()
    return {"dias": fechas, "lineas": len(filas), "importe": round(sum(f["importe"] for f in filas), 2)}


def importar_pdf(con: sqlite3.Connection, path) -> dict:
    resumen = importar_lineas(con, leer_pdf(path))
    regenerar(con, resumen["dias"])
    return resumen


def regenerar(con: sqlite3.Connection, fechas: list[str] | None = None) -> dict:
    """Reconstruye los consumos TPV (origen 'tpv') de las fechas dadas (todas si None).
    En esas fechas, los consumos de comida/bebidas heredados de BM v2 se retiran: la fuente es el TPV."""
    if fechas is None:
        fechas = [r[0] for r in con.execute("SELECT DISTINCT fecha FROM tpv_ventas")]
    recetas = defaultdict(list)
    porciones = dict(con.execute("SELECT id, porciones FROM recetas").fetchall())
    for r in con.execute("SELECT receta_id, producto, cantidad FROM receta_lineas"):
        recetas[r["receta_id"]].append((r["producto"], r["cantidad"]))

    n = 0
    for fecha in fechas:
        con.execute("DELETE FROM consumos WHERE origen='tpv' AND fecha=?", (fecha,))
        con.execute(
            "DELETE FROM consumos WHERE origen='bm2' AND tipo='consumo' AND servicio IN ('comida','cena','bebidas') AND fecha=?",
            (fecha,),
        )
        lineas = defaultdict(list)
        for v in con.execute(
            """SELECT v.importe, a.* FROM tpv_ventas v JOIN tpv_articulos a ON a.codigo=v.codigo
               WHERE v.fecha=? AND a.ignorar=0 AND a.precio > 0 AND (a.receta_id IS NOT NULL OR a.producto IS NOT NULL)""",
            (fecha,),
        ):
            uds = round(v["importe"] / v["precio"])
            if uds <= 0:
                continue
            if v["receta_id"]:
                rid = receta_real(con, v["receta_id"], fecha)  # "Coctel del dia" -> el de ese día
                f = uds / (porciones.get(rid) or 1)
                lineas[v["servicio"]] += [(p, q * f, rid) for p, q in recetas[rid]]
            else:
                lineas[v["servicio"]].append((v["producto"], uds * v["factor"], None))
        for servicio, ls in lineas.items():
            cid = con.execute(
                "INSERT INTO consumos(fecha, servicio, origen, ref) VALUES(?,?, 'tpv', ?)",
                (fecha, servicio, f"tpv:{fecha}:{servicio}"),
            ).lastrowid
            con.executemany(
                "INSERT INTO consumo_lineas(consumo_id, producto, cantidad, receta_id) VALUES(?,?,?,?)",
                [(cid, p, q, r) for p, q, r in ls],
            )
            n += 1
    con.commit()
    return {"consumos": n, "dias": len(fechas)}


def pendientes(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Artículos vendidos sin asignar, por importe vendido (lo que más pesa primero)."""
    return con.execute(
        """SELECT a.codigo, a.nombre, a.servicio, a.precio, SUM(v.importe) importe, COUNT(DISTINCT v.fecha) dias
           FROM tpv_articulos a JOIN tpv_ventas v ON v.codigo=a.codigo
           WHERE a.ignorar=0 AND a.receta_id IS NULL AND a.producto IS NULL
           GROUP BY a.codigo ORDER BY importe DESC"""
    ).fetchall()


GENERICAS = {"copa", "botella", "vino", "racion", "vaso", "plato", "media"}


def _clave(nombre_n: str) -> list[str]:
    """Palabras que identifican un artículo: las de 4+ letras y los números (Licor 43, Habana 7), sin las genéricas."""
    return [w for w in nombre_n.split() if (len(w) >= 4 or w.isdigit()) and w not in GENERICAS]


def _parecido(art: list[str], rec: list[str]) -> float:
    """0..1: palabras en común sobre las del más largo. La primera palabra del artículo (plato o marca) debe estar."""
    if not art or not rec or not _comparten(art[:1], rec):
        return 0.0
    return sum(_comparten([p], rec) for p in art) / max(len(art), len(rec))


def _comparten(palabras: list[str], otras: list[str]) -> bool:
    """Alguna palabra coincide (por las 5 primeras letras: plurales y erratas; los números, exactos)."""
    return any(w == p if p.isdigit() else w.startswith(p[:5]) for p in palabras for w in otras)


def sugerencias(con: sqlite3.Connection) -> dict:
    """Para cada artículo sin asignar: la receta de nombre más parecido o, si no hay, el producto más comprado
    que contiene sus palabras. Solo se sugiere: alguien lo confirma con un clic."""
    import difflib

    from bm.excel import _n

    recetas = {_n(r["nombre"]): (r["id"], r["nombre"]) for r in con.execute("SELECT id, nombre FROM recetas WHERE activo=1")}
    compras = {r[0]: r[1] for r in con.execute(
        """SELECT producto, COUNT(*) FROM bc_movs WHERE tipo='Compra' AND fecha>=date('now','-180 days') GROUP BY 1""")}
    productos = [(r["codigo"], r["nombre"], _n(r["nombre"]).split()) for r in con.execute(
        "SELECT codigo, nombre FROM productos WHERE es_tpv=0 AND categoria LIKE '1%' AND activo=1")]
    out = {}
    for a in pendientes(con):
        k = _n(a["nombre"])
        palabras = _clave(k)
        # Receta: la que más palabras con significado comparte (desempata el parecido del texto).
        score, _, m = max(((_parecido(palabras, _clave(n)), difflib.SequenceMatcher(None, k, n).ratio(), n) for n in recetas),
                          default=(0, 0, None))
        if score >= 0.5:
            out[a["codigo"]] = {"tipo": "receta", "id": recetas[m][0], "nombre": recetas[m][1], "confianza": round(score, 2)}
            continue
        cands = [(compras.get(c, 0), c, n) for c, n, ws in productos if palabras and all(_comparten([p], ws) for p in palabras)]
        if cands:
            _, c, n = max(cands)
            out[a["codigo"]] = {"tipo": "producto", "id": c, "nombre": n, "confianza": 0.5}
    return out
