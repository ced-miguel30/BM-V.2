import unittest
from datetime import date, timedelta

from bm import consumos, db, inventario, prevision

HOY = date.today()


def dia(n: int) -> str:
    return (HOY - timedelta(days=n)).isoformat()


def _base():
    con = db.connect(":memory:")
    con.executemany("INSERT INTO productos(codigo, nombre, unidad, categoria) VALUES(?,?,'UD','101')", [("P", "LECHE"), ("Q", "AZUCAR")])
    movs = [  # n_mov, fecha, tipo, tipo_doc, almacen, producto, cantidad, coste_total
        (1, dia(35), "Compra", "Albarán compra", "ECONOMATO", "P", 100, 100.0),
        (2, dia(35), "Ajuste positivo", "", "ECONOMATO", "P", 0, 0),       # inventario: 100
        (3, dia(5), "Ajuste negativo", "", "ECONOMATO", "P", -95, -95.0),  # inventario: 5 -> se gastan 95 en 30 días
        (4, dia(30), "Compra", "Albarán compra", "ECONOMATO", "Q", 50, 50.0),
        (5, dia(20), "Transferencia", "", "ECONOMATO", "Q", -10, -10.0),
        (6, dia(20), "Transferencia", "", "DESAYUNO", "Q", 10, 10.0),
    ]
    con.executemany("""INSERT INTO bc_movs(n_mov, fecha, tipo, tipo_doc, almacen, producto, cantidad, coste_total, proveedor, documento)
                       VALUES(?,?,?,?,?,?,?,?,'GRANJA','AL1')""", movs)
    inventario.sembrar(con)
    con.execute("UPDATE proveedores SET dias_reparto='0,1,2,3,4,5,6', plazo_dias=2 WHERE nombre='GRANJA'")
    consumos.registrar(con, fecha=dia(10), servicio="desayuno", items=[{"producto": "Q", "cantidad": 10}])
    return con


class TestPrevision(unittest.TestCase):
    def test_ritmo_real_y_stock_estimado(self):
        d = prevision.analizar(_base(), {"HOTEL": prevision.FB})[("P", "HOTEL")]
        self.assertAlmostEqual(d["ritmo"], 95 / 30, places=3)
        self.assertEqual(d["estimado"], 0)  # quedaban 5 hace 5 días y se gastan ~3,2 al día

    def test_pedido_redondeado_al_lote_y_comprar_por_fuera(self):
        r = prevision.pedidos(_base())
        lineas = {l["producto"]: l for p in r["pedidos"] for l in p["lineas"]}
        self.assertEqual(lineas["P"]["pedir"], 100)  # se compra en lotes de 100
        self.assertIn("P", {u["producto"] for u in r["urgentes"]})  # se acaba antes del reparto

    def test_reposicion_restaurante(self):
        r = {x["producto"]: x for x in prevision.reposicion(_base())}
        self.assertIn("Q", r)  # subió 10 al restaurante y se gastaron 10: queda 0
        self.assertTrue(1 <= r["Q"]["subir"] <= 40)
        self.assertEqual(r["Q"]["economato"], 40)


if __name__ == "__main__":
    unittest.main()
