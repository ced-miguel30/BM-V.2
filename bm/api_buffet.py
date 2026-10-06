"""API del buffet del día."""

from __future__ import annotations

from datetime import date

from fastapi import Depends
from pydantic import BaseModel

from bm import buffet
from bm.app import OPERATIVO, _error, app, con, requiere


@app.get("/api/buffet")
def ver(fecha: str | None = None, u: dict = Depends(requiere(*OPERATIVO))):
    return _error(buffet.propuesta, con, fecha or date.today().isoformat())


class Linea(BaseModel):
    etiqueta: str
    sacado: float | None = None
    sobro: float | None = None


class Confirmacion(BaseModel):
    fecha: str
    comensales: int | None = None
    items: list[Linea]


@app.post("/api/buffet")
def confirmar(d: Confirmacion, u: dict = Depends(requiere(*OPERATIVO))):
    cid = _error(buffet.confirmar, con, d.fecha, [i.model_dump() for i in d.items], d.comensales, u["nombre"])
    return {"id": cid}
