"""API de avisos, cierre de mes e informe mensual."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from fastapi import Depends

from bm import analisis, avisos, cierre, inventario, noray
from bm.app import CONTAR, GESTION, _resumen, app, con, requiere, usuario


@app.get("/api/avisos")
def ver_avisos(u: dict = Depends(usuario)):
    return avisos.avisos(con, u["rol"])


@app.get("/api/cierre")
def ver_cierre(mes: str, u: dict = Depends(requiere(*GESTION))):
    return cierre.estado(con, mes)


@app.get("/api/cierre/informe")
def informe(mes: str, u: dict = Depends(requiere(*GESTION))):
    ini, fin = cierre._limites(mes)
    a, b = ini.isoformat(), fin.isoformat()
    platos = analisis.rentabilidad(con, a, b)
    control = analisis.desviaciones(con, a, b)
    nombres = dict(con.execute("SELECT codigo, nombre FROM productos").fetchall())
    por_prod = Counter()
    for d in control:
        por_prod[d["producto"]] += d["valor"] or 0
    return {
        "mes": mes, "estado": cierre.estado(con, mes),
        "resumen": _resumen(a, (fin + timedelta(days=1)).isoformat()),
        "objetivo_food_cost": float(inventario.ajuste(con, "objetivo_food_cost", "30")),
        "centros": [dict(x) for x in con.execute("SELECT codigo, nombre, tipo FROM centros ORDER BY orden")],
        "perdidas": {k: v for k, v in analisis.perdidas(con, a, b).items() if k != "platos_que_no_salen"},
        "clases": dict(Counter(p.get("clase") for p in platos if p.get("clase"))),
        "estrellas": [p for p in platos if p.get("clase") == "estrella"][:5],
        "perros": [p for p in platos if p.get("clase") == "perro"][:5],
        "desviaciones": [{"producto": p, "nombre": nombres.get(p, p), "valor": round(v, 2)} for p, v in por_prod.most_common()[:-11:-1] if v < 0],
        "compras": [dict(x) for x in con.execute(
            """SELECT proveedor, COUNT(DISTINCT documento) documentos, ROUND(SUM(coste_total), 2) importe FROM bc_movs
               WHERE tipo='Compra' AND fecha>=? AND fecha<=? GROUP BY 1 ORDER BY 3 DESC LIMIT 10""", (a, b))],
        "precios": analisis.variacion_precios(con)[:5],
    }


@app.get("/api/cierre/noray")
def cierre_noray(mes: str, u: dict = Depends(requiere(*GESTION))):
    """Cantidad física por almacén de Noray a fin de mes (o a hoy si el mes no ha terminado), para su diario de inventario."""
    fin = min(cierre._limites(mes)[1], date.today())
    return {"fecha": fin.isoformat(), "lineas": noray.cierre(con, fin.isoformat())}


@app.get("/api/cierre/recomendados")
def recomendados(ubicacion: str, desde: str | None = None, u: dict = Depends(requiere(*CONTAR))):
    """Fresco y caro sin contar desde `desde` (por defecto, desde el día 1 de este mes)."""
    xs = cierre.recomendados(con, ubicacion, desde or date.today().replace(day=1).isoformat())
    if u["rol"] not in GESTION:  # el jefe ve cuánto espera BM pero no lo que vale; el resto, solo qué contar
        campos = ("producto", "nombre", "unidad", "motivos") + (("stock", "ultimo_recuento") if u["rol"] == "jefe" else ())
        xs = [{k: x[k] for k in campos} for x in xs]
    return xs


@app.get("/api/anomalias")
def anomalias(u: dict = Depends(requiere(*GESTION))):
    return analisis.anomalias(con)
