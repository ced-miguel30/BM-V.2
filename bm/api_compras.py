"""API de compras: documentos de BC, adjuntos y fichas de proveedor."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bm import compras
from bm.app import GESTION, OPERATIVO, _error, _subida, app, con, requiere

TIPOS_ADJUNTO = {".pdf", ".jpg", ".jpeg", ".png", ".heic", ".webp"}


@app.get("/api/compras")
def listar(desde: str, hasta: str, proveedor: str | None = None, u: dict = Depends(requiere(*GESTION))):
    return compras.documentos(con, desde, hasta, proveedor)


@app.get("/api/compras/{doc}")
def ver(doc: str, u: dict = Depends(requiere(*GESTION))):
    d = compras.documento(con, doc)
    if not d:
        raise HTTPException(404, "No existe")
    return d


@app.post("/api/compras/{doc}/adjuntos")
def adjuntar(doc: str, archivo: UploadFile, u: dict = Depends(requiere(*OPERATIVO))):
    ext = Path(archivo.filename or "").suffix.lower()
    if ext not in TIPOS_ADJUNTO:
        raise HTTPException(400, "Sube una foto (JPG/PNG) o un PDF")
    aid = _error(compras.guardar_adjunto, con, doc, archivo.filename or "adjunto", _subida(archivo), archivo.content_type, u["nombre"])
    return {"id": aid}


@app.get("/api/adjuntos/{aid}")
def descargar(aid: int, u: dict = Depends(requiere(*GESTION))):
    a = con.execute("SELECT * FROM adjuntos WHERE id=?", (aid,)).fetchone()
    if not a or not Path(a["fichero"]).is_file():
        raise HTTPException(404, "No existe")
    tipo = a["tipo"] or mimetypes.guess_type(a["nombre"])[0] or "application/octet-stream"
    return FileResponse(a["fichero"], media_type=tipo, filename=a["nombre"], content_disposition_type="inline")


@app.get("/api/proveedores")
def proveedores(u: dict = Depends(requiere(*GESTION))):
    return compras.proveedores(con)


@app.get("/api/proveedores/{nombre}/productos")
def productos_proveedor(nombre: str, u: dict = Depends(requiere(*GESTION))):
    return [dict(x) for x in con.execute(
        """SELECT m.producto, p.nombre, p.unidad, COUNT(DISTINCT m.documento) entregas, ROUND(SUM(m.cantidad), 2) cantidad,
             MAX(m.fecha) ultima FROM bc_movs m JOIN productos p ON p.codigo=m.producto
           WHERE m.tipo='Compra' AND m.proveedor=? AND m.fecha>=date('now','-365 days') GROUP BY 1 ORDER BY entregas DESC""", (nombre,))]


class Ficha(BaseModel):
    email: str | None = None
    telefono: str | None = None
    contacto: str | None = None
    dias_reparto: list[int] | None = None  # None/[] = deducir del histórico
    plazo_dias: int | None = None
    pedido_minimo: float | None = None
    notas: str | None = None
    activo: bool = True


@app.put("/api/proveedores/{nombre}")
def guardar(nombre: str, d: Ficha, u: dict = Depends(requiere(*GESTION))):
    if d.email and ("@" not in d.email or " " in d.email.strip()):
        raise HTTPException(400, "Correo no válido")
    if any(not 0 <= x <= 6 for x in d.dias_reparto or []):
        raise HTTPException(400, "Días no válidos")
    n = con.execute(
        """UPDATE proveedores SET email=?, telefono=?, contacto=?, dias_reparto=?, plazo_dias=?, pedido_minimo=?, notas=?, activo=?
           WHERE nombre=?""",
        ((d.email or "").strip() or None, d.telefono, d.contacto, ",".join(map(str, sorted(set(d.dias_reparto)))) if d.dias_reparto else None,
         d.plazo_dias, d.pedido_minimo, d.notas, int(d.activo), nombre)).rowcount
    if not n:
        raise HTTPException(404, "Proveedor desconocido")
    con.commit()
    return {"ok": True}
