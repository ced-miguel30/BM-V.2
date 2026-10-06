import unittest

from bm import consumos, db, inventario as inv


def _base():
    con = db.connect(":memory:")
    con.execute("INSERT INTO productos(codigo, nombre, unidad, categoria) VALUES('P','PRODUCTO','UD','101')")
    movs = [  # n_mov, fecha, tipo, almacen, cantidad, coste_total
        (1, "2026-09-01", "Compra", "ECONOMATO", 10, 10.0),
        (2, "2026-09-02", "Transferencia", "ECONOMATO", -4, -4.0),
        (3, "2026-09-02", "Transferencia", "DESAYUNO", 4, 4.0),
    ]
    con.executemany("INSERT INTO bc_movs(n_mov, fecha, tipo, almacen, producto, cantidad, coste_total) VALUES(?,?,?,?,'P',?,?)", movs)
    inv.sembrar(con)
    return con


def st(con, ub):
    return inv.stock_de(con, "P", ub)


class TestInventario(unittest.TestCase):
    def test_compra_traslado_bc_y_consumo(self):
        con = _base()
        consumos.registrar(con, fecha="2026-09-03", servicio="desayuno", items=[{"producto": "P", "cantidad": 1}])
        self.assertEqual((st(con, "ECONOMATO"), st(con, "RESTAURANTE")), (6, 3))  # desayuno sale de DESAYUNO

    def test_recuento_manda_y_deja_desviacion(self):
        con = _base()
        inv.registrar_recuento(con, fecha="2026-09-03", ubicacion="RESTAURANTE", lineas=[{"producto": "P", "contado": 2.5}])
        r = inv.stock(con, "RESTAURANTE", "P")[0]
        self.assertEqual((r["stock"], r["desviacion"]), (2.5, -1.5))
        self.assertEqual(con.execute("SELECT teorico FROM recuento_lineas").fetchone()[0], 4)

    def test_recuento_bc_es_ancla(self):
        con = _base()
        con.execute("INSERT INTO bc_movs(n_mov, fecha, tipo, almacen, producto, cantidad) VALUES(4,'2026-09-30','Ajuste negativo','DESAYUNO','P',-3)")
        consumos.registrar(con, fecha="2026-09-10", servicio="desayuno", items=[{"producto": "P", "cantidad": 2}])
        r = inv.stock(con, "RESTAURANTE", "P")[0]
        self.assertEqual((r["stock"], r["desviacion"]), (1, -1))  # BC contó 1; BM esperaba 2

    def test_traslados_solo_en_un_sitio(self):
        con = _base()
        item = [{"producto": "P", "cantidad": 2}]
        with self.assertRaises(ValueError):
            inv.registrar_traslado(con, fecha="2026-09-03", origen="ECONOMATO", destino="RESTAURANTE", items=item)
        con.execute("UPDATE ajustes SET valor='bm' WHERE clave='traslados_en'")
        inv.registrar_traslado(con, fecha="2026-09-03", origen="ECONOMATO", destino="RESTAURANTE", items=item)
        self.assertEqual((st(con, "ECONOMATO"), st(con, "RESTAURANTE")), (8, 2))  # los traslados BC ya no cuentan

    def test_almacenes_contables_son_un_sitio_fisico(self):
        con = _base()  # BC: DESAYUNO -> SNACK COMI es un apunte contable; físicamente no se mueve nada
        con.executemany("INSERT INTO bc_movs(n_mov, fecha, tipo, almacen, producto, cantidad) VALUES(?,?,?,?,'P',?)",
                        [(4, "2026-09-04", "Transferencia", "DESAYUNO", -2), (5, "2026-09-04", "Transferencia", "SNACK COMI", 2)])
        inv.sembrar(con)
        self.assertEqual((st(con, "ECONOMATO"), st(con, "RESTAURANTE")), (6, 4))

    def test_zona_por_ubicacion(self):
        con = _base()
        inv.poner_zona(con, "P", "RESTAURANTE", "  nevera ")
        self.assertEqual(inv.zonas(con, "RESTAURANTE"), {"P": "Nevera"})
        self.assertEqual(inv.zonas(con, "ECONOMATO"), {})
        inv.poner_zona(con, "P", "RESTAURANTE", "")
        self.assertEqual(inv.zonas(con, "RESTAURANTE"), {})
        with self.assertRaises(ValueError):
            inv.poner_zona(con, "X", "RESTAURANTE", "Nevera")

    def test_caducidad_a_merma(self):
        con = _base()
        cid = inv.registrar_caducidad(con, producto="P", ubicacion="RESTAURANTE", cantidad=1, caduca="2026-09-05")
        inv.cerrar_caducidad(con, cid, "merma")
        self.assertEqual(st(con, "RESTAURANTE"), 3)
        self.assertEqual(con.execute("SELECT tipo, servicio FROM consumos").fetchone()[:], ("merma", "desayuno"))
        with self.assertRaises(ValueError):
            inv.cerrar_caducidad(con, cid, "usada")


if __name__ == "__main__":
    unittest.main()
