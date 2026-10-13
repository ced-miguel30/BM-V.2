import unittest
from datetime import date, timedelta

from bm import pedidos, prevision
from bm.tests.test_prevision import _base, dia


def _albaran(con, n_mov, doc, producto, cantidad, fecha):
    con.execute("""INSERT INTO bc_movs(n_mov, fecha, tipo, tipo_doc, almacen, producto, cantidad, coste_total, proveedor, documento)
                   VALUES(?,?,'Compra','Albarán compra','ECONOMATO',?,?,?,'GRANJA',?)""", (n_mov, fecha, producto, cantidad, cantidad, doc))
    con.commit()


class TestPedidos(unittest.TestCase):
    def test_lo_pedido_no_se_vuelve_a_proponer(self):
        con = _base()
        antes = {l["producto"]: l["pedir"] for p in prevision.pedidos(con)["pedidos"] for l in p["lineas"]}
        pedidos.crear(con, proveedor="GRANJA", entrega=dia(-2), lineas=[{"producto": "P", "cantidad": antes["P"]}])
        despues = {l["producto"]: l["pedir"] for p in prevision.pedidos(con)["pedidos"] for l in p["lineas"]}
        self.assertNotIn("P", despues)

    def test_albaran_completo_e_incompleto(self):
        con = _base()
        a = pedidos.crear(con, proveedor="GRANJA", entrega=dia(-1), lineas=[{"producto": "P", "cantidad": 100}])
        _albaran(con, 50, "ALB-1", "P", 100, date.today().isoformat())
        b = pedidos.crear(con, proveedor="GRANJA", entrega=dia(-1), lineas=[{"producto": "P", "cantidad": 100}, {"producto": "Q", "cantidad": 10}])
        _albaran(con, 51, "ALB-2", "P", 60, date.today().isoformat())
        self.assertEqual(pedidos.conciliar(con), 2)
        estados = {p["id"]: p for p in pedidos.listar(con)}
        self.assertEqual(estados[a]["estado"], "recibido")
        self.assertEqual((estados[b]["estado"], estados[b]["albaranes"]), ("incompleto", "ALB-2"))
        self.assertEqual({f["producto"]: f["falta"] for f in pedidos.faltas(con, b)}, {"P": 40, "Q": 10})
        _albaran(con, 52, "ALB-3", "Q", 10, date.today().isoformat())  # llega el resto
        _albaran(con, 53, "ALB-4", "P", 40, date.today().isoformat())
        pedidos.conciliar(con)
        self.assertEqual({p["id"]: p["estado"] for p in pedidos.listar(con)}[b], "recibido")
        c = pedidos.crear(con, proveedor="GRANJA", entrega=dia(-1), lineas=[{"producto": "Q", "cantidad": 5}])
        pedidos.cerrar(con, c, "anulado", "no se pidió", "ADM")
        self.assertEqual({p["id"]: p["estado"] for p in pedidos.listar(con)}[c], "anulado")

    def test_sin_albaran_y_entrega_pasada_es_retrasado(self):
        con = _base()
        pedidos.crear(con, proveedor="GRANJA", entrega=(date.today() - timedelta(days=3)).isoformat(),
                      lineas=[{"producto": "P", "cantidad": 5}])
        self.assertTrue(pedidos.listar(con)[0]["retrasado"])


    def test_recepcion_en_puerta_dice_lo_que_falta_y_no_duplica(self):
        con = _base()
        pid = pedidos.crear(con, proveedor="GRANJA", entrega=dia(1), lineas=[{"producto": "P", "cantidad": 10}, {"producto": "Q", "cantidad": 4}])
        hoy = date.today().isoformat()
        r = pedidos.recibir(con, pedido_id=pid, proveedor="", fecha=hoy, ref="m1",
                            lineas=[{"producto": "P", "cantidad": 7}, {"producto": "Q", "cantidad": 4}])
        self.assertEqual([(f["producto"], f["diferencia"]) for f in r["faltan"]], [("P", -3)])
        self.assertEqual(pedidos.recibir(con, pedido_id=pid, proveedor="", fecha=hoy, ref="m1", lineas=[])["id"], r["id"])  # reenvío
        self.assertEqual({l["producto"]: l["recibido"] for l in pedidos.por_recibir(con)[0]["lineas"]}, {"P": 7, "Q": 4})

    def test_albaran_de_noray_con_mas_de_lo_que_llego(self):
        con = _base()
        pid = pedidos.crear(con, proveedor="GRANJA", entrega=dia(-1), lineas=[{"producto": "P", "cantidad": 10}])
        pedidos.recibir(con, pedido_id=pid, proveedor="", fecha=date.today().isoformat(), lineas=[{"producto": "P", "cantidad": 8}])
        _albaran(con, 60, "ALB-9", "P", 10, date.today().isoformat())  # Noray registra 10
        pedidos.conciliar(con)
        self.assertEqual([(d["albaran"], d["puerta"]) for d in pedidos.descuadres(con)], [(10, 8)])


if __name__ == "__main__":
    unittest.main()
