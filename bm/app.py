"""Servidor web de BM. Un solo proceso escribe en SQLite; los PCs y móviles entran por navegador.

    python -m bm.servidor       -> http://<servidor>:8000
"""

from __future__ import annotations

import os
import secrets
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, Response as RawResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bm import analisis, bc, consumos, costing, db, excel, inventario, plantilla, tpv
from bm.passwords import verify_password

con = db.connect()
app = FastAPI(title="BM", docs_url="/api/docs", openapi_url="/api/openapi.json")
STATIC = Path(__file__).resolve().parent / "static"

# ---------------------------------------------------------------- sesión y permisos
_SESIONES: dict[str, dict] = {}  # ponytail: en memoria; reiniciar el servidor obliga a volver a entrar
GESTION = ("direccion", "administracion")
OPERATIVO = GESTION + ("recepcion", "restaurante")


def usuario(request: Request) -> dict:
    u = _SESIONES.get(request.cookies.get("bm_sesion", ""))
    if not u:
        raise HTTPException(401, "Sesión no iniciada")
    return u


def requiere(*roles):
    def dep(u: dict = Depends(usuario)) -> dict:
        if u["rol"] not in roles:
            raise HTTPException(403, "Sin permiso para esta acción")
        return u
    return dep


def _error(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


class Login(BaseModel):
    login: str
    password: str


@app.post("/api/login")
def login(datos: Login, response: Response):
    u = con.execute("SELECT * FROM usuarios WHERE login=? AND activo=1", (datos.login.strip().lower(),)).fetchone()
    if not u or not verify_password(datos.password, u["password_hash"]):
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    token = secrets.token_urlsafe(32)
    _SESIONES[token] = {"id": u["id"], "nombre": u["nombre"], "rol": u["rol"], "login": u["login"]}
    response.set_cookie("bm_sesion", token, httponly=True, samesite="lax", max_age=60 * 60 * 12)
    return _SESIONES[token]


@app.post("/api/logout")
def logout(request: Request, response: Response):
    _SESIONES.pop(request.cookies.get("bm_sesion", ""), None)
    response.delete_cookie("bm_sesion")
    return {"ok": True}


@app.get("/api/me")
def me(u: dict = Depends(usuario)):
    return u


# ---------------------------------------------------------------- panel
def _mes(mes: str | None) -> tuple[str, str, str]:
    mes = mes or date.today().strftime("%Y-%m")
    y, m = map(int, mes.split("-"))
    ini = date(y, m, 1)
    fin = (ini + timedelta(days=32)).replace(day=1)
    return mes, ini.isoformat(), fin.isoformat()


def _resumen(ini: str, fin: str) -> dict:
    tipos = dict(con.execute("SELECT codigo, tipo FROM centros").fetchall())
    r = {c: 0.0 for c in tipos}
    r["mermas"] = 0.0
    for x in con.execute(
        """SELECT c.servicio, c.tipo, SUM(l.coste) coste FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id
           WHERE c.anulado=0 AND c.fecha>=? AND c.fecha<? GROUP BY 1,2""", (ini, fin)
    ):
        if x["tipo"] == "merma":
            r["mermas"] += x["coste"] or 0
        elif x["servicio"] in r:
            r[x["servicio"]] += x["coste"] or 0
    r["restauracion"] = sum(r[c] for c, t in tipos.items() if t == "restauracion")
    r["departamentos"] = sum(r[c] for c, t in tipos.items() if t == "departamento")
    r["consumo"] = r["restauracion"] + r["departamentos"]
    r["ventas_tpv"] = con.execute("SELECT COALESCE(SUM(importe),0) FROM tpv_ventas WHERE fecha>=? AND fecha<?", (ini, fin)).fetchone()[0]
    coste_tpv = con.execute(
        """SELECT COALESCE(SUM(l.coste),0) FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id
           WHERE c.origen='tpv' AND c.fecha>=? AND c.fecha<?""", (ini, fin)).fetchone()[0]
    r["coste_tpv"] = coste_tpv
    # Food cost sobre venta NETA (los importes del TPV llevan IGIC)
    r["ventas_netas"] = r["ventas_tpv"] / (1 + analisis.igic(con))
    r["food_cost_pct"] = round(100 * coste_tpv / r["ventas_netas"], 1) if r["ventas_netas"] else None
    com = con.execute(
        "SELECT COALESCE(SUM(comensales),0) FROM consumos WHERE anulado=0 AND servicio='desayuno' AND tipo='consumo' AND fecha>=? AND fecha<?",
        (ini, fin)).fetchone()[0]
    r["comensales_desayuno"] = com
    r["coste_por_comensal"] = round(r["desayuno"] / com, 2) if com else None
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()}


