import unittest
from datetime import date

from bm import db
from bm.excel import Fila, Resolver


def _base():
    con = db.connect(":memory:")
    con.executemany("INSERT INTO productos(codigo, nombre, unidad, categoria) VALUES(?,?,?,'101')", [
        ("HUEVO", "HUEVO CASCARA", "UD"), ("MOLDE", "MOLDE COMUN", "UD"), ("INTEGRAL", "MOLDE INTEGRAL", "UD"),
        ("BACON", "BACON", "KG"), ("CHAMPI", "CHAMPINON LAMINADO", "KG")])
    con.execute("INSERT INTO recetas(id, nombre, porciones) VALUES('r1','Desayuno ingles',1)")
    con.executemany("INSERT INTO receta_lineas VALUES('r1',?,?)", [("HUEVO", 1), ("MOLDE", 0.0625), ("BACON", 0.02), ("CHAMPI", 0.01)])
    con.executemany("INSERT INTO atajos(etiqueta, grupo, producto, cantidad, sustituye) VALUES(?,?,?,?,?)", [
        ("Huevo pochado", "extra", "HUEVO", 1, "huevo"), ("Tostada", "extra", "MOLDE", 0.03125, "pan"),
        ("Tostada integral", "extra", "INTEGRAL", 0.03125, "pan"), ("Bacon", "extra", "BACON", 0.015, None),
        ("Sin huevo", "omitir", None, 0, "huevo")])
    con.executemany("INSERT INTO sustitucion VALUES(?,?)", [("huevo", "HUEVO"), ("pan", "MOLDE"), ("pan", "INTEGRAL")])
    return con


def fila(nombre="Desayuno ingles", cantidad=1, extras=(), omitir=()):
    return Fila("Registro", 2, date(2026, 10, 1), "receta", nombre, cantidad, 1, list(extras), list(omitir))


def total(lineas):
    out = {}
    for p, q, _ in lineas:
        out[p] = round(out.get(p, 0) + q, 6)
    return out


class TestExcelDesayuno(unittest.TestCase):
    def setUp(self):
        self.r = Resolver(_base())

    def test_receta_y_extra(self):
        t = total(self.r.fila(fila(cantidad=2, extras=[("Bacon", 1)])))
        self.assertEqual(t["HUEVO"], 2)
        self.assertEqual(t["BACON"], 0.055)  # 2 x 0,02 de ficha + 1 extra de 0,015

    def test_pan_integral_sustituye_mismas_rebanadas(self):
        t = total(self.r.fila(fila(cantidad=2, extras=[("Tostada integral", 1)])))
        self.assertNotIn("MOLDE", t)
        self.assertEqual(t["INTEGRAL"], 0.125)  # 2 raciones x 2 rebanadas

    def test_huevo_pochado_no_suma_segundo_huevo(self):
        self.assertEqual(total(self.r.fila(fila(extras=[("Huevo pochado", 1)])))["HUEVO"], 1)

    def test_omitir(self):
        t = total(self.r.fila(fila(omitir=["Sin huevo", "Champinon laminado"])))
        self.assertNotIn("HUEVO", t)
        self.assertNotIn("CHAMPI", t)

    def test_desconocido_es_error(self):
        with self.assertRaises(ValueError):
            self.r.fila(fila(nombre="Plato inventado"))
        with self.assertRaises(ValueError):
            self.r.fila(fila(omitir=["Caviar"]))


if __name__ == "__main__":
    unittest.main()
