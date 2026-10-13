"""Solicitudes de pedido: el jefe pide a administración lo que necesita; administración responde.
El pedido real se hace por el flujo normal (Pedidos), así no hay dos caminos para comprar."""

from __future__ import annotations

import sqlite3

DESTINOS = ("administracion", "jefe")


def crear(con: sqlite3.Connection, *, lineas: list[dict], usuario: str | None, nota: str | None = None,
          para: str = "administracion") -> int:
    if para not in DESTINOS:
        raise ValueError("Destino no válido")
    buenas = {}
    for l in lineas:
        q = float(l.get("cantidad") or 0)
        if q <= 0:
            continue
        if not con.execute("SELECT 1 FROM productos WHERE codigo=?", (l["producto"],)).fetchone():
            raise ValueError(f"Producto desconocido: {l['producto']}")
        buenas[l["producto"]] = buenas.get(l["producto"], 0) + q
    if not buenas:
        raise ValueError("La solicitud no tiene cantidades")
    sid = con.execute("INSERT INTO solicitudes(usuario, para, nota) VALUES(?,?,?)", (usuario, para, nota)).lastrowid
    con.executemany("INSERT INTO solicitud_lineas VALUES(?,?,?)", [(sid, p, q) for p, q in buenas.items()])
    con.commit()
    return sid


def listar(con: sqlite3.Connection, *, para: str | None = None, usuario: str | None = None, limite: int = 100) -> list[dict]:
    sql, args = "SELECT * FROM solicitudes WHERE 1=1", []
    if para:
        sql, args = sql + " AND para=?", args + [para]
    if usuario:
        sql, args = sql + " AND usuario=?", args + [usuario]
    out = []
    for s in con.execute(sql + " ORDER BY estado='pendiente' DESC, id DESC LIMIT ?", (*args, limite)).fetchall():
        lineas = [dict(l) for l in con.execute(
            """SELECT l.producto, l.cantidad, p.nombre, p.unidad FROM solicitud_lineas l JOIN productos p ON p.codigo=l.producto
               WHERE l.solicitud_id=? ORDER BY p.nombre""", (s["id"],))]
        out.append({**dict(s), "lineas": lineas})
    return out


def responder(con: sqlite3.Connection, sid: int, estado: str, respuesta: str | None, usuario: str | None) -> None:
    if estado not in ("pedida", "rechazada"):
        raise ValueError("Estado no válido")
    if estado == "rechazada" and not (respuesta or "").strip():
        raise ValueError("Di por qué se rechaza")
    n = con.execute("""UPDATE solicitudes SET estado=?, respuesta=?, respondido=datetime('now','localtime'), respondido_por=?
                       WHERE id=? AND estado='pendiente'""", (estado, respuesta, usuario, sid)).rowcount
    if not n:
        raise ValueError("No existe o ya está respondida")
    con.commit()
