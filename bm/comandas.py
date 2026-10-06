"""Comandas de desayuno desde la tablet: un toque por plato, extras y quitar con botones, comensales con un contador.
Cada cambio recalcula el consumo del día con el mismo motor que el Excel (excel.Resolver)."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from bm import costing, excel

_BEBIDAS = {excel._n(n) for n in json.loads((Path(__file__).parent / "semillas_desayuno.json").read_text(encoding="utf-8"))
            .get("recetas_bebidas_desayuno", [])}


def _corto(nombre: str) -> str:
    """'BACON SELECTED PREMIUM 4-2,27KG' -> 'Bacon selected premium' (sin formato de compra)."""
    palabras = []
    for w in nombre.split():
        if any(ch.isdigit() for ch in w) or w in ("*", "-", "/"):
            break
        palabras.append(w)
    return " ".join(palabras[:3]).capitalize() or nombre


def catalogo(con: sqlite3.Connection) -> dict:
    """Botones de la pantalla, los más pedidos primero."""
    uso = dict(con.execute("""SELECT nombre, COUNT(*) FROM comanda_lineas WHERE anulada=0 AND fecha>=date('now','-60 days')
                              GROUP BY nombre""").fetchall())
    uso_rec = dict(con.execute("""SELECT r.nombre, COUNT(DISTINCT c.fecha) FROM consumo_lineas l JOIN consumos c ON c.id=l.consumo_id
                                  JOIN recetas r ON r.id=l.receta_id WHERE c.servicio='desayuno' AND c.fecha>=date('now','-90 days')
                                  GROUP BY r.nombre""").fetchall())
    ingredientes = {}
    for r in con.execute("SELECT l.receta_id, p.nombre FROM receta_lineas l JOIN productos p ON p.codigo=l.producto"):
        ingredientes.setdefault(r["receta_id"], []).append(_corto(r["nombre"]))
    platos, bebidas = [], []
    for r in con.execute("""SELECT id, nombre, servicio FROM recetas WHERE activo=1 AND servicio IN ('desayuno','bebidas')
                            AND id NOT IN (SELECT receta_id FROM atajos WHERE grupo='buffet' AND receta_id IS NOT NULL)
                            AND id NOT IN (SELECT receta_id FROM recetas_dia)"""):  # sale "Tostada del dia", no las 7
        item = {"nombre": r["nombre"], "uso": uso.get(r["nombre"], 0) * 10 + uso_rec.get(r["nombre"], 0),
                "ingredientes": sorted(set(ingredientes.get(r["id"], [])))[:12]}
        if r["servicio"] == "desayuno":
            platos.append(item)
        elif excel._n(r["nombre"]) in _BEBIDAS:
            bebidas.append(item)
    atajos = [dict(a) for a in con.execute(
        "SELECT etiqueta, grupo, sustituye FROM atajos WHERE activo=1 AND grupo IN ('extra','leche','bebida','omitir')")]
    for a in atajos:
        a["uso"] = uso.get(a["etiqueta"], 0)
    bebidas += [{"nombre": a["etiqueta"], "uso": a["uso"], "ingredientes": []} for a in atajos if a["grupo"] in ("bebida", "leche")]
    por_uso = lambda xs, k: sorted(xs, key=lambda x: (-x["uso"], x[k]))  # noqa: E731
    return {
        "platos": por_uso(platos, "nombre"),
        "bebidas": por_uso(bebidas, "nombre"),
        "extras": por_uso([a for a in atajos if a["grupo"] == "extra" and not a["sustituye"]], "etiqueta"),
        "sustituir": [a for a in atajos if a["grupo"] == "extra" and a["sustituye"]],
        "quitar": [a for a in atajos if a["grupo"] == "omitir"],
    }


def _comensales(con, fecha: str) -> tuple[int, bool]:
    """Los apuntados a mano mandan; si no, cada línea de plato es un huésped (cómo se hace en el hotel)."""
    c = con.execute("SELECT comensales FROM comanda_dia WHERE fecha=?", (fecha,)).fetchone()
    if c and c[0]:
        return c[0], False
    n = sum(1 for (nombre,) in con.execute("SELECT nombre FROM comanda_lineas WHERE fecha=? AND anulada=0", (fecha,))
            if excel._n(nombre) not in _BEBIDAS and con.execute("SELECT 1 FROM recetas WHERE nombre=? AND servicio='desayuno'", (nombre,)).fetchone())
    return n, True


def dia(con: sqlite3.Connection, fecha: str) -> dict:
    lineas = [{**dict(r), "extras": json.loads(r["extras"]), "omitir": json.loads(r["omitir"])} for r in con.execute(
        "SELECT * FROM comanda_lineas WHERE fecha=? AND anulada=0 ORDER BY id DESC", (fecha,))]
    n, auto = _comensales(con, fecha)
    return {"fecha": fecha, "comensales": n, "comensales_auto": auto, "lineas": lineas, "platos": round(sum(l["cantidad"] for l in lineas))}


def _fila(res, f: date, lid: int, nombre: str, cantidad: float, extras, omitir) -> excel.Fila:
    es_receta = bool(res.receta(nombre, f))
    bebida = excel._n(nombre) in _BEBIDAS or not es_receta
    return excel.Fila(hoja="RegistroBebidasDesayuno" if bebida else "Registro", fila=lid, fecha=f,
                      tipo="receta" if es_receta else "producto", nombre=nombre, cantidad=cantidad,
                      extras=[tuple(x) for x in extras], omitir=list(omitir))


def regenerar(con: sqlite3.Connection, fecha: str) -> None:
    """Rehace el consumo del día a partir de las comandas (y sustituye lo importado por Excel ese día)."""
    f = date.fromisoformat(fecha)
    res = excel.Resolver(con)
    lineas = []
    for l in con.execute("SELECT * FROM comanda_lineas WHERE fecha=? AND anulada=0", (fecha,)):
        lineas += res.fila(_fila(res, f, l["id"], l["nombre"], l["cantidad"], json.loads(l["extras"]), json.loads(l["omitir"])))
    for hoja in ("Registro", "RegistroBebidasDesayuno"):
        for cid in excel._previos(con, hoja, f, "consumo"):
            con.execute("DELETE FROM consumos WHERE id=?", (cid,))
    con.execute("DELETE FROM consumos WHERE ref=?", (f"comandas:{fecha}",))
    comensales = _comensales(con, fecha)[0]
    if lineas or comensales:
        cid = con.execute(
            "INSERT INTO consumos(fecha, servicio, tipo, origen, ref, comensales, nota) VALUES(?, 'desayuno', 'consumo', 'comandas', ?, ?, ?)",
            (fecha, f"comandas:{fecha}", comensales or None, "Comandas de desayuno")).lastrowid
        con.executemany("INSERT INTO consumo_lineas(consumo_id, producto, cantidad, receta_id) VALUES(?,?,?,?)",
                        [(cid, p, q, r) for p, q, r in lineas if q > 0])
    con.commit()
    costing.valorar(con)


def anadir(con, *, fecha: str, nombre: str, cantidad: float = 1, extras=(), omitir=(), usuario: str | None = None) -> int:
    f = date.fromisoformat(fecha)
    if cantidad <= 0:
        raise ValueError("Cantidad mayor que 0")
    res = excel.Resolver(con)
    res.fila(_fila(res, f, 0, nombre, cantidad, extras, omitir))  # si no se entiende, no se apunta
    lid = con.execute("INSERT INTO comanda_lineas(fecha, nombre, cantidad, extras, omitir, usuario) VALUES(?,?,?,?,?,?)",
                      (fecha, nombre, cantidad, json.dumps([list(x) for x in extras], ensure_ascii=False),
                       json.dumps(list(omitir), ensure_ascii=False), usuario)).lastrowid
    regenerar(con, fecha)
    return lid


def quitar(con, lid: int) -> None:
    r = con.execute("SELECT fecha FROM comanda_lineas WHERE id=? AND anulada=0", (lid,)).fetchone()
    if not r:
        raise ValueError("No existe")
    con.execute("UPDATE comanda_lineas SET anulada=1 WHERE id=?", (lid,))
    regenerar(con, r[0])


def poner_comensales(con, fecha: str, n: int) -> None:
    date.fromisoformat(fecha)
    con.execute("INSERT INTO comanda_dia VALUES(?, ?) ON CONFLICT(fecha) DO UPDATE SET comensales=excluded.comensales", (fecha, max(0, int(n))))
    regenerar(con, fecha)
