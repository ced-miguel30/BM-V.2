"""Tests A6 — LocalArchivoStorage staging / publish / compensación."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.storage.archivo_storage import (
    ArchivoValidationError,
    LocalArchivoStorage,
    PublishBatch,
)


class TestA6ArchivoStorage(unittest.TestCase):
    def test_stage_publish_and_path_traversal(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            store = LocalArchivoStorage(tmp)
            h = store.stage(b"%PDF-1.4 test", "factura.pdf")
            self.assertTrue(h.staging_path.exists())
            self.assertFalse(h.final_path.exists())
            store.publish(h)
            self.assertTrue(h.final_path.exists())
            self.assertFalse(h.staging_path.exists())
            with self.assertRaises(ArchivoValidationError):
                store.path_for_key("../etc/passwd")
            # Path en el nombre se reduce al basename (sin traversal efectivo)
            h2 = store.stage(b"x", "../../evil.pdf")
            self.assertEqual(h2.nombre_original_seguro, "evil.pdf")
            with self.assertRaises(ArchivoValidationError):
                sanitizar = __import__(
                    "app.core.storage.archivo_storage", fromlist=["sanitizar_nombre_original"]
                ).sanitizar_nombre_original
                sanitizar("..")

    def test_extension_and_size(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            store = LocalArchivoStorage(tmp, max_bytes=10)
            with self.assertRaises(ArchivoValidationError):
                store.stage(b"12345678901", "a.pdf")
            with self.assertRaises(ArchivoValidationError):
                store.stage(b"ok", "malware.exe")

    def test_rollback_after_publish(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            store = LocalArchivoStorage(tmp)
            h = store.stage(b"abc", "x.pdf")
            store.publish(h)
            batch = PublishBatch(
                published_keys=[h.storage_key],
                published_paths=[h.final_path],
            )
            done = store.rollback_published(batch)
            self.assertEqual(done, [h.storage_key])
            self.assertFalse(h.final_path.exists())

    def test_publish_batch_failure_compensates(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            store = LocalArchivoStorage(tmp)
            h1 = store.stage(b"one", "a.pdf")
            h2 = store.stage(b"two", "b.pdf")
            # Forzar destino final de h2 ya existente
            h2.final_path.write_bytes(b"preexistente")
            with self.assertRaises(Exception):
                store.publish_batch([h1, h2])
            self.assertFalse(h1.final_path.exists())


if __name__ == "__main__":
    unittest.main()
