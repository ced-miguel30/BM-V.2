"""Ingredientes intercambiables (lechugas, quesos de sándwich, croquetas, bolsas de smoothie...).

La ficha lleva un producto del grupo; al registrar un consumo BM descuenta el que toca ese día:
  1. el que tiene una caducidad registrada más próxima (hay que gastarlo antes),
  2. si no, de los comprados en los 30 días anteriores, el más barato,
  3. si no, el de la ficha.
ponytail: se decide por compras recientes y no por el stock calculado (estable al recalcular días pasados y
sin coste); si hiciera falta, cambiar el paso 2 por "con stock en la ubicación".
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta


def grupos(con: sqlite3.Connection) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for p, g in con.execute("SELECT producto, grupo FROM intercambiables ORDER BY grupo"):
        out.setdefault(g, []).append(p)
    return out


def poner(con: sqlite3.Connection, grupo: str, productos: list[str]) -> None:
    """Fija los productos de un grupo (lista vacía = borrar el grupo). Todos con la misma unidad."""
    grupo = " ".join(grupo.split())
    if not grupo:
        raise ValueError("Pon un nombre al grupo")
    unidades = {r[0] for r in con.execute(
        f"SELECT unidad FROM productos WHERE codigo IN ({','.join('?' * len(productos))})", productos)} if productos else set()
    if len(unidades) > 1:
        raise ValueError(f"Todos deben tener la misma unidad (hay {', '.join(sorted(u or '?' for u in unidades))})")
    if productos and len(productos) < 2:
        raise ValueError("Un grupo necesita al menos dos productos")
    con.execute("DELETE FROM intercambiables WHERE grupo=?", (grupo,))
    con.executemany("INSERT OR REPLACE INTO intercambiables VALUES(?, ?)", [(p, grupo) for p in productos])
    con.commit()


class Selector:
    """Elige el producto de cada grupo por fecha (con caché: se usa al regenerar muchos días)."""

    def __init__(self, con: sqlite3.Connection):
        self.con = con
        self.grupo_de = dict(con.execute("SELECT producto, grupo FROM intercambiables").fetchall())
        self.miembros = grupos(con)
        self._cache: dict = {}

    def elegir(self, producto: str, fecha: str) -> str:
        g = self.grupo_de.get(producto)
        if not g:
            return producto
        if (g, fecha) not in self._cache:
            self._cache[(g, fecha)] = self._elegir(self.miembros[g], fecha) or producto
        return self._cache[(g, fecha)]

    def _elegir(self, miembros: list[str], fecha: str) -> str | None:
        marcas = ",".join("?" * len(miembros))
        cad = self.con.execute(
            f"""SELECT producto FROM caducidades WHERE estado='activa' AND producto IN ({marcas}) AND caduca>=? AND date(creado)<=?
                ORDER BY caduca LIMIT 1""", (*miembros, fecha, fecha)).fetchone()
        if cad:
            return cad[0]
        desde = (date.fromisoformat(fecha) - timedelta(days=30)).isoformat()
        r = self.con.execute(
            f"""SELECT producto, coste_total / cantidad pu FROM bc_movs WHERE tipo='Compra' AND cantidad>0 AND coste_total>0
                AND producto IN ({marcas}) AND fecha>=? AND fecha<=? ORDER BY pu LIMIT 1""", (*miembros, desde, fecha)).fetchone()
        return r[0] if r else None

    def lineas(self, lineas: list, fecha: str) -> list:
        """[(producto, cantidad, receta_id)] -> mismo formato con el intercambiable elegido (solo líneas de receta)."""
        return [(self.elegir(p, fecha) if r else p, q, r) for p, q, r in lineas]


def sembrar_carta(con: sqlite3.Connection, path) -> dict:
    """semillas_carta.json: grupos de intercambiables, recetas estimadas y su artículo del TPV.
    Idempotente y sin pisar: no toca grupos ya creados, recetas existentes ni artículos ya asignados."""
    import json
    from pathlib import Path
    s = json.loads(Path(path).read_text(encoding="utf-8"))
    existe = lambda c: con.execute("SELECT 1 FROM productos WHERE codigo=?", (c,)).fetchone()  # noqa: E731
    hechos = {"grupos": 0, "recetas": 0, "tpv": 0}
    for g, ps in s.get("intercambiables", {}).items():
        ps = [p for p in ps if existe(p)]
        if len(ps) >= 2 and not con.execute("SELECT 1 FROM intercambiables WHERE grupo=?", (g,)).fetchone():
            con.executemany("INSERT OR IGNORE INTO intercambiables VALUES(?, ?)", [(p, g) for p in ps])
            hechos["grupos"] += 1
    for r in s.get("recetas", []):
        if con.execute("SELECT 1 FROM recetas WHERE id=?", (r["id"],)).fetchone() or not all(existe(p) for p, _ in r["lineas"]):
            continue
        con.execute("INSERT INTO recetas(id, nombre, servicio, porciones, nota) VALUES(?,?,?,?,?)",
                    (r["id"], r["nombre"], r["servicio"], r["porciones"], f"Estimada por BM, ajustar: {r['nota']}"))
        con.executemany("INSERT INTO receta_lineas VALUES(?,?,?)", [(r["id"], p, q) for p, q in r["lineas"]])
        hechos["recetas"] += 1
        if r.get("tpv"):
            hechos["tpv"] += con.execute("""UPDATE tpv_articulos SET receta_id=? WHERE codigo=? AND receta_id IS NULL
                                            AND producto IS NULL AND ignorar=0""", (r["id"], r["tpv"])).rowcount
    con.commit()
    return hechos
