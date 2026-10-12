import unittest
from datetime import date, timedelta

from bm import consumos, db, intercambiables

HOY = date.today()


def dia(n):
    return (HOY - timedelta(days=n)).isoformat()


class TestIntercambiables(unittest.TestCase):
    def setUp(self):
        self.con = con = db.connect(":memory:")
        con.executemany("INSERT INTO productos(codigo, nombre, unidad, categoria) VALUES(?,?,'UD','101')",
                        [("ROMANA", "LECHUGA ROMANA"), ("ROBLE", "LECHUGA HOJA DE ROBLE"), ("LOLLO", "LECHUGA LOLLO ROSA")])
        con.execute("INSERT INTO productos(codigo, nombre, unidad, categoria) VALUES('KILO', 'ALGO', 'KG', '101')")
        con.executemany("""INSERT INTO bc_movs(n_mov, fecha, tipo, almacen, producto, cantidad, coste_total) VALUES(?,?,'Compra','ECONOMATO',?,?,?)""",
                        [(1, "2025-08-01", "ROMANA", 10, 9.0), (2, dia(5), "ROBLE", 10, 14.0), (3, dia(3), "LOLLO", 10, 15.0)])
        con.execute("INSERT INTO recetas(id, nombre, servicio) VALUES('r', 'Ensalada', 'comida')")
        con.execute("INSERT INTO receta_lineas VALUES('r', 'ROMANA', 0.5)")
        con.commit()
        intercambiables.poner(con, "Lechugas", ["ROMANA", "ROBLE", "LOLLO"])

    def test_usa_la_comprada_mas_barata_y_si_no_la_que_caduca_antes(self):
        cid = consumos.registrar(self.con, fecha=HOY.isoformat(), servicio="comida", items=[{"receta_id": "r", "cantidad": 2}])
        self.assertEqual(self.con.execute("SELECT producto FROM consumo_lineas WHERE consumo_id=?", (cid,)).fetchone()[0], "ROBLE")
        self.con.execute("INSERT INTO caducidades(producto, cantidad, caduca) VALUES('LOLLO', 3, ?)", ((HOY + timedelta(days=1)).isoformat(),))
        self.con.commit()
        cid = consumos.registrar(self.con, fecha=HOY.isoformat(), servicio="comida", items=[{"receta_id": "r", "cantidad": 1}])
        self.assertEqual(self.con.execute("SELECT producto FROM consumo_lineas WHERE consumo_id=?", (cid,)).fetchone()[0], "LOLLO")
        self.assertEqual(consumos.coste_receta(self.con, "r")["lineas"][0]["usa"], "LOLLO")

    def test_producto_directo_no_se_cambia_y_unidades_iguales(self):
        cid = consumos.registrar(self.con, fecha=HOY.isoformat(), servicio="comida", items=[{"producto": "ROMANA", "cantidad": 1}])
        self.assertEqual(self.con.execute("SELECT producto FROM consumo_lineas WHERE consumo_id=?", (cid,)).fetchone()[0], "ROMANA")
        with self.assertRaises(ValueError):
            intercambiables.poner(self.con, "Mal", ["ROMANA", "KILO"])


    def test_semillas_de_carta_no_pisan(self):
        import json
        import tempfile
        from pathlib import Path
        f = Path(tempfile.mkdtemp()) / "carta.json"
        f.write_text(json.dumps({"intercambiables": {"Lechugas": ["ROMANA", "ROBLE"]}, "recetas": [
            {"id": "c_x", "nombre": "Ensalada nueva", "servicio": "comida", "porciones": 1, "nota": "estimada", "lineas": [["ROBLE", 1]], "tpv": "PV1"}]}),
            encoding="utf-8")
        self.con.execute("INSERT INTO tpv_articulos(codigo, nombre) VALUES('PV1', 'ENSALADA')")
        r = intercambiables.sembrar_carta(self.con, f)
        self.assertEqual(r, {"grupos": 0, "recetas": 1, "tpv": 1})  # el grupo Lechugas ya existía: no se toca
        self.assertEqual(len(intercambiables.grupos(self.con)["Lechugas"]), 3)
        self.assertEqual(intercambiables.sembrar_carta(self.con, f), {"grupos": 0, "recetas": 0, "tpv": 0})


if __name__ == "__main__":
    unittest.main()
