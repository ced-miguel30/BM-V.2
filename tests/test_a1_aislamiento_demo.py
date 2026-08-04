"""Fase A1 — cierre: red de seguridad BM_TEST_ISOLATION + aislamiento local."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.core.models import AppData
from app.core.storage import demo_files as demo_files_mod
from app.data import serializers as serializers_mod
from tests.demo_isolation import (
    isolation_env_active,
    protected_demo_path,
    restore_test_isolation_env,
)


class TestA1RedSeguridadDemo(unittest.TestCase):
    """Pruebas que activan/restauran BM_TEST_ISOLATION de forma local."""

    def setUp(self) -> None:
        self._prev_env = os.environ.get("BM_TEST_ISOLATION")
        os.environ["BM_TEST_ISOLATION"] = "1"
        demo_files_mod.set_demo_file_override(None)

    def tearDown(self) -> None:
        demo_files_mod.set_demo_file_override(None)
        restore_test_isolation_env(self._prev_env)

    def test_bloquea_ruta_canonica_absoluta(self) -> None:
        with self.assertRaises(RuntimeError):
            serializers_mod.save_json(
                protected_demo_path(), {"meta": {"probe": True}}
            )

    def test_bloquea_ruta_relativa(self) -> None:
        rel = Path("data") / "demo" / "datos_hotel.json"
        self.assertEqual(rel.resolve(), protected_demo_path())
        with self.assertRaises(RuntimeError):
            serializers_mod.save_json(rel, {"meta": {"probe": True}})

    def test_bloquea_ruta_con_segmentos_dotdot(self) -> None:
        # data/demo/../demo/datos_hotel.json → misma ruta resuelta
        tricky = Path("data") / "demo" / ".." / "demo" / "datos_hotel.json"
        self.assertEqual(tricky.resolve(), protected_demo_path())
        with self.assertRaises(RuntimeError):
            serializers_mod.save_json(tricky, {"meta": {"probe": True}})

    def test_bloquea_via_binding_demo_files_save_json(self) -> None:
        with self.assertRaises(RuntimeError):
            demo_files_mod.save_json(
                protected_demo_path(), {"meta": {"via_demo_files": True}}
            )

    def test_bloquea_save_demo_files_sin_override(self) -> None:
        with self.assertRaises(RuntimeError):
            demo_files_mod.save_demo_files(AppData())

    def test_bloquea_delete_demo_files_sin_override(self) -> None:
        with self.assertRaises(RuntimeError):
            demo_files_mod.delete_demo_files()

    def test_permite_escritura_y_borrado_en_temporarydirectory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "datos_hotel.json"
            serializers_mod.save_json(dest, {"ok": True})
            self.assertTrue(dest.is_file())
            self.assertNotEqual(dest.resolve(), protected_demo_path())
            dest.unlink()
            self.assertFalse(dest.exists())

    def test_override_temporal_save_load_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "datos_hotel.json"
            demo_files_mod.set_demo_file_override(dest)
            try:
                written = demo_files_mod.save_demo_files(AppData())
                self.assertEqual(written.resolve(), dest.resolve())
                loaded = demo_files_mod.load_demo_files()
                self.assertIsInstance(loaded, AppData)
                self.assertTrue(demo_files_mod.delete_demo_files())
                self.assertFalse(dest.exists())
            finally:
                demo_files_mod.set_demo_file_override(None)

    def test_sin_flag_no_bloquea_por_env_pero_no_escribimos_demo(self) -> None:
        """Sin BM_TEST_ISOLATION el check de env no dispara; no se escribe el demo."""
        os.environ.pop("BM_TEST_ISOLATION", None)
        # Solo verificamos que el helper de rechazo no alza sin flag;
        # no invocamos escritura real al demo.
        serializers_mod._reject_protected_demo_write(protected_demo_path())
        os.environ["BM_TEST_ISOLATION"] = "1"

    def test_isolation_env_context_restaura(self) -> None:
        os.environ.pop("BM_TEST_ISOLATION", None)
        with isolation_env_active():
            self.assertEqual(os.environ.get("BM_TEST_ISOLATION"), "1")
            with self.assertRaises(RuntimeError):
                serializers_mod.save_json(
                    protected_demo_path(), {"meta": {"ctx": True}}
                )
        self.assertNotEqual(os.environ.get("BM_TEST_ISOLATION"), "1")
        # Dejar activo para tearDown coherente con setUp
        os.environ["BM_TEST_ISOLATION"] = "1"

    def test_funciones_persistencia_no_neutralizadas(self) -> None:
        """persist_data / save_demo_files siguen siendo funciones reales (no mocks)."""
        from app.core.storage import session_store

        self.assertTrue(callable(session_store.persist_data))
        self.assertTrue(callable(demo_files_mod.save_demo_files))
        self.assertTrue(callable(serializers_mod.save_json))
        # Un save a temporal debe funcionar (no están "neutralizado")
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "x.json"
            serializers_mod.save_json(dest, {"alive": True})
            self.assertEqual(
                serializers_mod.load_json(dest).get("alive"), True
            )


class TestA1RutaProtegidaMeta(unittest.TestCase):
    def test_ruta_protegida_es_absoluta_y_estable(self) -> None:
        p = protected_demo_path()
        self.assertTrue(p.is_absolute())
        self.assertEqual(p.name, "datos_hotel.json")
        self.assertEqual(p.parent.name, "demo")


if __name__ == "__main__":
    unittest.main()
