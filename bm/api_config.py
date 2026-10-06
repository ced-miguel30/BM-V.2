"""Configuración: ajustes, usuarios, centros, ubicaciones, atajos, recetas del día, copias y actividad."""

from __future__ import annotations

import asyncio

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bm import copias, usuarios as usuarios_mod
from bm.app import GESTION, _error, app, con, requiere, usuario
from bm.passwords import hash_password, verify_password

DIRECCION = ("direccion",)


@app.on_event("startup")
async def copia_diaria():
    async def bucle():
        while True:
            if not copias.hay_copia_de_hoy():
                copias.hacer(con)
            await asyncio.sleep(3600)
    asyncio.create_task(bucle())


@app.get("/api/config")
def config(u: dict = Depends(requiere(*GESTION))):
    q = lambda sql: [dict(x) for x in con.execute(sql)]  # noqa: E731
    return {
        "ajustes": dict(con.execute("SELECT clave, valor FROM ajustes").fetchall()),
        "centros": q("SELECT * FROM centros ORDER BY orden, nombre"),
        "ubicaciones": q("SELECT * FROM ubicaciones ORDER BY nombre"),
        "almacenes_bc": q("""SELECT a.*, (SELECT COUNT(*) FROM bc_movs m WHERE m.almacen=a.codigo) movimientos
                             FROM almacenes_bc a ORDER BY movimientos DESC"""),
        "atajos": q("""SELECT a.*, p.nombre producto_nombre, p.unidad, r.nombre receta_nombre FROM atajos a
                       LEFT JOIN productos p ON p.codigo=a.producto LEFT JOIN recetas r ON r.id=a.receta_id ORDER BY a.grupo, a.etiqueta"""),
        "recetas_dia": q("SELECT d.*, r.nombre receta_nombre FROM recetas_dia d JOIN recetas r ON r.id=d.receta_id ORDER BY etiqueta, dia_semana"),
        "usuarios": q("SELECT id, nombre, login, rol, activo FROM usuarios ORDER BY activo DESC, nombre") if u["rol"] in DIRECCION else [],
        "copias": copias.listar(),
    }


class Ajustes(BaseModel):
    igic_ventas: float
    objetivo_food_cost: float
    traslados_en: str


@app.put("/api/config/ajustes")
def guardar_ajustes(d: Ajustes, u: dict = Depends(requiere(*DIRECCION))):
    if d.traslados_en not in ("bc", "bm") or not 0 <= d.igic_ventas <= 30 or not 0 < d.objetivo_food_cost < 100:
        raise HTTPException(400, "Valores no válidos")
    con.executemany("INSERT OR REPLACE INTO ajustes VALUES(?, ?)",
                    [("igic_ventas", str(d.igic_ventas)), ("objetivo_food_cost", str(d.objetivo_food_cost)), ("traslados_en", d.traslados_en)])
    con.commit()
    return {"ok": True}


class Centro(BaseModel):
    nombre: str
    tipo: str
    ubicacion: str | None = None
    color: str = "gray"
    orden: int = 99
    activo: bool = True


@app.put("/api/config/centros/{codigo}")
def guardar_centro(codigo: str, d: Centro, u: dict = Depends(requiere(*GESTION))):
    codigo = codigo.strip().lower()
    if not codigo.isidentifier() or d.tipo not in ("restauracion", "departamento") or not d.nombre.strip():
        raise HTTPException(400, "Código (sin espacios), nombre y tipo son obligatorios")
    con.execute("""INSERT INTO centros(codigo, nombre, tipo, ubicacion, color, orden, activo) VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(codigo) DO UPDATE SET nombre=excluded.nombre, tipo=excluded.tipo, ubicacion=excluded.ubicacion,
                   color=excluded.color, orden=excluded.orden, activo=excluded.activo""",
                (codigo, d.nombre.strip(), d.tipo, d.ubicacion, d.color, d.orden, int(d.activo)))
    con.commit()
    return {"ok": True}


class Ubicacion(BaseModel):
    nombre: str
    activo: bool = True


@app.put("/api/config/ubicaciones/{codigo}")
def guardar_ubicacion(codigo: str, d: Ubicacion, u: dict = Depends(requiere(*GESTION))):
    if not d.nombre.strip() or not codigo.strip():
        raise HTTPException(400, "Nombre obligatorio")
    con.execute("""INSERT INTO ubicaciones(codigo, nombre, activo) VALUES(?,?,?)
                   ON CONFLICT(codigo) DO UPDATE SET nombre=excluded.nombre, activo=excluded.activo""",
                (codigo.strip().upper(), d.nombre.strip(), int(d.activo)))
    con.commit()
    return {"ok": True}


class AlmacenBC(BaseModel):
    ubicacion: str
    centro: str | None = None


@app.put("/api/config/almacenes/{codigo}")
def guardar_almacen(codigo: str, d: AlmacenBC, u: dict = Depends(requiere(*GESTION))):
    if not con.execute("SELECT 1 FROM ubicaciones WHERE codigo=?", (d.ubicacion,)).fetchone():
        raise HTTPException(400, "Ubicación desconocida")
    con.execute("UPDATE almacenes_bc SET ubicacion=?, centro=? WHERE codigo=?", (d.ubicacion, d.centro, codigo))
    con.commit()
    return {"ok": True}


