"""Solicitudes. El jefe pide a administración lo que necesita (pedida / rechazada) y el equipo avisa al jefe de lo que
queda poco o recomienda pedir (atendida / descartada). El pedido real se hace por Pedidos: un solo camino para comprar."""

from __future__ import annotations

import sqlite3

TIPOS = ("pedido", "queda_poco")
RESPUESTAS = {"administracion": ("pedida", "rechazada"), "jefe": ("atendida", "descartada")}


def crear(con: sqlite3.Connection, *, lineas: list[dict], usuario: str | None, nota: str | None = None,
          para: str = "administracion", tipo: str = "pedido") -> int:
    if para not in RESPUESTAS or tipo not in TIPOS:
        raise ValueError("Solicitud no válida")
    if para == "administracion" and tipo != "pedido":
        raise ValueError("A administración se le pide un pedido")
    buenas: dict[str, float | None] = {}
    for l in lineas:
        q = l.get("cantidad")
        q = None if q in (None, "") else float(q)
        if q is not None and q < 0:
            raise ValueError("Una cantidad no puede ser negativa")
        if tipo == "pedido" and not q:
            continue  # pedir 0 no es pedir
        if not con.execute("SELECT 1 FROM productos WHERE codigo=?", (l["producto"],)).fetchone():
            raise ValueError(f"Producto desconocido: {l['producto']}")
        buenas[l["producto"]] = q if q is None or buenas.get(l["producto"]) is None else buenas[l["producto"]] + q
    if not buenas:
        raise ValueError("La solicitud está vacía")
    sid = con.execute("INSERT INTO solicitudes(usuario, para, tipo, nota) VALUES(?,?,?,?)", (usuario, para, tipo, nota)).lastrowid
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


def para_de(con: sqlite3.Connection, sid: int) -> str | None:
    r = con.execute("SELECT para FROM solicitudes WHERE id=?", (sid,)).fetchone()
    return r[0] if r else None


def responder(con: sqlite3.Connection, sid: int, estado: str, respuesta: str | None, usuario: str | None) -> None:
    para = para_de(con, sid)
    if para is None:
        raise ValueError("No existe")
    if estado not in RESPUESTAS[para]:
        raise ValueError("Estado no válido")
    if estado == "rechazada" and not (respuesta or "").strip():
        raise ValueError("Di por qué se rechaza")
    n = con.execute("""UPDATE solicitudes SET estado=?, respuesta=?, respondido=datetime('now','localtime'), respondido_por=?
                       WHERE id=? AND estado='pendiente'""", (estado, respuesta, usuario, sid)).rowcount
    if not n:
        raise ValueError("Ya está respondida")
    con.commit()
