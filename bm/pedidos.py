"""Pedidos a proveedores: BM los propone (prevision.pedidos), aquí se guardan al enviarlos y se cruzan con los
albaranes que llegan de BC para saber si llegó todo. BC sigue siendo quien registra la compra."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, timedelta

MARGEN = 0.98  # recibido >= 98 % de lo pedido cuenta como completo (redondeos, pesos)


def crear(con: sqlite3.Connection, *, proveedor: str, entrega: str | None, lineas: list[dict], usuario: str | None = None,
          nota: str | None = None, hoy: date | None = None) -> int:
    if entrega:
        date.fromisoformat(entrega)
    buenas = [(l["producto"], float(l["cantidad"])) for l in lineas if float(l.get("cantidad") or 0) > 0]
    if not buenas:
        raise ValueError("El pedido no tiene cantidades")
    for p, _ in buenas:
        if not con.execute("SELECT 1 FROM productos WHERE codigo=?", (p,)).fetchone():
            raise ValueError(f"Producto desconocido: {p}")
    pid = con.execute("INSERT INTO pedidos(proveedor, fecha, entrega, usuario, nota) VALUES(?,?,?,?,?)",
                      (proveedor, (hoy or date.today()).isoformat(), entrega, usuario, nota)).lastrowid
    con.executemany("INSERT INTO pedido_lineas VALUES(?,?,?)", [(pid, p, q) for p, q in buenas])
    con.commit()
    return pid


def en_camino(con: sqlite3.Connection) -> dict[str, float]:
    """Cantidad pedida y aún no recibida por producto (para no volver a proponerla)."""
    out: dict[str, float] = defaultdict(float)
    for r in con.execute("""SELECT l.producto, l.cantidad FROM pedidos p JOIN pedido_lineas l ON l.pedido_id=p.id
                            WHERE p.estado='enviado'"""):
        out[r["producto"]] += r["cantidad"]
    return dict(out)


def _recibido(con, albaranes: list[str]) -> dict[str, float]:
    if not albaranes:
        return {}
    marcas = ",".join("?" * len(albaranes))
    return dict(con.execute(f"""SELECT producto, SUM(cantidad) FROM bc_movs WHERE tipo='Compra' AND documento IN ({marcas})
                               GROUP BY producto""", albaranes).fetchall())


def conciliar(con: sqlite3.Connection, hoy: date | None = None) -> int:
    """Cruza cada pedido enviado (o incompleto, por si llega el resto) con los albaranes del proveedor llegados desde que se pidió (hasta una semana
    después de la entrega prevista) y aún sin asignar a otro pedido. Devuelve cuántos pedidos cambiaron."""
    usados = {a for (t,) in con.execute("SELECT albaranes FROM pedidos WHERE albaranes IS NOT NULL") for a in t.split(",")}
    cambios = 0
    for p in con.execute("SELECT * FROM pedidos WHERE estado IN ('enviado','incompleto') ORDER BY fecha, id").fetchall():
        limite = (date.fromisoformat(p["entrega"] or p["fecha"]) + timedelta(days=7)).isoformat()
        pedidos_prod = {r[0] for r in con.execute("SELECT producto FROM pedido_lineas WHERE pedido_id=?", (p["id"],))}
        docs = [r["documento"] for r in con.execute(
            """SELECT documento, GROUP_CONCAT(producto) prods FROM bc_movs WHERE tipo='Compra' AND cantidad>0 AND proveedor=?
               AND fecha>=? AND fecha<=? AND documento<>'' GROUP BY documento ORDER BY MIN(fecha)""",
            (p["proveedor"], p["fecha"], limite)) if r["documento"] not in usados and pedidos_prod & set(r["prods"].split(","))]
        previos = p["albaranes"].split(",") if p["albaranes"] else []
        tomados = list(previos)
        for doc in docs:  # por fecha, hasta que el pedido quede completo (el siguiente albarán será de otro pedido)
            tomados.append(doc)
            if not faltas(con, p["id"], tomados):
                break
        if tomados == previos:
            continue
        usados |= set(tomados)
        estado = "recibido" if not faltas(con, p["id"], tomados) else "incompleto"
        con.execute("UPDATE pedidos SET estado=?, albaranes=? WHERE id=?", (estado, ",".join(tomados), p["id"]))
        cambios += 1
    con.commit()
    return cambios


def faltas(con: sqlite3.Connection, pid: int, albaranes: list[str] | None = None) -> list[dict]:
    if albaranes is None:
        r = con.execute("SELECT albaranes FROM pedidos WHERE id=?", (pid,)).fetchone()
        albaranes = (r["albaranes"] or "").split(",") if r and r["albaranes"] else []
    rec = _recibido(con, albaranes)
    out = []
    for l in con.execute("""SELECT l.producto, l.cantidad, pr.nombre, pr.unidad FROM pedido_lineas l
                            LEFT JOIN productos pr ON pr.codigo=l.producto WHERE l.pedido_id=?""", (pid,)):
        llego = rec.get(l["producto"], 0.0)
        if llego < l["cantidad"] * MARGEN:
            out.append({"producto": l["producto"], "nombre": l["nombre"], "unidad": l["unidad"], "pedido": l["cantidad"],
                        "recibido": round(llego, 3), "falta": round(l["cantidad"] - llego, 3)})
    return out


def listar(con: sqlite3.Connection, dias: int = 60) -> list[dict]:
    desde = (date.today() - timedelta(days=dias)).isoformat()
    out = []
    for p in con.execute("SELECT * FROM pedidos WHERE fecha>=? ORDER BY fecha DESC, id DESC", (desde,)).fetchall():
        albs = (p["albaranes"] or "").split(",") if p["albaranes"] else []
        rec = _recibido(con, albs)
        lineas = [{**dict(l), "recibido": round(rec.get(l["producto"], 0.0), 3)} for l in con.execute(
            """SELECT l.producto, l.cantidad, pr.nombre, pr.unidad FROM pedido_lineas l LEFT JOIN productos pr ON pr.codigo=l.producto
               WHERE l.pedido_id=? ORDER BY pr.nombre""", (p["id"],))]
        retrasado = p["estado"] == "enviado" and p["entrega"] and p["entrega"] < (date.today() - timedelta(days=1)).isoformat()
        out.append({**dict(p), "lineas": lineas, "retrasado": bool(retrasado),
                    "faltan": sum(1 for l in lineas if albs and l["recibido"] < l["cantidad"] * MARGEN)})
    return out


def cerrar(con: sqlite3.Connection, pid: int, estado: str, nota: str | None, usuario: str | None) -> None:
    """Cerrar (lo que faltaba ya no se espera, p. ej. reclamado o abonado) o anular (no se llegó a pedir)."""
    if estado not in ("cerrado", "anulado"):
        raise ValueError("Estado no válido")
    n = con.execute("UPDATE pedidos SET estado=?, nota=COALESCE(nota || ' | ', '') || ? WHERE id=? AND estado IN ('enviado','incompleto')",
                    (estado, f"{estado.upper()} por {usuario or '?'}: {nota or ''}".strip(), pid)).rowcount
    if not n:
        raise ValueError("No existe o ya está cerrado")
    con.commit()