class Atajo(BaseModel):
    grupo: str
    etiqueta: str
    producto: str | None = None
    receta_id: str | None = None
    cantidad: float
    sustituye: str | None = None
    activo: bool = True
    etiqueta_anterior: str | None = None  # para renombrar


@app.put("/api/config/atajos")
def guardar_atajo(d: Atajo, u: dict = Depends(requiere(*GESTION))):
    if d.grupo not in ("extra", "leche", "bebida", "buffet", "omitir") or not d.etiqueta.strip():
        raise HTTPException(400, "Grupo o etiqueta no válidos")
    if bool(d.producto) == bool(d.receta_id) and d.grupo != "omitir":
        raise HTTPException(400, "Indica un producto o una receta (solo uno)")
    if d.etiqueta_anterior and d.etiqueta_anterior != d.etiqueta:
        con.execute("DELETE FROM atajos WHERE grupo=? AND etiqueta=?", (d.grupo, d.etiqueta_anterior))
    con.execute("INSERT OR REPLACE INTO atajos(etiqueta, grupo, producto, receta_id, cantidad, sustituye, activo) VALUES(?,?,?,?,?,?,?)",
                (d.etiqueta.strip(), d.grupo, d.producto, d.receta_id, d.cantidad, d.sustituye or None, int(d.activo)))
    con.commit()
    return {"ok": True}


class RecetaDia(BaseModel):
    etiqueta: str
    dia_semana: int
    receta_id: str


@app.put("/api/config/recetas_dia")
def guardar_receta_dia(d: RecetaDia, u: dict = Depends(requiere(*GESTION))):
    if not 0 <= d.dia_semana <= 6:
        raise HTTPException(400, "Día no válido")
    con.execute("INSERT OR REPLACE INTO recetas_dia VALUES(?,?,?)", (d.etiqueta, d.dia_semana, d.receta_id))
    con.commit()
    from bm import costing, tpv
    tpv.regenerar(con)  # el TPV histórico depende de qué cóctel tocaba cada día
    costing.valorar(con)
    return {"ok": True}


class Usuario(BaseModel):
    login: str
    nombre: str
    rol: str
    activo: bool = True
    password: str | None = None


@app.post("/api/config/usuarios")
def guardar_usuario(d: Usuario, u: dict = Depends(requiere(*DIRECCION))):
    existe = con.execute("SELECT id FROM usuarios WHERE login=?", (d.login.strip().lower(),)).fetchone()
    if not existe and not d.password:
        raise HTTPException(400, "Un usuario nuevo necesita contraseña")
    if d.password and len(d.password) < 8:
        raise HTTPException(400, "La contraseña debe tener al menos 8 caracteres")
    if d.password:
        _error(usuarios_mod.guardar, con, d.login, d.nombre, d.rol, d.password)
    elif d.rol not in usuarios_mod.ROLES:
        raise HTTPException(400, "Rol no válido")
    con.execute("UPDATE usuarios SET nombre=?, rol=?, activo=? WHERE login=?", (d.nombre, d.rol, int(d.activo), d.login.strip().lower()))
    if not d.activo:
        con.execute("DELETE FROM sesiones WHERE usuario_id=(SELECT id FROM usuarios WHERE login=?)", (d.login.strip().lower(),))
    con.commit()
    return {"ok": True}


class CambioClave(BaseModel):
    actual: str
    nueva: str


@app.post("/api/me/password")
def cambiar_clave(d: CambioClave, u: dict = Depends(usuario)):
    r = con.execute("SELECT password_hash FROM usuarios WHERE id=?", (u["id"],)).fetchone()
    if not verify_password(d.actual, r["password_hash"]):
        raise HTTPException(400, "La contraseña actual no es correcta")
    if len(d.nueva) < 8:
        raise HTTPException(400, "La nueva contraseña debe tener al menos 8 caracteres")
    con.execute("UPDATE usuarios SET password_hash=? WHERE id=?", (hash_password(d.nueva), u["id"]))
    con.commit()
    return {"ok": True}


@app.get("/api/config/actividad")
def actividad(u: dict = Depends(requiere(*DIRECCION))):
    return [dict(x) for x in con.execute("SELECT * FROM auditoria ORDER BY id DESC LIMIT 500")]


@app.post("/api/config/copias")
def copia_ahora(u: dict = Depends(requiere(*GESTION))):
    return {"nombre": copias.hacer(con, "manual").name}


@app.get("/api/config/copias/{nombre}")
def descargar_copia(nombre: str, u: dict = Depends(requiere(*DIRECCION))):
    f = copias.carpeta() / nombre
    if "/" in nombre or "\\" in nombre or not f.is_file():
        raise HTTPException(404, "No existe")
    return FileResponse(f, filename=nombre, media_type="application/octet-stream")