@app.get("/api/panel")
def panel(mes: str | None = None, u: dict = Depends(requiere(*GESTION))):
    mes, ini, fin = _mes(mes)
    y, m = map(int, mes.split("-"))
    prev = f"{y - (m == 1)}-{12 if m == 1 else m - 1:02d}"
    _, pini, pfin = _mes(prev)
    hoy_iso = date.today().isoformat()
    if ini <= hoy_iso < fin:
        # Mes en curso: se compara con los mismos días del mes anterior, no con el mes entero.
        dias = (date.today() - date.fromisoformat(ini)).days + 1
        pfin = min(pfin, (date.fromisoformat(pini) + timedelta(days=dias)).isoformat())
    serie = [dict(x) for x in con.execute(
        """SELECT c.fecha, c.servicio, ROUND(SUM(l.coste),2) coste FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id
           WHERE c.anulado=0 AND c.tipo='consumo' AND c.fecha>=? AND c.fecha<? GROUP BY 1,2 ORDER BY 1""", (ini, fin))]
    top = [dict(x) for x in con.execute(
        """SELECT l.producto codigo, p.nombre, p.unidad, ROUND(SUM(l.cantidad),2) cantidad, ROUND(SUM(l.coste),2) coste
           FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id JOIN productos p ON p.codigo=l.producto
           WHERE c.anulado=0 AND c.fecha>=? AND c.fecha<? GROUP BY 1 ORDER BY coste DESC LIMIT 10""", (ini, fin))]
    hoy = date.today()
    d0, d1 = date.fromisoformat(ini), date.fromisoformat(fin)
    dias_mes = [d0 + timedelta(days=i) for i in range((d1 - d0).days)]
    con_desayuno = {x[0] for x in con.execute(
        "SELECT DISTINCT fecha FROM consumos WHERE anulado=0 AND servicio='desayuno' AND fecha>=? AND fecha<?", (ini, fin))}
    pend = tpv.pendientes(con)
    alertas = {
        "dias_sin_desayuno": [d.isoformat() for d in dias_mes if d < hoy and d.isoformat() not in con_desayuno],
        "tpv_pendientes": len(pend),
        "tpv_pendiente_importe": round(sum(p["importe"] for p in pend), 2),
        "lineas_por_estado": dict(con.execute(
            """SELECT l.coste_estado, COUNT(*) FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id
               WHERE c.anulado=0 AND c.fecha>=? AND c.fecha<? GROUP BY 1""", (ini, fin)).fetchall()),
        "ultimo_movimiento_bc": con.execute("SELECT MAX(fecha) FROM bc_movs WHERE fecha<=?", (hoy.isoformat(),)).fetchone()[0],
        "ultimo_inventario_bc": con.execute(
            "SELECT MAX(fecha) FROM bc_movs WHERE tipo LIKE 'Ajuste%' AND fecha<=?", (hoy.isoformat(),)).fetchone()[0],
    }
    return {"mes": mes, "actual": _resumen(ini, fin), "anterior": _resumen(pini, pfin), "comparado_hasta": pfin,
            "objetivo_food_cost": float(inventario.ajuste(con, "objetivo_food_cost", "30")), "serie": serie, "top": top, "alertas": alertas}


# ---------------------------------------------------------------- consumos
@app.get("/api/consumos")
def listar_consumos(desde: str, hasta: str, servicio: str | None = None, tipo: str | None = None,
                    u: dict = Depends(requiere(*GESTION))):
    q = """SELECT c.*, COUNT(l.id) n_lineas, ROUND(SUM(l.coste),2) coste,
             MAX(CASE l.coste_estado WHEN 'sin_precio' THEN 3 WHEN 'sin_stock' THEN 2 WHEN 'provisional' THEN 1 ELSE 0 END) peor
           FROM consumos c LEFT JOIN consumo_lineas l ON l.consumo_id=c.id WHERE c.fecha>=? AND c.fecha<=?"""
    args = [desde, hasta]
    if servicio:
        q += " AND c.servicio=?"
        args.append(servicio)
    if tipo:
        q += " AND c.tipo=?"
        args.append(tipo)
    return [dict(x) for x in con.execute(q + " GROUP BY c.id ORDER BY c.fecha DESC, c.id DESC", args)]


