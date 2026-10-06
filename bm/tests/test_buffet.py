import unittest
from datetime import date, timedelta

from bm import buffet, consumos, db, inventario

AYER = (date.today() - timedelta(days=1)).isoformat()
HOY = date.today().isoformat()


def _base():
    con = db.connect(":memory:")
    con.execute("INSERT INTO productos(codigo, nombre, unidad, categoria) VALUES('CRO', 'CROISSANT', 'UD', '101')")
    con.execute("INSERT INTO bc_movs(n_mov, fecha, tipo, almacen, producto, cantidad, coste_total) VALUES(1, ?, 'Compra', 'DESAYUNO', 'CRO', 500, 150)",
                ((date.today() - timedelta(days=10)).isoformat(),))
    inventario.sembrar(con)
    con.execute("INSERT INTO atajos(etiqueta, grupo, producto, cantidad, seccion) VALUES('Croissant', 'buffet', 'CRO', 1, 'Bollería')")
    con.commit()
    for f, n in ((AYER, 20), (HOY, 30)):  # el registro del desayuno trae los comensales
        consumos.registrar(con, fecha=f, servicio="desayuno", comensales=n, items=[{"producto": "CRO", "cantidad": 0.001}])
    return con


class TestBuffet(unittest.TestCase):
    def test_confirmar_corregir_y_aprender(self):
        con = _base()
        buffet.confirmar(con, AYER, [{"etiqueta": "Croissant", "sacado": 50, "sobro": 10}], 20, "t")
        buffet.confirmar(con, AYER, [{"etiqueta": "Croissant", "sacado": 50, "sobro": 10}], 20, "t")  # corregir no duplica
        q = con.execute("SELECT SUM(l.cantidad) FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id WHERE c.ref=?", (f"buffet:{AYER}",)).fetchone()[0]
        self.assertEqual(q, 40)  # sacado - sobró
        item = buffet.propuesta(con, HOY)["items"][0]
        self.assertEqual((item["por_comensal"], item["propuesta"]), (2.0, 60))  # 40 croissants / 20 comensales x 30 de hoy

    def test_sobra_mas_de_lo_sacado(self):
        with self.assertRaises(ValueError):
            buffet.confirmar(_base(), HOY, [{"etiqueta": "Croissant", "sacado": 5, "sobro": 6}], 30, "t")


if __name__ == "__main__":
    unittest.main()
