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


if __name__ == "__main__":
    unittest.main()