@app.get("/api/consumos/{cid}")
def ver_consumo(cid: int, u: dict = Depends(requiere(*GESTION))):
    c = con.execute("SELECT * FROM consumos WHERE id=?", (cid,)).fetchone()
    if not c:
        raise HTTPException(404, "No existe")
    lineas = []
    for l in con.execute(
        """SELECT l.*, p.nombre, p.unidad, r.nombre receta FROM consumo_lineas l JOIN productos p ON p.codigo=l.producto
           LEFT JOIN recetas r ON r.id=l.receta_id WHERE l.consumo_id=? ORDER BY r.nombre, p.nombre""", (cid,)
    ):
        traza = [dict(a) for a in con.execute(
            """SELECT a.cantidad, a.coste_unit, m.documento, m.fecha, m.proveedor, m.tipo_doc
               FROM asignaciones a LEFT JOIN bc_movs m ON m.n_mov=a.n_mov WHERE a.linea_id=?""", (l["id"],))]
        lineas.append({**dict(l), "traza": traza})
    return {**dict(c), "lineas": lineas}


class Item(BaseModel):
    receta_id: str | None = None
    producto: str | None = None
    cantidad: float


class NuevoConsumo(BaseModel):
    fecha: str
    servicio: str | None = None
    tipo: str = "consumo"
    comensales: int | None = None
    nota: str | None = None
    ubicacion: str | None = None
    items: list[Item]


@app.post("/api/consumos")
def crear_consumo(d: NuevoConsumo, u: dict = Depends(requiere(*OPERATIVO))):
    cid = _error(consumos.registrar, con, fecha=d.fecha, servicio=d.servicio, tipo=d.tipo, comensales=d.comensales,
                 nota=d.nota, usuario=u["nombre"], ubicacion=d.ubicacion, items=[i.model_dump() for i in d.items])
    return {"id": cid}


class Anulacion(BaseModel):
    motivo: str


@app.post("/api/consumos/{cid}/anular")
def anular_consumo(cid: int, d: Anulacion, u: dict = Depends(requiere(*GESTION))):
    if not d.motivo.strip():
        raise HTTPException(400, "Indica el motivo")
    _error(consumos.anular, con, cid, d.motivo.strip(), u["nombre"])
    return {"ok": True}


@app.get("/api/catalogo")
def catalogo(u: dict = Depends(requiere(*OPERATIVO))):
    """Lo que se puede registrar: recetas activas y productos de alimentación/bebida."""
    return {
        "recetas": [dict(x) for x in con.execute("SELECT id, nombre, servicio FROM recetas WHERE activo=1 ORDER BY nombre")],
        "productos": [dict(x) for x in con.execute(
            """SELECT codigo, nombre, unidad FROM productos WHERE activo=1 AND es_tpv=0
               AND (categoria LIKE '1%' OR origen='bm2' OR codigo IN (SELECT producto FROM receta_lineas)) ORDER BY nombre""")],
    }


# ---------------------------------------------------------------- productos y recetas
@app.get("/api/productos")
def listar_productos(q: str = "", u: dict = Depends(requiere(*GESTION))):
    like = f"%{q.strip()}%"
    return [dict(x) for x in con.execute(
        """SELECT p.codigo, p.nombre, p.unidad, p.categoria, p.origen,
             (SELECT ROUND(SUM(cantidad),2) FROM bc_movs m WHERE m.producto=p.codigo) stock_bc,
             (SELECT MAX(fecha) FROM bc_movs m WHERE m.producto=p.codigo AND m.tipo='Compra' AND m.cantidad>0) ultima_compra,
             (SELECT ABS(coste_total/cantidad) FROM bc_movs m WHERE m.producto=p.codigo AND m.tipo='Compra' AND m.cantidad>0
                AND m.coste_total>0 ORDER BY fecha DESC, n_mov DESC LIMIT 1) ultimo_precio
           FROM productos p WHERE p.es_tpv=0 AND (p.nombre LIKE ? OR p.codigo LIKE ?)
             AND (p.categoria LIKE '1%' OR p.origen='bm2' OR ?<>'')
           ORDER BY p.nombre LIMIT 300""", (like, like, q.strip()))]


