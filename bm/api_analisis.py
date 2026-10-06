"""API de análisis para dirección (solo gestión)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from fastapi import Depends

from bm import analisis, inventario
from bm.app import GESTION, app, con, requiere


def _nombres():
    return {r["codigo"]: (r["nombre"], r["unidad"]) for r in con.execute("SELECT codigo, nombre, unidad FROM productos")}


@app.get("/api/analisis/rentabilidad")
def rentabilidad(desde: str, hasta: str, u: dict = Depends(requiere(*GESTION))):
    return {"igic": round(analisis.igic(con) * 100, 2), "objetivo_food_cost": float(inventario.ajuste(con, "objetivo_food_cost", "30")),
            "platos": analisis.rentabilidad(con, desde, hasta)}


@app.get("/api/analisis/control")
def control(desde: str, hasta: str, ubicacion: str | None = None, u: dict = Depends(requiere(*GESTION))):
    det = analisis.desviaciones(con, desde, hasta, ubicacion)
    nombres = _nombres()
    por_producto = defaultdict(lambda: {"diferencia": 0.0, "valor": 0.0, "recuentos": 0})
    por_ubicacion, por_mes = defaultdict(float), defaultdict(float)
    for d in det:
        k = (d["producto"], d["ubicacion"])
        por_producto[k]["diferencia"] += d["diferencia"]
        por_producto[k]["valor"] += d["valor"] or 0
        por_producto[k]["recuentos"] += 1
        por_ubicacion[d["ubicacion"]] += d["valor"] or 0
        por_mes[d["fecha"][:7]] += d["valor"] or 0
    productos = [{"producto": p, "ubicacion": ub, "nombre": nombres.get(p, (p, None))[0], "unidad": nombres.get(p, (p, None))[1],
                  "diferencia": round(v["diferencia"], 3), "valor": round(v["valor"], 2), "recuentos": v["recuentos"]}
                 for (p, ub), v in por_producto.items()]
    return {
        "productos": sorted(productos, key=lambda x: x["valor"]),
        "por_ubicacion": sorted(({"ubicacion": k, "valor": round(v, 2)} for k, v in por_ubicacion.items()), key=lambda x: x["valor"]),
        "por_mes": [{"mes": k, "valor": round(v, 2)} for k, v in sorted(por_mes.items())],
        "total": round(sum(por_ubicacion.values()), 2),
    }


@app.get("/api/analisis/precios")
def precios(dias: int = 90, u: dict = Depends(requiere(*GESTION))):
    return {"variaciones": analisis.variacion_precios(con, dias), "dudosos": analisis.precios_dudosos(con)}


@app.get("/api/analisis/tendencia")
def tendencia(meses: int = 12, u: dict = Depends(requiere(*GESTION))):
    return {"meses": analisis.tendencia(con, meses), "objetivo_food_cost": float(inventario.ajuste(con, "objetivo_food_cost", "30")),
            "hoy": date.today().isoformat()}


@app.get("/api/analisis/perdidas")
def perdidas(desde: str, hasta: str, u: dict = Depends(requiere(*GESTION))):
    from bm.consumos import MOTIVOS_MERMA
    return {**analisis.perdidas(con, desde, hasta), "motivos": MOTIVOS_MERMA}


@app.get("/api/analisis/fichas")
def fichas(u: dict = Depends(requiere(*GESTION))):
    return analisis.revision_fichas(con)
