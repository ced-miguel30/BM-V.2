"""Registro de hechos físicos (desayuno, servicio, merma) y coste de recetas."""

from __future__ import annotations

import sqlite3
from datetime import date

from bm import costing



def receta_real(con: sqlite3.Connection, receta_id: str, fecha: str) -> str:
    """'Tostada del dia' / 'Coctel del dia' -> la receta que toca ese día de la semana."""
    r = con.execute(
        """SELECT d.receta_id FROM recetas_dia d JOIN recetas r ON lower(r.nombre)=lower(d.etiqueta)
           WHERE r.id=? AND d.dia_semana=?""", (receta_id, date.fromisoformat(fecha).weekday())).fetchone()
    return r[0] if r else receta_id


def expandir(con: sqlite3.Connection, items: list[dict], fecha: str | None = None) -> list[tuple[str, float, str | None]]:
    """items: [{'receta_id': .., 'cantidad': raciones} | {'producto': .., 'cantidad': uds}]
    -> [(producto, cantidad, receta_id)] en unidad base BC."""
    out = []
    for it in items:
        q = float(it.get("cantidad") or 0)
        if q <= 0:
            continue
        if it.get("receta_id"):
            rid = receta_real(con, it["receta_id"], fecha) if fecha else it["receta_id"]
            r = con.execute("SELECT porciones FROM recetas WHERE id=?", (rid,)).fetchone()
            if not r:
                raise ValueError(f"Receta desconocida: {it['receta_id']}")
            f = q / (r["porciones"] or 1)
            out += [(l["producto"], l["cantidad"] * f, rid)
                    for l in con.execute("SELECT producto, cantidad FROM receta_lineas WHERE receta_id=?", (rid,))]
        elif it.get("producto"):
            if not con.execute("SELECT 1 FROM productos WHERE codigo=?", (it["producto"],)).fetchone():
                raise ValueError(f"Producto desconocido: {it['producto']}")
            out.append((it["producto"], q, None))
    if not out:
        raise ValueError("No hay líneas con cantidad")
    return out


def centro_valido(con: sqlite3.Connection, codigo: str | None) -> bool:
    return bool(codigo) and bool(con.execute("SELECT 1 FROM centros WHERE codigo=? AND activo=1", (codigo,)).fetchone())


def registrar(con: sqlite3.Connection, *, fecha: str, servicio: str | None, items: list[dict], tipo: str = "consumo",
              comensales: int | None = None, nota: str | None = None, usuario: str | None = None,
              origen: str = "manual", ref: str | None = None, ubicacion: str | None = None) -> int:
    if servicio and not centro_valido(con, servicio):
        raise ValueError(f"Centro de consumo no válido: {servicio}")
    if tipo == "consumo" and not servicio:
        raise ValueError("Indica el servicio o departamento")
    if ubicacion and not con.execute("SELECT 1 FROM ubicaciones WHERE codigo=?", (ubicacion,)).fetchone():
        raise ValueError(f"Ubicación desconocida: {ubicacion}")
    if tipo not in ("consumo", "merma"):
        raise ValueError(f"Tipo no válido: {tipo}")
    date.fromisoformat(fecha)
    lineas = expandir(con, items, fecha)
    if ref and con.execute("SELECT 1 FROM consumos WHERE ref=?", (ref,)).fetchone():
        raise ValueError("Este registro ya existe (misma referencia)")
    cid = con.execute(
        "INSERT INTO consumos(fecha, servicio, tipo, origen, ref, comensales, nota, usuario, ubicacion) VALUES(?,?,?,?,?,?,?,?,?)",
        (fecha, servicio, tipo, origen, ref, comensales, nota, usuario, ubicacion),
    ).lastrowid
    con.executemany(
        "INSERT INTO consumo_lineas(consumo_id, producto, cantidad, receta_id) VALUES(?,?,?,?)",
        [(cid, p, q, r) for p, q, r in lineas],
    )
    con.commit()
    costing.valorar(con)
    return cid


def anular(con: sqlite3.Connection, cid: int, motivo: str, usuario: str | None = None) -> None:
    """Anular no borra: el registro queda visible y deja de contar. El FIFO se recalcula entero,
    así que los lotes vuelven exactamente a su estado sin este consumo."""
    c = con.execute("SELECT anulado, origen FROM consumos WHERE id=?", (cid,)).fetchone()
    if not c:
        raise ValueError("No existe")
    if c["origen"] == "tpv":
        raise ValueError("Los consumos TPV se corrigen desde la asignación del artículo, no anulándolos")
    if c["anulado"]:
        return
    con.execute(
        "UPDATE consumos SET anulado=1, nota=COALESCE(nota || ' | ', '') || ? WHERE id=?",
        (f"ANULADO por {usuario or '?'}: {motivo}", cid),
    )
    con.commit()
    costing.valorar(con)


def precio_actual(con: sqlite3.Connection, producto: str, fecha: str | None = None) -> float | None:
    """Último precio facturado en BC hasta la fecha (para coste teórico de recetas)."""
    fecha = fecha or date.today().isoformat()
    r = con.execute(
        """SELECT ABS(coste_total / cantidad) FROM bc_movs WHERE producto=? AND tipo='Compra'
           AND cantidad > 0 AND coste_total > 0 AND fecha <= ? ORDER BY fecha DESC, n_mov DESC LIMIT 1""",
        (producto, fecha),
    ).fetchone()
    if r:
        return r[0]
    r = con.execute("SELECT coste_ref FROM productos WHERE codigo=?", (producto,)).fetchone()
    return r[0] if r else None


def coste_receta(con: sqlite3.Connection, receta_id: str) -> dict:
    r = con.execute("SELECT * FROM recetas WHERE id=?", (receta_id,)).fetchone()
    lineas, total, completo = [], 0.0, True
    for l in con.execute(
        """SELECT l.producto, l.cantidad, p.nombre, p.unidad FROM receta_lineas l
           JOIN productos p ON p.codigo=l.producto WHERE l.receta_id=?""", (receta_id,)
    ):
        pu = precio_actual(con, l["producto"])
        coste = None if pu is None else round(pu * l["cantidad"], 4)
        completo &= coste is not None
        total += coste or 0
        lineas.append({**dict(l), "precio": pu, "coste": coste})
    porciones = r["porciones"] or 1
    return {**dict(r), "lineas": lineas, "coste_total": round(total, 4),
            "coste_racion": round(total / porciones, 4), "completo": completo}
