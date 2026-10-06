"""API de inventario: centros, ubicaciones, stock, recuentos, traslados y caducidades.
Se registra sobre la app de bm.app (importado al final de ese módulo)."""

from __future__ import annotations

from datetime import date

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from bm import consumos, inventario
from bm.app import GESTION, OPERATIVO, _error, app, con, requiere


@app.get("/api/centros")
def centros(u: dict = Depends(requiere(*OPERATIVO))):
    return [dict(x) for x in con.execute("SELECT * FROM centros ORDER BY orden, nombre")]


@app.get("/api/ubicaciones")
def ubicaciones(u: dict = Depends(requiere(*OPERATIVO))):
    return [dict(x) for x in con.execute(
        """SELECT u.*, (SELECT COUNT(*) FROM bc_movs m WHERE m.almacen=u.codigo) movimientos
           FROM ubicaciones u ORDER BY movimientos DESC, u.nombre""")]


@app.get("/api/stock")
def stock(ubicacion: str | None = None, u: dict = Depends(requiere(*OPERATIVO))):
    filas = inventario.stock(con, ubicacion)
    info = {r["codigo"]: r for r in con.execute("SELECT codigo, nombre, unidad, categoria FROM productos")}
    ver_euros = u["rol"] in GESTION
    precios: dict[str, float | None] = {}
    out = []
    for f in filas:
        if abs(f["stock"]) < 1e-6 and f["desviacion"] in (None, 0) and not f["salidas_desde_recuento"]:
            continue  # producto que pasó por la ubicación pero ya no tiene nada que contar
        p = info.get(f["producto"])
        fila = {**f, "nombre": p["nombre"] if p else f["producto"], "unidad": p["unidad"] if p else None,
                "categoria": p["categoria"] if p else None}
        if ver_euros:
            pu = precios.setdefault(f["producto"], consumos.precio_actual(con, f["producto"]))
            fila["precio"] = pu
            fila["valor"] = None if pu is None else round(max(f["stock"], 0) * pu, 2)
            fila["desviacion_valor"] = None if pu is None or f["desviacion"] is None else round(f["desviacion"] * pu, 2)
        out.append(fila)
    return sorted(out, key=lambda x: (x["ubicacion"], x["nombre"]))


class LineaRecuento(BaseModel):
    producto: str
    contado: float


class NuevoRecuento(BaseModel):
    fecha: str
    ubicacion: str
    nota: str | None = None
    lineas: list[LineaRecuento]


@app.post("/api/recuentos")
def crear_recuento(d: NuevoRecuento, u: dict = Depends(requiere(*OPERATIVO))):
    rid = _error(inventario.registrar_recuento, con, fecha=d.fecha, ubicacion=d.ubicacion, nota=d.nota,
                 usuario=u["nombre"], lineas=[x.model_dump() for x in d.lineas])
    return {"id": rid}


@app.get("/api/recuentos")
def listar_recuentos(u: dict = Depends(requiere(*GESTION))):
    return [dict(x) for x in con.execute(
        """SELECT r.*, COUNT(l.producto) n_productos, ROUND(SUM(l.contado - l.teorico), 3) diferencia_uds
           FROM recuentos r LEFT JOIN recuento_lineas l ON l.recuento_id=r.id GROUP BY r.id ORDER BY r.fecha DESC, r.id DESC LIMIT 200""")]


@app.get("/api/recuentos/{rid}")
def ver_recuento(rid: int, u: dict = Depends(requiere(*GESTION))):
    r = con.execute("SELECT * FROM recuentos WHERE id=?", (rid,)).fetchone()
    if not r:
        raise HTTPException(404, "No existe")
    lineas = []
    for l in con.execute(
        """SELECT l.*, p.nombre, p.unidad FROM recuento_lineas l JOIN productos p ON p.codigo=l.producto
           WHERE l.recuento_id=? ORDER BY p.nombre""", (rid,)
    ):
        pu = consumos.precio_actual(con, l["producto"], r["fecha"])
        dif = l["contado"] - (l["teorico"] or 0)
        lineas.append({**dict(l), "diferencia": round(dif, 4), "diferencia_valor": None if pu is None else round(dif * pu, 2)})
    return {**dict(r), "lineas": lineas}


class NuevoTraslado(BaseModel):
    fecha: str
    origen: str
    destino: str
    nota: str | None = None
    items: list[dict]


@app.post("/api/traslados")
def crear_traslado(d: NuevoTraslado, u: dict = Depends(requiere(*OPERATIVO))):
    return {"id": _error(inventario.registrar_traslado, con, fecha=d.fecha, origen=d.origen, destino=d.destino,
                         nota=d.nota, usuario=u["nombre"], items=d.items)}


@app.get("/api/traslados")
def listar_traslados(u: dict = Depends(requiere(*OPERATIVO))):
    return {
        "traslados_en": inventario.ajuste(con, "traslados_en", "bc"),
        "lista": [dict(x) for x in con.execute(
            """SELECT t.*, COUNT(l.producto) n_productos FROM traslados t LEFT JOIN traslado_lineas l ON l.traslado_id=t.id
               GROUP BY t.id ORDER BY t.fecha DESC, t.id DESC LIMIT 200""")],
    }


class Anulacion(BaseModel):
    motivo: str


@app.post("/api/{tabla}/{id_}/anular")
def anular(tabla: str, id_: int, d: Anulacion, u: dict = Depends(requiere(*GESTION))):
    if tabla not in ("traslados", "recuentos"):
        raise HTTPException(404, "No encontrado")
    _error(inventario.anular, con, tabla, id_, d.motivo, u["nombre"])
    return {"ok": True}


class NuevaCaducidad(BaseModel):
    producto: str
    ubicacion: str | None = None
    cantidad: float
    caduca: str
    nota: str | None = None


@app.get("/api/caducidades")
def listar_caducidades(estado: str = "activa", u: dict = Depends(requiere(*OPERATIVO))):
    hoy = date.today()
    out = []
    for c in con.execute(
        """SELECT c.*, p.nombre, p.unidad FROM caducidades c JOIN productos p ON p.codigo=c.producto
           WHERE c.estado=? ORDER BY c.caduca LIMIT 500""", (estado,)
    ):
        out.append({**dict(c), "dias": (date.fromisoformat(c["caduca"]) - hoy).days})
    return out


@app.post("/api/caducidades")
def crear_caducidad(d: NuevaCaducidad, u: dict = Depends(requiere(*OPERATIVO))):
    return {"id": _error(inventario.registrar_caducidad, con, usuario=u["nombre"], **d.model_dump())}


class Cierre(BaseModel):
    estado: str


@app.post("/api/caducidades/{cid}/cerrar")
def cerrar_caducidad(cid: int, d: Cierre, u: dict = Depends(requiere(*OPERATIVO))):
    _error(inventario.cerrar_caducidad, con, cid, d.estado, u["nombre"])
    return {"ok": True}
