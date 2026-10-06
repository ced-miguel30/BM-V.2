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


@app.get("/api/desayunos")
def historial(desde: str, hasta: str, u: dict = Depends(requiere(*OPERATIVO))):
    """Registro de desayunos día a día (comandas, Excel o histórico), con coste solo para gestión."""
    filas = [dict(x) for x in con.execute(
        """SELECT c.fecha, (SELECT SUM(c2.comensales) FROM consumos c2 WHERE c2.fecha=c.fecha AND c2.servicio='desayuno'
                AND c2.anulado=0 AND c2.tipo='consumo') comensales,
             GROUP_CONCAT(DISTINCT c.origen) origen, ROUND(SUM(l.coste), 2) coste,
             (SELECT COUNT(*) FROM comanda_lineas k WHERE k.fecha=c.fecha AND k.anulada=0) comandas,
             (SELECT COUNT(*) FROM buffet_diario b WHERE b.fecha=c.fecha) buffet
           FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id
           WHERE c.anulado=0 AND c.servicio='desayuno' AND c.fecha>=? AND c.fecha<=? GROUP BY c.fecha ORDER BY c.fecha DESC""", (desde, hasta))]
    for f in filas:
        f["coste_comensal"] = round(f["coste"] / f["comensales"], 2) if f["comensales"] else None
        if u["rol"] not in ("direccion", "administracion"):
            f.pop("coste"), f.pop("coste_comensal")
    return filas
