"""Inventario por ubicación: stock teórico, traslados, recuentos y caducidades.

Stock teórico de (producto, ubicación), en orden de fecha:
  + compras de BC que entran en esa ubicación
  ± traslados (de BC o de BM, según el ajuste `traslados_en`; nunca de los dos)
  - consumos y mermas de BM que salen de esa ubicación
  = un recuento (inventario de BC o recuento de BM) FIJA el stock real.
    La diferencia con el teórico justo antes es la DESVIACIÓN (lo que se ha ido sin registrar).
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date

CENTROS_INICIALES = [  # codigo, nombre, tipo, ubicación BC, color, orden
    ("desayuno", "Desayuno", "restauracion", "DESAYUNO", "orange", 1),
    ("comida", "Comida", "restauracion", "SNACK COMI", "teal", 2),
    ("cena", "Cena", "restauracion", "SNACK CENA", "indigo", 3),
    ("bebidas", "Bebidas", "restauracion", "SNACK BEBI", "grape", 4),
    ("habitaciones", "Habitaciones", "departamento", "HABITACION", "cyan", 10),
    ("pisos", "Pisos", "departamento", "PISOS", "blue", 11),
    ("limpieza", "Limpieza", "departamento", "LIMPIEZA", "lime", 12),
    ("mantenimiento", "Mantenimiento", "departamento", "MANTEN", "gray", 13),
    ("personal", "Personal", "departamento", "PERSONAL", "yellow", 14),
    ("amenities", "Amenities", "departamento", "AMENITIES", "pink", 15),
]


def sembrar(con: sqlite3.Connection) -> None:
    """Idempotente: ubicaciones de BC y centros por defecto (editables después)."""
    con.executemany("INSERT OR IGNORE INTO ubicaciones(codigo, nombre) VALUES(?, ?)",
                    [(c[3], c[3].title()) for c in CENTROS_INICIALES])
    con.execute("""INSERT OR IGNORE INTO ubicaciones(codigo, nombre)
                   SELECT DISTINCT almacen, almacen FROM bc_movs WHERE almacen <> ''""")
    con.executemany("INSERT OR IGNORE INTO centros(codigo, nombre, tipo, ubicacion, color, orden) VALUES(?,?,?,?,?,?)",
                    CENTROS_INICIALES)
    con.executemany("INSERT OR IGNORE INTO ajustes VALUES(?, ?)",
                    [("traslados_en", "bc"), ("igic_ventas", "7"), ("objetivo_food_cost", "30")])
    con.commit()


def ajuste(con: sqlite3.Connection, clave: str, defecto: str | None = None) -> str | None:
    r = con.execute("SELECT valor FROM ajustes WHERE clave=?", (clave,)).fetchone()
    return r[0] if r else defecto


def _filtro(col_p: str, col_u: str, producto, ubicacion) -> tuple[str, list]:
    sql, args = "", []
    if producto:
        sql += f" AND {col_p}=?"
        args.append(producto)
    if ubicacion:
        sql += f" AND {col_u}=?"
        args.append(ubicacion)
    return sql, args


def _eventos(con, producto=None, ubicacion=None, hasta=None):
    """-> {(producto, ubicacion): [(fecha, orden, tipo, valor)]}  orden: 0 entra/sale, 1 consumo, 2 recuento."""
    hasta = hasta or "9999-12-31"
    traslados_bc = ajuste(con, "traslados_en", "bc") == "bc"
    ev = defaultdict(list)
    f, a = _filtro("producto", "almacen", producto, ubicacion)
    bc_acum = defaultdict(float)
    ancla_bc = {}
    for m in con.execute(f"SELECT * FROM bc_movs WHERE almacen<>'' AND fecha<=? {f} ORDER BY fecha, n_mov", [hasta, *a]):
        k = (m["producto"], m["almacen"])
        bc_acum[k] += m["cantidad"]
        if m["tipo"].startswith("Ajuste"):
            ancla_bc[(k, m["fecha"])] = bc_acum[k]  # stock real contado por BC al cierre de ese día
        elif m["tipo"] == "Compra" or traslados_bc:
            ev[k].append((m["fecha"], 0, "bc", m["cantidad"]))
    for (k, fecha), valor in ancla_bc.items():
        ev[k].append((fecha, 2, "recuento_bc", valor))

    f, a = _filtro("l.producto", "COALESCE(c.ubicacion, ce.ubicacion)", producto, ubicacion)
    for r in con.execute(
        f"""SELECT c.fecha, l.producto, COALESCE(c.ubicacion, ce.ubicacion) ub, SUM(l.cantidad) q, c.tipo
            FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id LEFT JOIN centros ce ON ce.codigo=c.servicio
            WHERE c.anulado=0 AND c.fecha<=? {f} GROUP BY 1,2,3,5""", [hasta, *a]
    ):
        if r["ub"]:
            ev[(r["producto"], r["ub"])].append((r["fecha"], 1, r["tipo"], -r["q"]))

    if not traslados_bc:
        for col, signo in (("origen", -1), ("destino", 1)):
            f, a = _filtro("l.producto", f"t.{col}", producto, ubicacion)
            for r in con.execute(
                f"""SELECT t.fecha, l.producto, t.{col} ub, SUM(l.cantidad) q FROM traslados t
                    JOIN traslado_lineas l ON l.traslado_id=t.id WHERE t.anulado=0 AND t.fecha<=? {f} GROUP BY 1,2,3""",
                [hasta, *a],
            ):
                ev[(r["producto"], r["ub"])].append((r["fecha"], 0, "traslado", signo * r["q"]))

    f, a = _filtro("l.producto", "r.ubicacion", producto, ubicacion)
    for r in con.execute(
        f"""SELECT r.fecha, l.producto, r.ubicacion ub, l.contado FROM recuentos r
            JOIN recuento_lineas l ON l.recuento_id=r.id WHERE r.anulado=0 AND r.fecha<=? {f}
            ORDER BY r.creado""", [hasta, *a]
    ):
        ev[(r["producto"], r["ub"])].append((r["fecha"], 3, "recuento", r["contado"]))  # BM cuenta después que BC
    return ev


def stock(con: sqlite3.Connection, ubicacion: str | None = None, producto: str | None = None,
          hasta: str | None = None) -> list[dict]:
    """Stock teórico por (producto, ubicación) con su último recuento y la desviación de ese recuento."""
    out = []
    for (p, u), evs in _eventos(con, producto, ubicacion, hasta).items():
        evs.sort(key=lambda e: (e[0], e[1]))
        s, ult, fuente, desv, salidas = 0.0, None, None, None, 0.0
        for fecha, orden, tipo, v in evs:
            if orden >= 2:
                desv, s, ult, fuente, salidas = v - s, v, fecha, tipo, 0.0
            else:
                s += v
                salidas += -v if v < 0 else 0
        out.append({"producto": p, "ubicacion": u, "stock": round(s, 4), "ultimo_recuento": ult,
                    "fuente_recuento": fuente, "desviacion": None if desv is None else round(desv, 4),
                    "salidas_desde_recuento": round(salidas, 4)})
    return out


def stock_de(con, producto: str, ubicacion: str, hasta: str | None = None) -> float:
    r = stock(con, ubicacion, producto, hasta)
    return r[0]["stock"] if r else 0.0


def _validar_ubicacion(con, codigo: str) -> None:
    if not con.execute("SELECT 1 FROM ubicaciones WHERE codigo=? AND activo=1", (codigo,)).fetchone():
        raise ValueError(f"Ubicación desconocida: {codigo}")


def _validar_items(con, items: list[dict], campo: str) -> list[tuple[str, float]]:
    out = []
    for it in items:
        q = float(it.get(campo) or 0)
        if not con.execute("SELECT 1 FROM productos WHERE codigo=?", (it.get("producto"),)).fetchone():
            raise ValueError(f"Producto desconocido: {it.get('producto')}")
        out.append((it["producto"], q))
    if not out:
        raise ValueError("No hay productos")
    return out


def registrar_traslado(con, *, fecha: str, origen: str, destino: str, items: list[dict],
                       nota: str | None = None, usuario: str | None = None) -> int:
    if ajuste(con, "traslados_en", "bc") != "bm":
        raise ValueError("Los traslados se registran en Business Central. Cámbialo en Configuración para hacerlos en BM.")
    date.fromisoformat(fecha)
    _validar_ubicacion(con, origen)
    _validar_ubicacion(con, destino)
    if origen == destino:
        raise ValueError("Origen y destino son la misma ubicación")
    lineas = [(p, q) for p, q in _validar_items(con, items, "cantidad") if q > 0]
    if not lineas:
        raise ValueError("Indica alguna cantidad mayor que 0")
    tid = con.execute("INSERT INTO traslados(fecha, origen, destino, nota, usuario) VALUES(?,?,?,?,?)",
                      (fecha, origen, destino, nota, usuario)).lastrowid
    con.executemany("INSERT INTO traslado_lineas VALUES(?,?,?)", [(tid, p, q) for p, q in lineas])
    con.commit()
    return tid


def registrar_recuento(con, *, fecha: str, ubicacion: str, lineas: list[dict],
                       nota: str | None = None, usuario: str | None = None) -> int:
    """Solo fija los productos contados (recuento parcial permitido). Guarda el teórico como foto."""
    date.fromisoformat(fecha)
    _validar_ubicacion(con, ubicacion)
    contados = _validar_items(con, lineas, "contado")
    if any(q < 0 for _, q in contados):
        raise ValueError("Una cantidad contada no puede ser negativa")
    teorico = {r["producto"]: r["stock"] for r in stock(con, ubicacion, hasta=fecha)}
    rid = con.execute("INSERT INTO recuentos(fecha, ubicacion, nota, usuario) VALUES(?,?,?,?)",
                      (fecha, ubicacion, nota, usuario)).lastrowid
    con.executemany("INSERT INTO recuento_lineas VALUES(?,?,?,?)",
                    [(rid, p, q, teorico.get(p, 0.0)) for p, q in contados])
    con.commit()
    return rid


def anular(con, tabla: str, id_: int, motivo: str, usuario: str | None = None) -> None:
    if tabla not in ("traslados", "recuentos"):
        raise ValueError("Tabla no anulable")
    if not motivo.strip():
        raise ValueError("Indica el motivo")
    n = con.execute(
        f"UPDATE {tabla} SET anulado=1, nota=COALESCE(nota || ' | ', '') || ? WHERE id=? AND anulado=0",
        (f"ANULADO por {usuario or '?'}: {motivo.strip()}", id_),
    ).rowcount
    if not n:
        raise ValueError("No existe o ya estaba anulado")
    con.commit()


def registrar_caducidad(con, *, producto: str, ubicacion: str | None, cantidad: float, caduca: str,
                        nota: str | None = None, usuario: str | None = None) -> int:
    date.fromisoformat(caduca)
    if ubicacion:
        _validar_ubicacion(con, ubicacion)
    _validar_items(con, [{"producto": producto, "cantidad": cantidad}], "cantidad")
    if cantidad <= 0:
        raise ValueError("Cantidad mayor que 0")
    cid = con.execute("INSERT INTO caducidades(producto, ubicacion, cantidad, caduca, nota, usuario) VALUES(?,?,?,?,?,?)",
                      (producto, ubicacion, cantidad, caduca, nota, usuario)).lastrowid
    con.commit()
    return cid


def cerrar_caducidad(con, cid: int, estado: str, usuario: str | None = None) -> None:
    """usada = se consumió a tiempo. merma = se tira: crea la merma (coste y stock) automáticamente."""
    from bm import consumos

    c = con.execute("SELECT * FROM caducidades WHERE id=? AND estado='activa'", (cid,)).fetchone()
    if not c:
        raise ValueError("No existe o ya está cerrada")
    if estado not in ("usada", "merma"):
        raise ValueError("Estado no válido")
    consumo_id = None
    if estado == "merma":
        centro = con.execute("SELECT codigo FROM centros WHERE ubicacion=? AND activo=1 ORDER BY orden LIMIT 1",
                             (c["ubicacion"],)).fetchone()
        consumo_id = consumos.registrar(
            con, fecha=date.today().isoformat(), servicio=centro[0] if centro else None, tipo="merma",
            ubicacion=c["ubicacion"], items=[{"producto": c["producto"], "cantidad": c["cantidad"]}],
            nota=f"Caducado el {c['caduca']}" + (f" · {c['nota']}" if c["nota"] else ""), usuario=usuario)
    con.execute("UPDATE caducidades SET estado=?, cerrado=CURRENT_TIMESTAMP, consumo_id=? WHERE id=?",
                (estado, consumo_id, cid))
    con.commit()
