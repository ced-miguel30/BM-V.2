import unittest

from bm import db, tpv


class TestSugerencias(unittest.TestCase):
    def test_no_sugiere_parecidos_falsos(self):
        con = db.connect(":memory:")
        con.executemany("INSERT INTO recetas(id, nombre) VALUES(?,?)",
                        [("r1", "Tarta de queso con helado"), ("r2", "Sandwich club"), ("r3", "Copa Montecillo Rosado")])
        arts = [("A1", "TARTA DE ZANAHORIA"), ("A2", "HABANA CLUB 7"), ("A3", "MONTECILLO ROSÉ"), ("A4", "TARTA DE QUESO")]
        con.executemany("INSERT INTO tpv_articulos(codigo, nombre) VALUES(?,?)", arts)
        con.executemany("INSERT INTO tpv_ventas VALUES('2026-09-01',?,10)", [(c,) for c, _ in arts])
        s = tpv.sugerencias(con)
        self.assertNotIn("A1", s)
        self.assertNotIn("A2", s)
        self.assertEqual(s["A3"]["id"], "r3")
        self.assertEqual(s["A4"]["id"], "r1")


if __name__ == "__main__":
    unittest.main()
