"""La base de prueba (bm/prueba.py) se crea, se puede repetir y nunca pisa la real."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from bm import prueba


class TestPrueba(unittest.TestCase):
    def test_crea_y_repite_sin_duplicar(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            path = str(Path(d) / "prueba.sqlite")
            prueba.main(["--db", path])
            prueba.main(["--db", path])
            con = sqlite3.connect(path)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM productos").fetchone()[0], len(prueba.PRODUCTOS))
            self.assertEqual(con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0], len(prueba.USUARIOS))
            con.close()

    def test_no_toca_la_base_real(self):
        with self.assertRaises(SystemExit):
            prueba.main(["--db", "cualquier/bm.sqlite"])
