import unittest
from datetime import date

from bm import comandas, db
from bm.tests.test_excel import _base

HOY = date.today().isoformat()


class TestComandas(unittest.TestCase):
    def _total(self, con):
        return dict(con.execute("""SELECT l.producto, ROUND(SUM(l.cantidad), 6) FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id
                                   WHERE c.ref=? GROUP BY 1""", (f"comandas:{HOY}",)).fetchall())

    def test_tocar_platos_extras_y_comensales(self):
        con = _base()
        comandas.anadir(con, fecha=HOY, nombre="Desayuno ingles", extras=[("Huevo pochado", 1), ("Bacon", 1)])
        lid = comandas.anadir(con, fecha=HOY, nombre="Desayuno ingles", cantidad=2, omitir=["Sin huevo"])
        comandas.poner_comensales(con, HOY, 3)
        t = self._total(con)
        self.assertEqual(t["HUEVO"], 1)  # el pochado sustituye al frito; los otros dos platos van sin huevo
        self.assertEqual(t["BACON"], 0.075)  # 3 x 0,02 de ficha + 0,015 de extra
        comandas.quitar(con, lid)
        self.assertEqual(self._total(con)["BACON"], 0.035)
        self.assertEqual(con.execute("SELECT comensales FROM consumos WHERE ref=?", (f"comandas:{HOY}",)).fetchone()[0], 3)

    def test_comensales_automaticos_cuentan_platos(self):
        con = _base()
        con.execute("UPDATE recetas SET servicio='desayuno' WHERE id='r1'")
        comandas.anadir(con, fecha=HOY, nombre="Desayuno ingles", cantidad=2)
        comandas.anadir(con, fecha=HOY, nombre="Desayuno ingles")
        self.assertEqual(comandas.dia(con, HOY)["comensales"], 3)

    def test_comandero_envia_la_mesa_entera_una_sola_vez(self):
        con = _base()
        con.execute("UPDATE recetas SET servicio='desayuno' WHERE id='r1'")  # cada plato de desayuno es un huésped
        mesa = [{"nombre": "Desayuno ingles", "extras": [["Bacon", 1]]}, {"nombre": "Desayuno ingles", "omitir": ["Sin huevo"]}]
        self.assertEqual(comandas.enviar_mesa(con, fecha=HOY, mesa="12", lineas=mesa, ref="movil-7"), 2)
        self.assertEqual(comandas.enviar_mesa(con, fecha=HOY, mesa="12", lineas=mesa, ref="movil-7"), 0)  # reenvío sin cobertura
        d = comandas.dia(con, HOY)
        self.assertEqual(([l["mesa"] for l in d["lineas"]], d["comensales"]), (["12", "12"], 2))
        self.assertEqual(self._total(con)["BACON"], 0.055)  # 2 x 0,02 de ficha + 0,015 de extra
        with self.assertRaises(ValueError):  # un plato que no se entiende: no se apunta nada de la mesa
            comandas.enviar_mesa(con, fecha=HOY, mesa="3", lineas=[{"nombre": "Desayuno ingles"}, {"nombre": "Plato inventado"}])
        self.assertEqual(len(comandas.dia(con, HOY)["lineas"]), 2)

    def test_plato_desconocido_no_se_apunta(self):
        con = _base()
        with self.assertRaises(ValueError):
            comandas.anadir(con, fecha=HOY, nombre="Plato inventado xyz")
        self.assertEqual(con.execute("SELECT COUNT(*) FROM comanda_lineas").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
