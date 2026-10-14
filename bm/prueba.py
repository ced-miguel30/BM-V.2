"""Base de PRUEBA para enseñar BM o probarlo en el móvil: productos, platos y un usuario por perfil inventados.

    python -m bm.prueba [--db datos\\prueba.sqlite] [--clave prueba2026]

Nunca toca la base real (bm.sqlite). Idempotente: repetirlo no duplica nada.
"""

from __future__ import annotations

import argparse
from pathlib import Path

PRODUCTOS = [  # codigo, nombre, unidad, categoria, almacen BC, cantidad comprada, coste total
    ("P001", "HUEVO CASCARA L", "UD", "101", "DESAYUNO", 360, 90),
    ("P002", "PAN MOLDE", "UD", "101", "DESAYUNO", 20, 40),
    ("P003", "LECHE ENTERA 1L", "L", "101", "DESAYUNO", 48, 43),
    ("P004", "LECHE SIN LACTOSA 1L", "L", "101", "DESAYUNO", 24, 26),
    ("P005", "ZUMO NARANJA BRIK 1L", "L", "101", "DESAYUNO", 30, 45),
    ("P006", "BACON LONCHAS KG", "KG", "101", "DESAYUNO", 5, 40),
    ("P007", "QUESO CHEDDAR LONCHAS KG", "KG", "101", "DESAYUNO", 3, 27),
    ("P008", "JAMON COCIDO KG", "KG", "101", "DESAYUNO", 4, 36),
    ("P009", "AGUACATE KG", "KG", "102", "DESAYUNO", 6, 30),
    ("P010", "TOMATE KG", "KG", "102", "DESAYUNO", 10, 18),
    ("P011", "MANTEQUILLA PORCIONES", "UD", "101", "DESAYUNO", 200, 30),
    ("P012", "CAFE GRANO KG", "KG", "103", "DESAYUNO", 6, 108),
    ("P013", "COCA-COLA LATA 33CL", "UD", "104", "SNACK BEBI", 96, 48),
    ("P014", "AGUA 50CL", "UD", "104", "SNACK BEBI", 120, 24),
    ("P015", "CERVEZA 33CL", "UD", "104", "SNACK BEBI", 72, 50),
    ("P016", "PATATAS FRITAS BOLSA", "UD", "105", "SNACK COMI", 40, 20),
    ("P017", "ACEITE OLIVA 5L", "UD", "106", "ECONOMATO", 4, 110),
    ("P018", "AZUCAR SOBRES CAJA", "UD", "106", "ECONOMATO", 5, 25),
    ("P019", "HARINA KG", "KG", "106", "ECONOMATO", 10, 9),
    ("P020", "SALMON AHUMADO KG", "KG", "101", "DESAYUNO", 2, 52),
]
RECETAS = [  # id, nombre, servicio, [(producto, cantidad)]
    ("prueba-d1", "Huevos con bacon", "desayuno", [("P001", 2), ("P006", 0.04)]),
    ("prueba-d2", "Tostada con aguacate", "desayuno", [("P002", 0.1), ("P009", 0.08)]),
    ("prueba-d3", "Tostada con tomate", "desayuno", [("P002", 0.1), ("P010", 0.06)]),
    ("prueba-d4", "Sandwich mixto", "desayuno", [("P002", 0.1), ("P008", 0.03), ("P007", 0.02)]),
    ("prueba-d5", "Tortilla francesa", "desayuno", [("P001", 2)]),
    ("prueba-d6", "Salmon con huevo", "desayuno", [("P020", 0.05), ("P001", 1)]),
    ("prueba-b1", "Americano", "bebidas", [("P012", 0.008)]),
    ("prueba-b2", "Cafe con leche", "bebidas", [("P012", 0.008), ("P003", 0.1)]),
    ("prueba-b3", "Zumo de naranja", "bebidas", [("P005", 0.2)]),
]
ATAJOS = [  # etiqueta, grupo, producto, cantidad
    ("Bacon", "extra", "P006", 0.02), ("Queso cheddar", "extra", "P007", 0.02), ("Jamon york", "extra", "P008", 0.03),
    ("Aguacate", "extra", "P009", 0.05), ("Leche sin lactosa", "leche", "P004", 0.1), ("Sin tomate", "omitir", None, 0),
]
USUARIOS = [("dueno", "Dueño", "direccion"), ("admin", "Administración", "administracion"),
            ("jefe", "Jefe restaurante", "jefe"), ("cocina", "Cocina", "cocina"), ("comandero", "Comandero", "comandero")]


def crear(con, clave: str) -> None:
    from bm import inventario, usuarios
    con.executemany("INSERT OR IGNORE INTO productos(codigo, nombre, unidad, categoria) VALUES(?,?,?,?)",
                    [p[:4] for p in PRODUCTOS])
    con.executemany("""INSERT OR IGNORE INTO bc_movs(n_mov, fecha, tipo, almacen, producto, cantidad, coste_total,
                       documento, proveedor, tipo_doc) VALUES(?, date('now', '-7 days'), 'Compra', ?, ?, ?, ?, ?,
                       'PROVEEDOR PRUEBA SL', 'Albarán compra')""",
                    [(i + 1, p[4], p[0], p[5], p[6], f"PRUEBA{i + 1:03d}") for i, p in enumerate(PRODUCTOS)])
    for rid, nombre, servicio, lineas in RECETAS:
        con.execute("INSERT OR IGNORE INTO recetas(id, nombre, servicio, porciones) VALUES(?,?,?,1)", (rid, nombre, servicio))
        con.executemany("INSERT OR IGNORE INTO receta_lineas VALUES(?,?,?)", [(rid, p, q) for p, q in lineas])
    con.executemany("""INSERT OR REPLACE INTO atajos(etiqueta, grupo, producto, receta_id, cantidad, sustituye, activo)
                       VALUES(?, ?, ?, NULL, ?, NULL, 1)""", ATAJOS)
    con.commit()
    inventario.sembrar(con)
    for login, nombre, rol in USUARIOS:
        usuarios.guardar(con, login, nombre, rol, clave)
    con.commit()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(Path(__file__).resolve().parent.parent / "datos" / "prueba.sqlite"))
    ap.add_argument("--clave", default="prueba2026")
    a = ap.parse_args(argv)
    if Path(a.db).name == "bm.sqlite":
        raise SystemExit("Esto es la base real: la de prueba debe tener otro nombre (por ejemplo prueba.sqlite).")
    Path(a.db).parent.mkdir(parents=True, exist_ok=True)
    from bm import db
    con = db.connect(a.db)
    try:
        crear(con, a.clave)
    finally:
        con.close()
    print(f"Base de prueba lista en {a.db}")
    print("Usuarios (contraseña " + a.clave + "): " + ", ".join(u[0] for u in USUARIOS))


if __name__ == "__main__":
    main()
