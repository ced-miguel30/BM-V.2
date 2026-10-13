import unittest
from datetime import date, timedelta

from bm import analisis, cierre, consumos, db, inventario as inv, noray


def _base():
    """10 latas en el economato; Noray pasa 4 a DESAYUNO y 6 a SNACK BEBI (las dos están en Restaurante)."""
    con = db.connect(":memory:")
    con.execute("INSERT INTO productos(codigo, nombre, unidad) VALUES('P','LATA','UD')")
    movs = [(1, "2026-09-01", "Compra", "ECONOMATO", 16), (2, "2026-09-02", "Transferencia", "ECONOMATO", -10),
            (3, "2026-09-02", "Transferencia", "DESAYUNO", 4), (4, "2026-09-02", "Transferencia", "SNACK BEBI", 6)]
    con.executemany("INSERT INTO bc_movs(n_mov, fecha, tipo, almacen, producto, cantidad, coste_total) VALUES(?,?,?,?,'P',?,?)",
                    [(*m, m[4] * 1.0) for m in movs])
    inv.sembrar(con)
    return con


def lineas(con, hasta="2026-09-30"):
    return {(x["almacen"]): x["fisica"] for x in noray.cierre(con, hasta)}


class TestNoray(unittest.TestCase):
    def test_reparto_entero_no_parte_latas(self):
        self.assertEqual(noray.reparto(7, {"A": 1, "B": 1}, True), {"A": 4.0, "B": 3.0})
        self.assertEqual(noray.reparto(1.5, {"A": 1, "B": 2}, False), {"A": 0.5, "B": 1.0})

    def test_lo_gastado_por_un_centro_sale_de_su_almacen(self):
        con = _base()
        consumos.registrar(con, fecha="2026-09-10", servicio="bebidas", items=[{"producto": "P", "cantidad": 5}])
        self.assertEqual(lineas(con), {"ECONOMATO": 6, "DESAYUNO": 4, "SNACK BEBI": 1})

    def test_recuento_de_bm_se_reparte_y_dice_que_es_contado(self):
        con = _base()
        consumos.registrar(con, fecha="2026-09-10", servicio="bebidas", items=[{"producto": "P", "cantidad": 2}])
        inv.registrar_recuento(con, fecha="2026-09-20", ubicacion="RESTAURANTE", lineas=[{"producto": "P", "contado": 6}])
        r = {x["almacen"]: x for x in noray.cierre(con, "2026-09-30")}
        self.assertEqual((r["DESAYUNO"]["fisica"], r["SNACK BEBI"]["fisica"]), (3, 3))  # objetivos 4 y 4 → 6 a partes iguales
        self.assertEqual(r["SNACK BEBI"]["calculada"], 6)
        self.assertTrue(r["SNACK BEBI"]["origen"].startswith("Contado 20/09"))

    def test_lo_que_noray_no_tiene_alli_va_a_su_almacen_principal(self):
        con = _base()
        con.execute("INSERT INTO productos(codigo, nombre, unidad) VALUES('Q','NUEVO','UD')")
        con.execute("INSERT INTO bc_movs(n_mov, fecha, tipo, almacen, producto, cantidad) VALUES(9,'2026-09-03','Transferencia','DESAYUNO','P',-1)")
        inv.registrar_recuento(con, fecha="2026-09-20", ubicacion="RESTAURANTE", lineas=[{"producto": "Q", "contado": 2}])
        q = [x for x in noray.cierre(con, "2026-09-30") if x["producto"] == "Q"]
        self.assertEqual([(x["almacen"], x["calculada"], x["fisica"]) for x in q], [("DESAYUNO", 0, 2)])  # el más usado


class TestRecomendadosYRaros(unittest.TestCase):
    def test_fresco_se_recomienda_hasta_contarlo(self):
        con = _base()
        hoy = date.today()
        con.executemany("INSERT INTO bc_movs(n_mov, fecha, tipo, almacen, producto, cantidad, coste_total) VALUES(?,?,'Compra','ECONOMATO','P',1,1)",
                        [(10 + i, (hoy - timedelta(days=7 * i + 1)).isoformat()) for i in range(4)])  # casi cada semana
        con.execute("INSERT INTO bc_movs(n_mov, fecha, tipo, almacen, producto, cantidad) VALUES(20,?,'Transferencia','ECONOMATO','P',-1)",
                    ((hoy - timedelta(days=2)).isoformat(),))  # y se mueve
        r = cierre.recomendados(con, "ECONOMATO", hoy.replace(day=1).isoformat())
        self.assertIn("fresco", r[0]["motivos"])
        inv.registrar_recuento(con, fecha=hoy.isoformat(), ubicacion="ECONOMATO", lineas=[{"producto": "P", "contado": 5}])
        self.assertEqual(cierre.recomendados(con, "ECONOMATO", hoy.replace(day=1).isoformat()), [])

    def test_actividad_que_se_dispara_avisa(self):
        con = _base()
        hoy = date(2026, 9, 30)
        for i in range(70):  # 1 al día durante 8 semanas, 5 al día las dos últimas
            d = hoy - timedelta(days=i)
            consumos.registrar(con, fecha=d.isoformat(), servicio="bebidas", items=[{"producto": "P", "cantidad": 5 if i < 14 else 1}])
        raros = analisis.anomalias(con, hoy)
        self.assertEqual([x["tipo"] for x in raros], ["actividad"])
        self.assertIn("más actividad", raros[0]["detalle"])

    def test_recuento_con_mucha_falta_avisa_de_revisar_receta(self):
        con = _base()
        hoy = date(2026, 9, 30)
        con.execute("UPDATE bc_movs SET coste_total=cantidad*10")  # 10 € la lata
        consumos.registrar(con, fecha="2026-09-25", servicio="bebidas", items=[{"producto": "P", "cantidad": 1}])
        inv.registrar_recuento(con, fecha="2026-09-29", ubicacion="RESTAURANTE", lineas=[{"producto": "P", "contado": 5}])
        raros = analisis.anomalias(con, hoy)  # esperaba 9, hay 5: faltan 4 con solo 1 gastado
        self.assertEqual(raros[0]["tipo"], "recuento")
        self.assertIn("revisa la receta", raros[0]["detalle"])


if __name__ == "__main__":
    unittest.main()
