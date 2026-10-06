"""Migración desde BM v2 (datos_hotel.json) a SQLite.

Se migran hechos (qué se consumió, cuándo, en qué servicio) y recetas.
NO se migran lotes ni costes de v2: el coste se recalcula con los precios reales de BC.
Los registros anulados de v2 (reimportaciones) se descartan.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path

_UNIDADES = {"UD": "UD", "KG": "KG", "L": "LT", "LT": "LT"}


def _n(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def _mapear_productos(con: sqlite3.Connection, productos: list[dict], csv_map: dict) -> dict:
    """bm2_id -> (codigo, factor). Rellena mapa_bm2 y crea productos BM2-* sin equivalente."""
    por_nombre = defaultdict(list)
    for r in con.execute("SELECT codigo, nombre FROM productos WHERE origen='bc'"):
        por_nombre[_n(r["nombre"])].append(r["codigo"])
    n_movs = dict(con.execute("SELECT producto, count(*) FROM bc_movs GROUP BY producto").fetchall())
    unidad_bc = dict(con.execute("SELECT codigo, unidad FROM productos").fetchall())

    mapa = {}
    for p in productos:
        revisar = None
        cands = por_nombre.get(_n(p["nombre"]), [])
        if len(cands) == 1:
            codigo = cands[0]
        elif cands:
            codigo = max(cands, key=lambda c: n_movs.get(c, 0))
            revisar = f"nombre repetido en BC: {', '.join(cands)}"
        elif csv_map.get(p["id"]):
            codigo = csv_map[p["id"]]
            revisar = "asociado por informe de compras (nombre distinto)"
        else:
            codigo = f"BM2-{p['id']}"
            revisar = "sin artículo en BC"
            con.execute(
                "INSERT OR IGNORE INTO productos(codigo, nombre, unidad, origen) VALUES(?,?,?,'bm2')",
                (codigo, p["nombre"], _UNIDADES.get(_n(p["unidad"]), _n(p["unidad"]))),
            )
        u2 = _UNIDADES.get(_n(p["unidad"]), _n(p["unidad"]))
        ubc = unidad_bc.get(codigo) or u2
        if revisar is None and u2 != ubc:
            revisar = f"unidad BM2 {p['unidad']} vs BC {ubc}"
        con.execute(
            "INSERT OR REPLACE INTO mapa_bm2 VALUES(?,?,?,?,1,?)",
            (p["id"], p["nombre"], p["unidad"], codigo, revisar),
        )
        mapa[p["id"]] = (codigo, 1.0)
    return mapa


def migrar(con: sqlite3.Connection, json_path, csv_compras=None) -> dict:
    d = json.loads(Path(json_path).read_text(encoding="utf-8"))
    csv_map = {}
    if csv_compras and Path(csv_compras).exists():
        with open(csv_compras, encoding="utf-8-sig") as fh:
            csv_map = {r["producto_id"]: r["codigo"] for r in csv.DictReader(fh)}

    mapa = _mapear_productos(con, d["productos"], csv_map)

    def lineas(items):
        for l in items:
            if l["producto_id"] in mapa and l.get("cantidad"):
                codigo, factor = mapa[l["producto_id"]]
                yield codigo, l["cantidad"] * factor, l.get("coste")

    # Recetas
    for r in d["recetas"]:
        con.execute(
            "INSERT OR REPLACE INTO recetas(id, nombre, servicio, porciones, activo) VALUES(?,?,?,?,?)",
            (r["id"], r["nombre"], r.get("categoria"), r.get("porciones_estandar") or 1, int(r.get("activo", True))),
        )
        con.execute("DELETE FROM receta_lineas WHERE receta_id=?", (r["id"],))
        con.executemany(
            "INSERT INTO receta_lineas(receta_id, producto, cantidad) VALUES(?,?,?)",
            [(r["id"], c, q) for c, q, _ in lineas(r["ingredientes"])],
        )

    # Consumos (hechos físicos)
    n = defaultdict(int)

    def consumo(ref, fecha, servicio, tipo, comensales, nota, usuario, items):
        if con.execute("SELECT 1 FROM consumos WHERE ref=?", (ref,)).fetchone():
            n["ya_existia"] += 1
            return
        cid = con.execute(
            """INSERT INTO consumos(fecha, servicio, tipo, origen, ref, comensales, nota, usuario)
               VALUES(?,?,?,'bm2',?,?,?,?)""",
            (fecha, servicio, tipo, ref, comensales, nota, usuario),
        ).lastrowid
        con.executemany(
            "INSERT INTO consumo_lineas(consumo_id, producto, cantidad, coste_legacy) VALUES(?,?,?,?)",
            [(cid, c, q, cl) for c, q, cl in lineas(items)],
        )
        n[f"{tipo}:{servicio}"] += 1

    def recetas_txt(reg):
        rs = reg.get("registros_recetas") or []
        return "; ".join(f"{x['nombre_receta']} x{x['porciones']:g}" for x in rs) or None

    for x in d["desayunos"]:
        if not x.get("anulado"):
            estimado = (x.get("clave_idempotencia") or "").startswith("desayuno-media")
            nota = "ESTIMADO: media de otros días (no es un registro real)" if estimado else recetas_txt(x)
            consumo(f"bm2:{x['id']}:{x.get('clave_idempotencia') or ''}", x["fecha"], "desayuno", "consumo", x.get("num_huespedes"),
                    nota, x.get("registrado_por"), x["lineas"])
    # registros_buffet de v2 es un resumen por configuración; su consumo real ya está en desayunos.
    for x in d["registros_servicio"]:
        if not x.get("anulado"):
            consumo(f"bm2:{x['id']}", x["fecha"], x["tipo_servicio"], "consumo", x.get("num_huespedes"),
                    recetas_txt(x), x.get("registrado_por"), x["lineas"])
    for x in d["mermas"]:
        # "merma-hielo" la inventaba el importador TPV de v2 (10% de los cocteles): no es un hecho fisico.
        if not x.get("anulado") and not any("merma-hielo" in (l.get("comentario") or "") for l in x["lineas"]):
            ls = x["lineas"]
            servicio = next((l.get("tipo_servicio_snapshot") for l in ls if l.get("tipo_servicio_snapshot")), None)
            nota = "; ".join(filter(None, {f"{l.get('motivo') or ''} {l.get('comentario') or ''}".strip() for l in ls}))
            consumo(f"bm2:{x['id']}", x["fecha"], servicio, "merma", None, nota or None,
                    x.get("registrado_por"), ls)

    # Usuarios (mismo formato de hash pbkdf2 que v2)
    for u in d["usuarios"]:
        con.execute(
            "INSERT OR REPLACE INTO usuarios(id, nombre, login, rol, password_hash, activo) VALUES(?,?,?,?,?,?)",
            (u["id"], u["nombre"], (u.get("login") or "").strip().lower() or None, u["rol"],
             u.get("password_hash") or None, int(u.get("activo", True))),
        )
    con.commit()
    return dict(n)


def _clave(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", _n(s))


def sembrar_tpv(con: sqlite3.Connection, alias_json) -> int:
    """Una sola vez: reutiliza los alias TPV que v2 tenía escritos en código (extraídos a alias_tpv.json)
    como asignaciones iniciales editables. Los casos 'especiales' de v2 (smoothies/helados repartidos,
    cubetas, hielo) NO se migran: quedan pendientes."""
    recetas = {_clave(r["nombre"]): r["id"] for r in con.execute("SELECT id, nombre FROM recetas")}
    mapa = dict(con.execute("SELECT bm2_id, codigo FROM mapa_bm2").fetchall())
    alias = {}
    for x in json.loads(Path(alias_json).read_text(encoding="utf-8")):
        if x["tipo"] == "receta" and _clave(x["destino"]) in recetas:
            alias[_clave(x["alias"])] = ("receta", recetas[_clave(x["destino"])])
        elif x["tipo"] == "producto" and x["destino"] in mapa:
            alias[_clave(x["alias"])] = ("producto", mapa[x["destino"]])
    n = 0
    for art in con.execute("SELECT codigo, nombre FROM tpv_articulos WHERE receta_id IS NULL AND producto IS NULL").fetchall():
        k = _clave(art["nombre"])
        hit = alias.get(k) or next((alias[a] for a in sorted(alias, key=len, reverse=True) if len(a) >= 5 and a in k), None)
        if hit:
            col = "receta_id" if hit[0] == "receta" else "producto"
            con.execute(f"UPDATE tpv_articulos SET {col}=? WHERE codigo=?", (hit[1], art["codigo"]))
            n += 1
    con.commit()
    return n


def ventas_tpv_historicas(json_path) -> list[dict]:
    """Líneas TPV de agosto que v2 extrajo por OCR (_tpv_merged_reimport.json), en formato tpv.leer_pdf."""
    out = []
    for x in json.loads(Path(json_path).read_text(encoding="utf-8")):
        d, m, y = x["fecha"].split("/")
        out.append({"fecha": f"{y}-{m}-{d}", "codigo": x["pv"], "nombre": x["nombre"],
                    "categoria": "104BEBIDAS" if x.get("cat") == "bebidas" else "101ALIMENTACION",
                    "importe": float(x["importe"])})
    return out


_SUSTITUYE = {
    "huevo": ("huevo frito", "huevo pochado", "huevo cocido", "huevos revueltos"),
    "pan": ("tostada", "tostada integral", "pan blanco", "pan integral", "tostada sin gluten", "pan sin gluten"),
}


def sembrar_desayuno(con: sqlite3.Connection, semillas) -> dict:
    """Una sola vez: atajos, buffet, sustituciones y recetas del día que v2 tenía escritos en código."""
    s = json.loads(Path(semillas).read_text(encoding="utf-8"))
    mapa = dict(con.execute("SELECT bm2_id, codigo FROM mapa_bm2").fetchall())
    recetas = {_clave(r["nombre"]): r["id"] for r in con.execute("SELECT id, nombre FROM recetas")}
    recetas_ids = set(recetas.values())
    sust = {e: g for g, es in _SUSTITUYE.items() for e in es}
    n = defaultdict(int)

    def atajo(etiqueta, grupo, producto, receta_id, cantidad, sustituye=None, activo=True):
        con.execute(
            "INSERT OR REPLACE INTO atajos(etiqueta, grupo, producto, receta_id, cantidad, sustituye, activo) VALUES(?,?,?,?,?,?,?)",
            (etiqueta, grupo, producto, receta_id if receta_id in recetas_ids else None, cantidad, sustituye, int(activo)),
        )
        n[grupo] += 1

    for a in s["atajos"]:
        if a["bm2_producto"] in mapa:
            atajo(a["etiqueta"], a["grupo"], mapa[a["bm2_producto"]], None, a["cantidad"], sust.get(_n(a["etiqueta"]).lower()))
    for etq, grupo in (("Sin huevo", "huevo"), ("Sin tostada", "pan"), ("Sin pan", "pan")):
        atajo(etq, "omitir", None, None, 0, grupo)
    for b in s["buffet"]:
        prod = mapa.get(b["bm2_producto"]) if b["bm2_producto"] else None
        if prod or b["receta_id"] in recetas_ids:
            atajo(b["etiqueta"], "buffet", prod, b["receta_id"], b["cantidad"] or 1, None, b["activo"])
            con.execute("UPDATE atajos SET seccion=? WHERE grupo='buffet' AND etiqueta=?", (b.get("seccion"), b["etiqueta"]))
    for grupo, ids in s["sustitucion"].items():
        con.executemany("INSERT OR IGNORE INTO sustitucion VALUES(?,?)", [(grupo, mapa[i]) for i in ids if i in mapa])
    for etiqueta, nombres in s["recetas_dia"].items():
        if _clave(etiqueta) not in recetas:  # receta "virtual" que se resuelve por día de la semana
            rid = "r-" + _clave(etiqueta).lower()
            con.execute("INSERT OR IGNORE INTO recetas(id, nombre, servicio) VALUES(?,?,?)",
                        (rid, etiqueta, "bebidas" if "COCTEL" in _clave(etiqueta) else "desayuno"))
            recetas[_clave(etiqueta)] = rid
            if "COCTEL" in _clave(etiqueta):
                con.execute("UPDATE tpv_articulos SET receta_id=? WHERE receta_id IS NULL AND nombre LIKE 'COCTEL DEL D%'", (rid,))
        for dia, nombre in enumerate(nombres):
            if _clave(nombre) in recetas:
                con.execute("INSERT OR REPLACE INTO recetas_dia VALUES(?,?,?)", (etiqueta, dia, recetas[_clave(nombre)]))
                n["receta_dia"] += 1
    con.commit()
    return dict(n)
