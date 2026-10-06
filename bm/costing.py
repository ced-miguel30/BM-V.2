"""Valoración FIFO anclada al inventario de Business Central.

Por producto, en orden de fecha:
  1. Cada compra de BC (albarán/factura) abre un lote con su coste real.
     Devoluciones a proveedor (cantidad < 0) restan de los lotes más nuevos.
  2. Los consumos registrados en BM (desayuno, TPV, mermas...) gastan lotes del más antiguo al más nuevo.
  3. Los días con inventario en BC (Ajuste positivo/negativo) mandan: el stock real de BC sustituye
     al teórico y quedan vivos los lotes más recientes (eso es FIFO). Así se absorbe lo que BM no ve
     (habitaciones, personal, roturas...). Antes del primer consumo se aplica el mismo anclaje.

Estados de coste por línea:
  fifo         todo sale de lotes con precio facturado
  provisional  algún lote es un albarán aún sin facturar (coste 0 en BC) o tiene un precio disparatado
               (error de BC, ver dudosos()): se usa el último precio fiable
  sin_stock    no quedaban lotes: se usa el último precio conocido
  sin_precio   el producto no tiene ninguna compra ni coste en BC
Se recalcula todo desde cero: el resultado sólo depende de los datos, nunca del orden de importación.
"""

from __future__ import annotations

import bisect
import sqlite3
from collections import defaultdict
from itertools import groupby

_PEOR = {"fifo": 0, "provisional": 1, "sin_stock": 2, "sin_precio": 3}


def _coste(m) -> float | None:
    if m["cantidad"] and m["coste_total"]:
        return abs(m["coste_total"] / m["cantidad"])
    return m["coste_unit"] or None


FACTOR_DUDOSO = 4.0  # un precio 4 veces por encima o por debajo de la mediana del producto es un error de BC


