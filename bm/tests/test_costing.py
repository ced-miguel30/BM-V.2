import unittest

from bm.costing import valorar_producto


def compra(n, fecha, q, coste_total):
    return {"n_mov": n, "fecha": fecha, "tipo": "Compra", "cantidad": q, "coste_unit": 0, "coste_total": coste_total}


def ajuste(n, fecha, q):
    return {"n_mov": n, "fecha": fecha, "tipo": "Ajuste negativo", "cantidad": q, "coste_unit": 0, "coste_total": 0}


class TestFifoAnclado(unittest.TestCase):
    def test_fifo_consume_lote_antiguo_primero(self):
        movs = [compra(1, "2026-07-01", 10, 10.0), compra(2, "2026-07-02", 10, 20.0)]
        [(_, coste, estado, partes)] = valorar_producto(movs, [{"id": 1, "fecha": "2026-07-03", "cantidad": 12}])
        self.assertEqual((coste, estado), (14.0, "fifo"))  # 10 x 1 + 2 x 2
        self.assertEqual([p[0] for p in partes], [1, 2])

    def test_inventario_bc_manda_y_deja_lotes_nuevos(self):
        # BC cuenta 5 uds a fin de mes: los lotes viejos se gastaron fuera de BM (habitaciones...).
        movs = [compra(1, "2026-07-01", 10, 10.0), compra(2, "2026-07-20", 10, 30.0), ajuste(3, "2026-07-31", -15)]
        [(_, coste, estado, partes)] = valorar_producto(movs, [{"id": 1, "fecha": "2026-08-01", "cantidad": 2}])
        self.assertEqual((coste, estado, partes[0][0]), (6.0, "fifo", 2))  # sale del lote de 3 EUR

    def test_albaran_sin_facturar_usa_ultimo_precio(self):
        movs = [compra(1, "2026-07-01", 1, 2.0), compra(2, "2026-07-02", 5, 0)]
        consumos = [{"id": 1, "fecha": "2026-07-03", "cantidad": 1}, {"id": 2, "fecha": "2026-07-03", "cantidad": 2}]
        r = valorar_producto(movs, consumos)
        self.assertEqual([(x[1], x[2]) for x in r], [(2.0, "fifo"), (4.0, "provisional")])

    def test_sin_stock_y_sin_precio(self):
        movs = [compra(1, "2026-07-01", 1, 3.0)]
        r = valorar_producto(movs, [{"id": 1, "fecha": "2026-07-02", "cantidad": 2}])
        self.assertEqual((r[0][1], r[0][2]), (6.0, "sin_stock"))
        r = valorar_producto([], [{"id": 1, "fecha": "2026-07-02", "cantidad": 1}])
        self.assertEqual((r[0][1], r[0][2]), (None, "sin_precio"))

    def test_stock_inicial_bc_antes_del_primer_consumo(self):
        # 100 compradas en 2025, BC cuenta 4 en junio: BM empieza con 4, no con 100.
        movs = [compra(1, "2025-01-01", 100, 100.0), ajuste(2, "2026-06-30", -96), compra(3, "2026-07-01", 10, 20.0)]
        r = valorar_producto(movs, [{"id": 1, "fecha": "2026-07-05", "cantidad": 6}])
        self.assertEqual(r[0][1], 8.0)  # 4 x 1 + 2 x 2


if __name__ == "__main__":
    unittest.main()
