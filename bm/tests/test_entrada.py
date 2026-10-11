import tempfile
import time
import unittest
from pathlib import Path

import openpyxl

from bm import db, entrada


def _excel(path: Path, filas: list[list]) -> None:
    wb = openpyxl.Workbook()
    for f in filas:
        wb.active.append(f)
    wb.save(path)


class TestEntrada(unittest.TestCase):
    def test_importa_lo_que_se_deja_y_aparta_lo_malo(self):
        tmp = Path(tempfile.mkdtemp())
        con = db.connect(":memory:")
        con.execute("INSERT INTO ajustes VALUES('carpeta_entrada', ?)", (str(tmp),))
        _excel(tmp / "movs.xlsx", [["Nº mov.", "Fecha registro", "Tipo movimiento", "Nº producto", "Descripción", "Cantidad",
                                     "Cód. almacén", "Importe coste (real)"],
                                    [1, "01/09/2026", "Compra", "P1", "LECHE", 10, "ECONOMATO", 9.5]])
        _excel(tmp / "otra_cosa.xlsx", [["Columna", "Rara"], [1, 2]])
        (tmp / "nuevo.pdf").write_bytes(b"%PDF-")  # recién copiado: se deja para la siguiente vuelta
        hechos = {h["fichero"]: h for h in entrada.procesar(con, ahora=time.time() + 30)}
        self.assertEqual(set(hechos), set())  # nada lleva 60 s quieto todavía
        hechos = {h["fichero"]: h for h in entrada.procesar(con, ahora=time.time() + 120)}
        self.assertTrue(hechos["movs.xlsx"]["ok"])
        self.assertFalse(hechos["otra_cosa.xlsx"]["ok"])
        self.assertEqual(con.execute("SELECT COUNT(*) FROM bc_movs").fetchone()[0], 1)
        self.assertEqual(len(list((tmp / "importados").iterdir())), 1)
        self.assertEqual(len(list((tmp / "con_error").iterdir())), 2)  # el Excel raro y el PDF vacío
        con.close()


if __name__ == "__main__":
    unittest.main()