@app.get("/api/productos/{codigo}")
def ver_producto(codigo: str, u: dict = Depends(requiere(*GESTION))):
    p = con.execute("SELECT * FROM productos WHERE codigo=?", (codigo,)).fetchone()
    if not p:
        raise HTTPException(404, "No existe")
    movs = [dict(x) for x in con.execute(
        """SELECT n_mov, fecha, tipo, tipo_doc, documento, proveedor, almacen, cantidad,
             CASE WHEN cantidad<>0 AND coste_total<>0 THEN ABS(coste_total/cantidad) ELSE coste_unit END coste_unit
           FROM bc_movs WHERE producto=? AND tipo<>'Transferencia' ORDER BY fecha DESC, n_mov DESC LIMIT 200""", (codigo,))]
    consumo = [dict(x) for x in con.execute(
        """SELECT substr(c.fecha,1,7) mes, c.servicio, ROUND(SUM(l.cantidad),3) cantidad, ROUND(SUM(l.coste),2) coste
           FROM consumo_lineas l JOIN consumos c ON c.id=l.consumo_id WHERE l.producto=? AND c.anulado=0
           GROUP BY 1,2 ORDER BY 1""", (codigo,))]
    recetas = [dict(x) for x in con.execute(
        "SELECT r.id, r.nombre, l.cantidad FROM receta_lineas l JOIN recetas r ON r.id=l.receta_id WHERE l.producto=?", (codigo,))]
    return {**dict(p), "precio_actual": consumos.precio_actual(con, codigo), "movimientos": movs, "consumo": consumo, "recetas": recetas}


@app.get("/api/recetas")
def listar_recetas(u: dict = Depends(requiere(*GESTION))):
    out = []
    for r in con.execute("SELECT id FROM recetas ORDER BY nombre"):
        c = consumos.coste_receta(con, r["id"])
        c["n_ingredientes"] = len(c.pop("lineas"))
        out.append(c)
    return out


@app.get("/api/recetas/{rid}")
def ver_receta(rid: str, u: dict = Depends(requiere(*GESTION))):
    if not con.execute("SELECT 1 FROM recetas WHERE id=?", (rid,)).fetchone():
        raise HTTPException(404, "No existe")
    return consumos.coste_receta(con, rid)


class LineaReceta(BaseModel):
    producto: str
    cantidad: float


class Receta(BaseModel):
    nombre: str
    servicio: str | None = None
    porciones: float = 1
    activo: bool = True
    lineas: list[LineaReceta]


def _guardar_receta(rid: str, d: Receta) -> None:
    if not d.nombre.strip() or d.porciones <= 0:
        raise HTTPException(400, "Nombre y porciones son obligatorios")
    con.execute(
        """INSERT INTO recetas(id, nombre, servicio, porciones, activo) VALUES(?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET nombre=excluded.nombre, servicio=excluded.servicio,
             porciones=excluded.porciones, activo=excluded.activo""",
        (rid, d.nombre.strip(), d.servicio, d.porciones, int(d.activo)),
    )
    con.execute("DELETE FROM receta_lineas WHERE receta_id=?", (rid,))
    con.executemany("INSERT INTO receta_lineas VALUES(?,?,?)", [(rid, l.producto, l.cantidad) for l in d.lineas if l.cantidad > 0])
    con.commit()
    # Las recetas usadas por el TPV cambian el consumo calculado: se regenera y revalora.
    tpv.regenerar(con)
    costing.valorar(con)


@app.post("/api/recetas")
def crear_receta(d: Receta, u: dict = Depends(requiere(*GESTION))):
    rid = "r" + secrets.token_hex(4)
    _guardar_receta(rid, d)
    return {"id": rid}


@app.put("/api/recetas/{rid}")
def editar_receta(rid: str, d: Receta, u: dict = Depends(requiere(*GESTION))):
    _guardar_receta(rid, d)
    return {"id": rid}


# ---------------------------------------------------------------- TPV
@app.get("/api/tpv/articulos")
def tpv_articulos(u: dict = Depends(requiere(*GESTION))):
    return [dict(x) for x in con.execute(
        """SELECT a.*, r.nombre receta, p.nombre producto_nombre, p.unidad producto_unidad,
              ROUND(SUM(v.importe),2) importe, COUNT(DISTINCT v.fecha) dias
            FROM tpv_articulos a JOIN tpv_ventas v ON v.codigo=a.codigo
            LEFT JOIN recetas r ON r.id=a.receta_id LEFT JOIN productos p ON p.codigo=a.producto
            GROUP BY a.codigo
            ORDER BY (a.receta_id IS NULL AND a.producto IS NULL AND a.ignorar=0) DESC, importe DESC""")]


