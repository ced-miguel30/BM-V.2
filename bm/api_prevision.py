"""API de previsión: pedidos por proveedor, reposición del restaurante, lo más vendido y ajustes por producto."""

from __future__ import annotations

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from bm import prevision
from bm.app import GESTION, OPERATIVO, app, con, requiere


@app.get("/api/prevision/pedidos")
def pedidos(u: dict = Depends(requiere(*GESTION))):
    return prevision.pedidos(con)


@app.get("/api/prevision/reposicion")
def reposicion(u: dict = Depends(requiere(*OPERATIVO))):
    return prevision.reposicion(con)


@app.get("/api/prevision/favoritos")
def favoritos(u: dict = Depends(requiere(*GESTION))):
    return prevision.favoritos(con)


class Parametros(BaseModel):
    stock_minimo: float | None = None
    minimo_restaurante: float | None = None
    lote: float | None = None
    no_pedir: bool = False


@app.get("/api/parametros/{producto}")
def ver_parametros(producto: str, u: dict = Depends(requiere(*GESTION))):
    r = con.execute("SELECT * FROM parametros_producto WHERE producto=?", (producto,)).fetchone()
    calc = prevision.analizar(con, {"HOTEL": prevision.FB, "RESTAURANTE": ("RESTAURANTE",)})
    return {"manual": dict(r) if r else None,
            "hotel": calc.get((producto, "HOTEL")), "restaurante": calc.get((producto, "RESTAURANTE"))}


@app.put("/api/parametros/{producto}")
def guardar_parametros(producto: str, d: Parametros, u: dict = Depends(requiere(*GESTION))):
    if not con.execute("SELECT 1 FROM productos WHERE codigo=?", (producto,)).fetchone():
        raise HTTPException(404, "Producto desconocido")
    if any(x is not None and x < 0 for x in (d.stock_minimo, d.minimo_restaurante, d.lote)):
        raise HTTPException(400, "Valores negativos no")
    con.execute("INSERT OR REPLACE INTO parametros_producto VALUES(?,?,?,?,?)",
                (producto, d.stock_minimo, d.minimo_restaurante, d.lote, int(d.no_pedir)))
    con.commit()
    return {"ok": True}
