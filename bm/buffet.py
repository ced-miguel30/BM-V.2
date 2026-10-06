"""Buffet del día: propuesta de lo que hay que sacar según comensales y lo que se gasta por comensal.

- Conceptos = atajos del grupo 'buffet' (fruta, bollería, pan, fiambres, yogures...).
- Producto: se aprende cuánto se gasta POR COMENSAL (histórico de buffets confirmados o importados).
- Receta (p. ej. "Estándar buffet diario"): se aprende cuántas raciones se sacan AL DÍA.
- Confirmar = registrar el consumo (lo sacado menos lo que sobró). Reconfirmar un día lo sustituye.
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import date, timedelta

from bm import consumos, costing, prevision

REF_BUFFET = ("buffet:%", "excel:ConsumoBuffet:%", "bm2:%:import-ago26-buffet%", "bm2:%:buffet-xlsx%")


def comensales_dia(con, fecha: str) -> int | None:
    """Comensales registrados ese día en desayuno (el registro del desayuno los trae)."""
    r = con.execute("SELECT SUM(comensales) FROM consumos WHERE anulado=0 AND servicio='desayuno' AND fecha=? AND comensales>0",
                    (fecha,)).fetchone()[0]
    return int(r) if r else None


def _historico(con, hoy: date, dias: int = 60):
    """-> (por producto: [cantidad/comensal], por receta: [raciones/día]) de los buffets con comensales conocidos."""
    desde = (hoy - timedelta(days=dias)).isoformat()
    filtro = " OR ".join("c.ref LIKE ?" for _ in REF_BUFFET)
    base_receta = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT receta_id, producto, cantidad FROM receta_lineas GROUP BY receta_id")}  # 1er ingrediente de referencia
    porciones = dict(con.execute("SELECT id, porciones FROM recetas").fetchall())
    prod_dia, rec_dia = defaultdict(lambda: defaultdict(float)), defaultdict(lambda: defaultdict(float))
    for l in con.execute(
        f"""SELECT c.fecha, l.producto, l.cantidad, l.receta_id FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id
            WHERE c.anulado=0 AND c.fecha>=? AND c.fecha<? AND ({filtro})""", (desde, hoy.isoformat(), *REF_BUFFET)
    ):
        if l["receta_id"] is None:
            prod_dia[l["producto"]][l["fecha"]] += l["cantidad"]
        elif base_receta.get(l["receta_id"], (None,))[0] == l["producto"]:
            _, q = base_receta[l["receta_id"]]
            rec_dia[l["receta_id"]][l["fecha"]] += l["cantidad"] / q * (porciones.get(l["receta_id"]) or 1)
    com = {}
    por_comensal = {}
    for p, dias_ in prod_dia.items():
        xs = []
        for f, q in dias_.items():
            n = com.setdefault(f, comensales_dia(con, f))
            if n:
                xs.append(q / n)
        if xs:
            por_comensal[p] = sum(xs) / len(xs)
    por_dia = {r: sum(v.values()) / len(v) for r, v in rec_dia.items() if v}
    return por_comensal, por_dia


def _redondear(q: float, unidad: str | None) -> float:
    return float(math.ceil(q - 1e-9)) if (unidad or "").upper() in ("UD", "PQ", "BT", "rac") else round(q, 2)


def propuesta(con: sqlite3.Connection, fecha: str) -> dict:
    hoy = date.fromisoformat(fecha)
    registrados = comensales_dia(con, fecha)
    previstos = next((x["comensales"] for x in prevision.favoritos(con, hoy - timedelta(days=1))["comensales"]
                      if x["fecha"] == fecha), None)
    comensales = registrados or previstos
    por_comensal, por_dia = _historico(con, hoy)
    hechos = {r["etiqueta"]: dict(r) for r in con.execute("SELECT * FROM buffet_diario WHERE fecha=?", (fecha,))}
    items = []
    for a in con.execute(
        """SELECT a.*, p.nombre producto_nombre, p.unidad FROM atajos a LEFT JOIN productos p ON p.codigo=a.producto
           WHERE a.grupo='buffet' AND a.activo=1 ORDER BY a.seccion, a.etiqueta"""
    ):
        if a["receta_id"]:
            unidad, base = "rac", por_dia.get(a["receta_id"])
            prop = None if base is None else _redondear(base, "rac")
        else:
            unidad, base = a["unidad"], por_comensal.get(a["producto"])
            prop = None if base is None or not comensales else _redondear(base * comensales, unidad)
        h = hechos.get(a["etiqueta"])
        items.append({"etiqueta": a["etiqueta"], "seccion": a["seccion"] or "Otros", "unidad": unidad,
                      "producto": a["producto_nombre"], "por_comensal": None if a["receta_id"] or base is None else round(base, 4),
                      "propuesta": prop, "sacado": h["sacado"] if h else None, "sobro": h["sobro"] if h else None})
    return {"fecha": fecha, "comensales_registrados": registrados, "comensales_previstos": previstos,
            "confirmado": bool(hechos), "items": items}


def confirmar(con: sqlite3.Connection, fecha: str, items: list[dict], comensales: int | None, usuario: str | None) -> int | None:
    """items: [{etiqueta, sacado, sobro}]. Registra el consumo (sacado - sobró) y guarda lo sacado para aprender."""
    date.fromisoformat(fecha)
    atajos = {r["etiqueta"]: r for r in con.execute("SELECT * FROM atajos WHERE grupo='buffet'")}
    lineas = []
    for it in items:
        a = atajos.get(it["etiqueta"])
        sacado, sobro = float(it.get("sacado") or 0), float(it.get("sobro") or 0)
        if not a:
            raise ValueError(f"Concepto de buffet desconocido: {it['etiqueta']}")
        if sacado < 0 or sobro < 0 or sobro > sacado:
            raise ValueError(f"{it['etiqueta']}: lo que sobra no puede ser más de lo que se sacó")
        if sacado - sobro > 0:
            lineas.append({"receta_id": a["receta_id"], "cantidad": sacado - sobro} if a["receta_id"]
                          else {"producto": a["producto"], "cantidad": sacado - sobro})
    con.execute("DELETE FROM consumos WHERE fecha=? AND (ref=? OR ref=?)", (fecha, f"buffet:{fecha}", f"excel:ConsumoBuffet:{fecha}:consumo"))
    con.execute("DELETE FROM buffet_diario WHERE fecha=?", (fecha,))
    con.executemany("INSERT INTO buffet_diario VALUES(?,?,?,?,?)",
                    [(fecha, it["etiqueta"], float(it.get("sacado") or 0), float(it.get("sobro") or 0), comensales)
                     for it in items if it.get("sacado")])
    con.commit()
    if not lineas:
        costing.valorar(con)
        return None
    return consumos.registrar(con, fecha=fecha, servicio="desayuno", items=lineas, origen="manual", ref=f"buffet:{fecha}",
                              nota=f"Buffet del día ({len(lineas)} conceptos)", usuario=usuario)
