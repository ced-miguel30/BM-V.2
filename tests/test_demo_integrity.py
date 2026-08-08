"""Integridad portátil del demo (LF/CRLF) — sin escribir el demo real.

    python -m unittest tests.test_demo_integrity -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["BM_TEST_ISOLATION"] = "1"

from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    normalize_demo_newlines,
    sha256_demo_bytes,
    sha256_demo_file,
)


class TestDemoIntegrityPortable(unittest.TestCase):
    def test_01_demo_canonico_normalizado(self) -> None:
        self.assertTrue(DEMO_FILE.exists())
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def test_02_lf_y_crlf_mismo_hash(self) -> None:
        lf = normalize_demo_newlines(DEMO_FILE.read_bytes())
        crlf = lf.replace(b"\n", b"\r\n")
        self.assertNotEqual(lf, crlf)
        self.assertEqual(sha256_demo_bytes(lf), DEMO_CONTENT_SHA256_CANONICO)
        self.assertEqual(sha256_demo_bytes(crlf), DEMO_CONTENT_SHA256_CANONICO)

    def test_03_cr_aislado_y_crlf(self) -> None:
        lf = b'{"a":1}\n{"b":2}\n'
        mixed = b'{"a":1}\r\n{"b":2}\r'
        self.assertEqual(sha256_demo_bytes(lf), sha256_demo_bytes(mixed))

    def test_04_cambio_semantico_cambia_hash(self) -> None:
        base = normalize_demo_newlines(DEMO_FILE.read_bytes())
        altered = base + b"\n"
        self.assertNotEqual(sha256_demo_bytes(base), sha256_demo_bytes(altered))

    def test_05_modificar_usuario_cambia_hash(self) -> None:
        base = normalize_demo_newlines(DEMO_FILE.read_bytes())
        # Cambio mínimo de texto en el rol/nombre sin reserializar JSON completo
        if b'"Admin"' not in base:
            self.skipTest("fixture sin Admin literal")
        altered = base.replace(b'"Admin"', b'"AdminX"', 1)
        self.assertNotEqual(sha256_demo_bytes(base), sha256_demo_bytes(altered))

    def test_06_solo_newlines_no_cambia_hash(self) -> None:
        lf = normalize_demo_newlines(DEMO_FILE.read_bytes())
        crlf = lf.replace(b"\n", b"\r\n")
        cr_only = lf.replace(b"\n", b"\r")
        self.assertEqual(sha256_demo_bytes(lf), sha256_demo_bytes(crlf))
        self.assertEqual(sha256_demo_bytes(lf), sha256_demo_bytes(cr_only))

    def test_07_no_reserializa_ni_ignora_espacios(self) -> None:
        a = b'{"x": 1}\n'
        b = b'{"x":1}\n'
        self.assertNotEqual(sha256_demo_bytes(a), sha256_demo_bytes(b))

    def test_08_temp_no_escribe_demo_real(self) -> None:
        before = DEMO_FILE.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "datos_hotel.json"
            p.write_bytes(b'{"meta":{"origen":"tmp"}}\n')
            h = sha256_demo_file(p)
            self.assertEqual(len(h), 64)
            self.assertNotEqual(h, DEMO_CONTENT_SHA256_CANONICO)
        self.assertEqual(DEMO_FILE.read_bytes(), before)

    def test_09_fixture_semantico_canonico(self) -> None:
        import json

        data = json.loads(DEMO_FILE.read_bytes().decode("utf-8"))
        self.assertEqual(len(data.get("usuarios") or []), 1)
        self.assertEqual((data["usuarios"][0].get("rol")), "Admin")
        self.assertEqual(len(data.get("actividades") or []), 18)
        self.assertEqual((data.get("meta") or {}).get("usuario_actual_id"), "u01")
        self.assertNotIn("conciliaciones_documento", data)
        self.assertEqual(len(data.get("productos") or []), 2)
        self.assertEqual(len(data.get("lotes") or []), 2)
        self.assertEqual(len(data.get("movimientos") or []), 2)
        self.assertEqual(len(data.get("recetas") or []), 2)
        self.assertEqual(len(data.get("documentos") or []), 0)
        self.assertEqual(len(data.get("proveedores") or []), 0)


if __name__ == "__main__":
    unittest.main()
