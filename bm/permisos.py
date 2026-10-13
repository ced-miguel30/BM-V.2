"""Lo que administración decide abrir (o dejar confidencial) para cada perfil del personal.

Dueño y administración lo ven siempre todo. Lo elegido se guarda en ajustes['permisos'] como {perfil: [claves]};
un perfil que nunca se ha tocado tiene los permisos por defecto.
"""

from __future__ import annotations

import json
import sqlite3

GESTION = ("direccion", "administracion")
CATALOGO = [  # clave, nombre, qué abre, perfiles a los que se puede dar, perfiles que lo tienen por defecto
    ("euros", "Ver euros", "Valor del stock, precios y diferencias de recuento en euros", ("jefe",), ("jefe",)),
    ("stock", "Pantalla Stock", "Cuánto hay de cada producto en cada sitio", ("jefe",), ("jefe",)),
    ("perdidas", "Pérdidas", "Análisis de mermas, comida de personal y diferencias (necesita «Ver euros»)", ("jefe",), ("jefe",)),
    ("traslados", "Traslados", "Ver y registrar traslados entre almacenes", ("jefe",), ("jefe",)),
    ("recetas", "Recetas", "Ver y ajustar las fichas de receta, con su coste", ("jefe",), ()),
    ("solicitar", "Pedir a administración", "Enviar solicitudes de pedido a administración", ("jefe",), ("jefe",)),
    ("comandas", "Comandas de desayuno", "Apuntar los desayunos", ("cocina",), ()),
]
CLAVES = [c[0] for c in CATALOGO]


def _guardado(con) -> dict:
    r = con.execute("SELECT valor FROM ajustes WHERE clave='permisos'").fetchone()
    try:
        return json.loads(r[0]) if r else {}
    except ValueError:
        return {}


def de(con: sqlite3.Connection, rol: str) -> list[str]:
    if rol in GESTION:
        return list(CLAVES)
    elegido = _guardado(con).get(rol)
    return [c for c, _, _, posibles, defecto in CATALOGO
            if rol in posibles and (c in elegido if elegido is not None else rol in defecto)]


def todos(con: sqlite3.Connection) -> dict:
    perfiles = [r for r in ("jefe", "cocina", "comandero") if any(r in c[3] for c in CATALOGO)]  # por jerarquía
    return {"catalogo": [{"clave": c, "nombre": n, "detalle": d, "perfiles": list(p)} for c, n, d, p, _ in CATALOGO],
            "actual": {r: de(con, r) for r in perfiles},
            "directos": {"jefe": proveedores_directos(con, "jefe")},
            "proveedores": [x[0] for x in con.execute(  # los que se compran de verdad, más usados primero
                """SELECT proveedor FROM bc_movs WHERE tipo='Compra' AND proveedor<>'' GROUP BY 1 ORDER BY COUNT(*) DESC""")]}


def proveedores_directos(con: sqlite3.Connection, rol: str) -> list[str]:
    """Proveedores a los que ese perfil puede hacer el pedido él mismo (lo decide administración). Gestión: todos."""
    r = con.execute("SELECT valor FROM ajustes WHERE clave='pedido_directo'").fetchone()
    try:
        return json.loads(r[0]).get(rol, []) if r else []
    except ValueError:
        return []


def guardar_proveedores(con: sqlite3.Connection, rol: str, proveedores: list[str]) -> None:
    if rol != "jefe":
        raise ValueError("Solo el jefe de restaurante puede tener pedido directo")
    r = con.execute("SELECT valor FROM ajustes WHERE clave='pedido_directo'").fetchone()
    actual = json.loads(r[0]) if r else {}
    validos = {x[0] for x in con.execute("SELECT nombre FROM proveedores")}
    actual[rol] = sorted(p for p in set(proveedores) if p in validos)
    con.execute("INSERT OR REPLACE INTO ajustes VALUES('pedido_directo', ?)", (json.dumps(actual),))
    con.commit()


def guardar(con: sqlite3.Connection, elegido: dict[str, list[str]]) -> None:
    validos = {r: {c[0] for c in CATALOGO if r in c[3]} for c in CATALOGO for r in c[3]}  # perfil -> claves que se le pueden dar
    limpio = {}
    for rol, claves in elegido.items():
        if rol not in validos:
            raise ValueError(f"Perfil no válido: {rol}")
        limpio[rol] = [c for c in CLAVES if c in claves and c in validos[rol]]
    con.execute("INSERT OR REPLACE INTO ajustes VALUES('permisos', ?)", (json.dumps({**_guardado(con), **limpio}),))
    con.commit()
