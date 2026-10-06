"""API de comandas de desayuno (tablet de cocina)."""

from __future__ import annotations

from datetime import date

from fastapi import Depends
from pydantic import BaseModel

from bm import comandas
from bm.app import OPERATIVO, _error, app, con, requiere


@app.get("/api/comandas")
def ver(fecha: str | None = None, u: dict = Depends(requiere(*OPERATIVO))):
    return {**comandas.dia(con, fecha or date.today().isoformat()), "catalogo": comandas.catalogo(con)}


class Linea(BaseModel):
    fecha: str
    nombre: str
    cantidad: float = 1
    extras: list[tuple[str, float]] = []
    omitir: list[str] = []


@app.post("/api/comandas")
def anadir(d: Linea, u: dict = Depends(requiere(*OPERATIVO))):
    lid = _error(comandas.anadir, con, fecha=d.fecha, nombre=d.nombre, cantidad=d.cantidad, extras=d.extras, omitir=d.omitir, usuario=u["nombre"])
    return comandas.dia(con, d.fecha) | {"id": lid}


@app.delete("/api/comandas/{lid}")
def quitar(lid: int, u: dict = Depends(requiere(*OPERATIVO))):
    fecha = con.execute("SELECT fecha FROM comanda_lineas WHERE id=?", (lid,)).fetchone()
    _error(comandas.quitar, con, lid)
    return comandas.dia(con, fecha[0])


class Comensales(BaseModel):
    fecha: str
    comensales: int


@app.put("/api/comandas/comensales")
def comensales(d: Comensales, u: dict = Depends(requiere(*OPERATIVO))):
    _error(comandas.poner_comensales, con, d.fecha, d.comensales)
    return comandas.dia(con, d.fecha)
