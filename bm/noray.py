"""Cierre para Noray (BC): la cantidad de cada producto en cada almacén de Noray a una fecha, sin contarlo todo.

BM da el total por ubicación física (último recuento + movimientos + consumos). Noray lleva el restaurante en varios
almacenes contables (DESAYUNO, SNACK BEBI, SNACK COMI...). El total se reparte así (decidido con el usuario el 13/10/2026):
  objetivo del almacén = lo que Noray tiene en él − lo que BM ha visto gastar a su centro desde el último inventario de Noray
y el total se reparte en proporción a esos objetivos. Administración pega «Cantidad física» en el diario de inventario
físico de Noray y lo registra; BM nunca registra en Noray por su cuenta.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from bm import consumos, inventario, prevision


def reparto(total: float, pesos: dict[str, float], entero: bool) -> dict[str, float]:
    """Reparte `total` en proporción a `pesos` (>0). Con `entero`, por restos mayores: 7 latas no salen 3,5 y 3,5."""
    suma = sum(pesos.values())
    bruto = {k: total * v / suma for k, v in pesos.items()}
    if not entero:
        return {k: round(v, 3) for k, v in bruto.items()}
    out = {k: int(v) for k, v in bruto.items()}
    for k in sorted(bruto, key=lambda k: bruto[k] - out[k], reverse=True)[: round(total) - sum(out.values())]:
        out[k] += 1
    return {k: float(v) for k, v in out.items()}


def _f(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}" if iso else ""


def cierre(con: sqlite3.Connection, hasta: str, ubicaciones=prevision.FB) -> list[dict]:
    fisica = dict(con.execute("SELECT codigo, ubicacion FROM almacenes_bc").fetchall())
    almacen_de_centro = {c: a for a, c in con.execute("SELECT codigo, centro FROM almacenes_bc WHERE centro IS NOT NULL")}
    centros_de = defaultdict(list)
    for c, a in almacen_de_centro.items():
        centros_de[a].append(c)

    usos = defaultdict(int)  # almacén de Noray más usado de cada ubicación: destino de lo que Noray no conoce allí
    for a, n in con.execute("SELECT almacen, COUNT(*) FROM bc_movs WHERE almacen<>'' GROUP BY 1"):
        usos[a] = n
    principal = {}
    for a, u in sorted(fisica.items()):
        if usos[a] > usos.get(principal.get(u), -1):
            principal[u] = a
    noray, ult_ajuste, entradas = defaultdict(dict), {}, defaultdict(float)
    for r in con.execute(
        """SELECT producto, almacen, SUM(cantidad) q, MAX(CASE WHEN tipo LIKE 'Ajuste%' THEN fecha END) aj,
                  SUM(CASE WHEN cantidad > 0 THEN cantidad ELSE 0 END) ent
           FROM bc_movs WHERE almacen<>'' AND fecha<=? GROUP BY 1, 2""", (hasta,)):
        u = fisica.get(r["almacen"], r["almacen"])
        if u in ubicaciones:
            noray[(r["producto"], u)][r["almacen"]] = r["q"]
            ult_ajuste[(r["producto"], r["almacen"])] = r["aj"]
            entradas[(r["producto"], r["almacen"])] = r["ent"]

    gastado = defaultdict(float)  # (producto, almacén) -> consumo de BM de su centro desde el último inventario de Noray
    for r in con.execute(
        """SELECT c.fecha, c.servicio, l.producto, SUM(l.cantidad) q FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id
           WHERE c.anulado=0 AND c.fecha<=? GROUP BY 1, 2, 3""", (hasta,)):
        a = almacen_de_centro.get(r["servicio"])
        if a and r["fecha"] > (ult_ajuste.get((r["producto"], a)) or ""):
            gastado[(r["producto"], a)] += r["q"]

    bm = {(s["producto"], s["ubicacion"]): s for u in ubicaciones for s in inventario.stock(con, u, hasta=hasta)}
    info = {r["codigo"]: r for r in con.execute("SELECT codigo, nombre, unidad FROM productos")}
    out = []
    for k in set(noray) | set(bm):
        p, u = k
        s = bm.get(k, {"stock": 0.0, "ultimo_recuento": None, "fuente_recuento": None})
        total = max(s["stock"], 0.0)
        en_noray = noray.get(k, {})
        pesos = {a: max(q - gastado[(p, a)], 0) for a, q in en_noray.items()}
        pesos = {a: v for a, v in pesos.items() if v > 1e-9} or {a: q for a, q in en_noray.items() if q > 1e-9}
        if not pesos:  # Noray no tiene nada: al almacén por donde suele entrar
            pesos = {max(en_noray, key=lambda a: entradas[(p, a)]) if en_noray else principal.get(u, u): 1.0}
        entero = abs(total - round(total)) < 1e-9 and all(abs(q - round(q)) < 1e-9 for q in en_noray.values())
        fisico = reparto(total, pesos, entero) if total > 0 else {}
        if s["fuente_recuento"] == "recuento":
            origen = f"Contado {_f(s['ultimo_recuento'])}"
        else:
            origen = f"Calculado por BM (inventario Noray {_f(s['ultimo_recuento'])})" if s["ultimo_recuento"] else "Calculado por BM"
        if s["stock"] < -1e-6:
            origen += " · stock negativo: falta registrar alguna entrada"
        for a in sorted(set(en_noray) | set(fisico)):
            calc, fis = round(en_noray.get(a, 0.0), 3), fisico.get(a, 0.0)
            if abs(calc) < 1e-9 and abs(fis) < 1e-9:
                continue
            pr = info.get(p)
            out.append({"almacen": a, "ubicacion": u, "producto": p, "nombre": pr["nombre"] if pr else p,
                        "unidad": pr["unidad"] if pr else None, "calculada": calc, "fisica": fis,
                        "diferencia": round(fis - calc, 3), "origen": origen})
    precios: dict = {}
    for x in out:
        pu = precios.setdefault(x["producto"], consumos.precio_actual(con, x["producto"], hasta))
        x["valor_diferencia"] = None if pu is None else round(x["diferencia"] * pu, 2)
    return sorted(out, key=lambda x: (x["almacen"], x["producto"]))