def dudosos(compras) -> set:
    """n_mov de compras con precio disparatado (errores de unidad/importe en BC).
    Cada compra se compara con la mediana de sus vecinas (5 antes y 5 después): un cambio real y
    sostenido de precio o de unidad no se marca; un precio aislado fuera de escala sí."""
    precios = sorted((m["fecha"], m["n_mov"], _coste(m)) for m in compras
                     if m["tipo"] == "Compra" and m["cantidad"] > 0 and _coste(m))
    def fuera(p, lado):
        xs = sorted(x[2] for x in lado)
        med = xs[len(xs) // 2]
        return p > med * FACTOR_DUDOSO or p < med / FACTOR_DUDOSO

    malos = set()
    for i, (_, n, p) in enumerate(precios):
        lados = [l for l in (precios[max(0, i - 5):i], precios[i + 1:i + 6]) if len(l) >= 2]
        # Dudoso solo si choca con lo de antes Y con lo de después: un cambio sostenido encaja con uno de los dos.
        if lados and all(fuera(p, l) for l in lados):
            malos.add(n)
    return malos


class Producto:
    def __init__(self, movs, coste_ref: float | None = None):
        self.compras: list[list] = []  # [n_mov, cantidad_original, coste_unit|None]
        self.lotes: list[list] = []    # [n_mov, cantidad_restante, coste_unit|None]  antiguo -> nuevo
        self.dudosos = dudosos(movs)   # se tratan como "sin facturar": valen al último precio fiable
        precios = sorted(
            (m["fecha"], m["n_mov"], _coste(m))
            for m in movs if m["tipo"] == "Compra" and m["cantidad"] > 0 and _coste(m) and m["n_mov"] not in self.dudosos
        )
        self._fechas = [p[0] for p in precios]
        self._precios = [p[2] for p in precios]
        self.coste_ref = coste_ref

    def precio_conocido(self, fecha: str) -> float | None:
        """Último precio facturado hasta la fecha; si no hay, el primero posterior; si no, el del maestro."""
        i = bisect.bisect_right(self._fechas, fecha)
        if i:
            return self._precios[i - 1]
        if self._precios:
            return self._precios[0]
        return self.coste_ref

    def compra(self, m) -> None:
        if m["cantidad"] > 0:
            coste = None if m["n_mov"] in self.dudosos else _coste(m)
            self.compras.append([m["n_mov"], m["cantidad"], coste])
            self.lotes.append([m["n_mov"], m["cantidad"], coste])
            return
        resto = -m["cantidad"]  # devolución a proveedor
        for capa in reversed(self.lotes):
            q = min(resto, capa[1])
            capa[1] -= q
            resto -= q
        self.lotes = [c for c in self.lotes if c[1] > 1e-9]

    def anclar(self, stock: float) -> None:
        """El stock real de BC manda: quedan vivas las compras más recientes que lo cubren."""
        nuevos, resto = [], max(stock, 0.0)
        for n_mov, q, coste in reversed(self.compras):
            if resto <= 1e-9:
                break
            t = min(q, resto)
            nuevos.append([n_mov, t, coste])
            resto -= t
        if resto > 1e-9:  # stock anterior al histórico exportado
            nuevos.append([None, resto, self.compras[0][2] if self.compras else None])
        self.lotes = nuevos[::-1]

    def consumir(self, cantidad: float, fecha: str):
        """-> (coste, estado, [(n_mov, cantidad, coste_unit)])"""
        partes, resto, estado = [], cantidad, "fifo"
        while resto > 1e-9 and self.lotes:
            capa = self.lotes[0]
            q = min(resto, capa[1])
            precio = capa[2]
            if precio is None:
                precio, estado = self.precio_conocido(fecha), max(estado, "provisional", key=_PEOR.get)
            partes.append((capa[0], q, precio))
            capa[1] -= q
            resto -= q
            if capa[1] <= 1e-9:
                self.lotes.pop(0)
        if resto > 1e-9:
            precio = self.precio_conocido(fecha)
            estado = max(estado, "sin_stock" if precio is not None else "sin_precio", key=_PEOR.get)
            partes.append((None, resto, precio))
        if any(p[2] is None for p in partes):
            return None, "sin_precio", partes
        return round(sum(q * p for _, q, p in partes), 4), estado, partes


def valorar_producto(movs, consumos, coste_ref=None):
    """movs: movimientos BC del producto (sin transferencias) ordenados por fecha.
    consumos: [{'id','fecha','cantidad'}] ordenados por fecha. -> [(id, coste, estado, partes)]"""
    p = Producto(movs, coste_ref)
    eventos = defaultdict(lambda: {"compras": [], "consumos": [], "ancla": False})
    stock_fin_dia, acumulado = {}, 0.0
    for m in movs:
        acumulado += m["cantidad"]
        stock_fin_dia[m["fecha"]] = acumulado
        if m["tipo"] == "Compra":
            eventos[m["fecha"]]["compras"].append(m)
        elif m["tipo"].startswith("Ajuste"):
            eventos[m["fecha"]]["ancla"] = True
    for l in consumos:
        eventos[l["fecha"]]["consumos"].append(l)

    fechas_stock = sorted(stock_fin_dia)
    primer_consumo = consumos[0]["fecha"] if consumos else None
    anclado_inicio, salida = False, []
    for fecha in sorted(eventos):
        ev = eventos[fecha]
        if not anclado_inicio and primer_consumo and fecha >= primer_consumo:
            # Punto de partida: stock real de BC al cierre del día anterior al primer consumo.
            i = bisect.bisect_left(fechas_stock, fecha)
            if i:
                p.anclar(stock_fin_dia[fechas_stock[i - 1]])
            anclado_inicio = True
        for m in ev["compras"]:
            p.compra(m)
        for l in ev["consumos"]:
            coste, estado, partes = p.consumir(l["cantidad"], fecha)
            salida.append((l["id"], coste, estado, partes))
        if ev["ancla"]:
            p.anclar(stock_fin_dia[fecha])
    return salida


def valorar(con: sqlite3.Connection) -> dict:
    lineas = con.execute(
        """SELECT l.id, l.producto, l.cantidad, c.fecha FROM consumo_lineas l
           JOIN consumos c ON c.id = l.consumo_id WHERE c.anulado = 0
           ORDER BY l.producto, c.fecha, c.id, l.id"""
    ).fetchall()
    coste_ref = dict(con.execute("SELECT codigo, coste_ref FROM productos").fetchall())
    movs = defaultdict(list)
    for m in con.execute(
        """SELECT * FROM bc_movs WHERE tipo <> 'Transferencia'
           AND producto IN (SELECT DISTINCT producto FROM consumo_lineas) ORDER BY producto, fecha, n_mov"""
    ):
        movs[m["producto"]].append(m)

    resultados, asignaciones, estados = [], [], defaultdict(int)
    for producto, grupo in groupby(lineas, key=lambda l: l["producto"]):
        for lid, coste, estado, partes in valorar_producto(movs.get(producto, []), list(grupo), coste_ref.get(producto)):
            resultados.append((coste, estado, lid))
            asignaciones.extend((lid, n, q, pu) for n, q, pu in partes)
            estados[estado] += 1

    con.execute("DELETE FROM asignaciones")
    con.execute("UPDATE consumo_lineas SET coste=NULL, coste_estado=NULL")
    con.executemany("UPDATE consumo_lineas SET coste=?, coste_estado=? WHERE id=?", resultados)
    con.executemany("INSERT INTO asignaciones VALUES(?,?,?,?)", asignaciones)
    con.commit()
    return dict(estados)