class Asignacion(BaseModel):
    receta_id: str | None = None
    producto: str | None = None
    factor: float = 1
    servicio: str
    precio: float | None = None
    ignorar: bool = False


@app.put("/api/tpv/articulos/{codigo}")
def tpv_asignar(codigo: str, d: Asignacion, u: dict = Depends(requiere(*GESTION))):
    if d.receta_id and d.producto:
        raise HTTPException(400, "Elige receta o producto, no ambos")
    if not consumos.centro_valido(con, d.servicio):
        raise HTTPException(400, "Servicio no válido")
    con.execute(
        "UPDATE tpv_articulos SET receta_id=?, producto=?, factor=?, servicio=?, precio=?, ignorar=? WHERE codigo=?",
        (d.receta_id, d.producto, d.factor, d.servicio, d.precio, int(d.ignorar), codigo),
    )
    con.commit()
    fechas = [r[0] for r in con.execute("SELECT DISTINCT fecha FROM tpv_ventas WHERE codigo=?", (codigo,))]
    tpv.regenerar(con, fechas)
    costing.valorar(con)
    return {"ok": True, "dias_recalculados": len(fechas)}


def _subida(f: UploadFile) -> Path:
    tmp = Path(tempfile.mkdtemp()) / Path(f.filename or "subida").name
    with tmp.open("wb") as out:
        shutil.copyfileobj(f.file, out)
    return tmp


@app.post("/api/tpv/pdf")
def tpv_subir(archivo: UploadFile, u: dict = Depends(requiere(*GESTION, "recepcion"))):
    r = _error(tpv.importar_pdf, con, _subida(archivo))
    costing.valorar(con)
    return {**r, "pendientes": len(tpv.pendientes(con))}


@app.get("/api/tpv/ventas")
def tpv_ventas(mes: str | None = None, u: dict = Depends(requiere(*GESTION))):
    _, ini, fin = _mes(mes)
    return [dict(x) for x in con.execute(
        """SELECT v.fecha, a.servicio, ROUND(SUM(v.importe),2) importe FROM tpv_ventas v JOIN tpv_articulos a ON a.codigo=v.codigo
           WHERE v.fecha>=? AND v.fecha<? GROUP BY 1,2 ORDER BY 1""", (ini, fin))]


# ---------------------------------------------------------------- Excel operativo
@app.get("/api/excel/plantilla")
def excel_plantilla(u: dict = Depends(requiere(*OPERATIVO))):
    return RawResponse(
        plantilla.generar(con),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="registro_operativo_{date.today():%Y%m%d}.xlsx"'},
    )


@app.post("/api/excel")
def excel_importar(archivo: UploadFile, confirmar: bool = False, u: dict = Depends(requiere(*OPERATIVO))):
    """Sin confirmar: vista previa (no escribe). Con confirmar: importa los días sin errores."""
    try:
        r = excel.importar(con, _subida(archivo), usuario=u["nombre"], confirmar=confirmar)
    except (ValueError, KeyError, OSError) as e:
        raise HTTPException(400, f"No se pudo leer el Excel: {e}") from e
    if u["rol"] not in GESTION:  # el personal operativo no ve costes
        for g in r["plan"]:
            g.pop("coste_estimado", None)
    return r


# ---------------------------------------------------------------- Business Central
@app.post("/api/bc/{tipo}")
def bc_subir(tipo: str, archivo: UploadFile, u: dict = Depends(requiere(*GESTION))):
    fn = {"movimientos": bc.importar_movimientos, "productos": bc.importar_productos}.get(tipo)
    if not fn:
        raise HTTPException(404, "Tipo desconocido")
    try:
        n = fn(con, _subida(archivo))
    except KeyError as e:
        raise HTTPException(400, str(e)) from e
    return {"filas": n, "valoracion": costing.valorar(con)}


# ---------------------------------------------------------------- módulos (registran rutas sobre `app`)
from bm import api_analisis, api_inventario  # noqa: E402,F401

# ---------------------------------------------------------------- web (siempre la última ruta)
if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str):
        f = STATIC / ruta
        return FileResponse(f if ruta and f.is_file() else STATIC / "index.html")

