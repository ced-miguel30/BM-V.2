"""Dos carpetas hotel — BM-CODIGO / BM-DATOS y runtime hook.

Ejecutar:

    py -m unittest tests.test_hotel_dos_carpetas -v
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.deploy.folder_markers import (
    BM_CODIGO_MARKER_NAME,
    BM_DATOS_MARKER_NAME,
    BM_CODIGO_MARKER_TEXT,
    BM_DATOS_MARKER_TEXT,
)


def _load_runtime_hook():
    """Carga packaging/runtime_hook_bm.py sin chocar con el paquete pip ``packaging``."""
    path = ROOT / "packaging" / "runtime_hook_bm.py"
    spec = importlib.util.spec_from_file_location("bm_runtime_hook_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestFolderMarkers(unittest.TestCase):
    def test_nombres_y_textos(self) -> None:
        self.assertEqual(BM_CODIGO_MARKER_NAME, "BM-CODIGO.txt")
        self.assertEqual(BM_DATOS_MARKER_NAME, "BM-DATOS.txt")
        self.assertIn("BM-CODIGO", BM_CODIGO_MARKER_TEXT)
        self.assertIn("BM-DATOS", BM_DATOS_MARKER_TEXT)
        self.assertIn("BM-V2-local", BM_DATOS_MARKER_TEXT)


class TestRuntimeHookDosCarpetas(unittest.TestCase):
    def test_sustituir_codigo_conserva_bm_instance_root(self) -> None:
        """El default de datos no depende de la carpeta del exe."""
        hook = _load_runtime_hook()

        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "LocalAppData"
            local.mkdir()
            code1 = Path(tmp) / "Apps" / "BM-V2-v1"
            code2 = Path(tmp) / "Apps" / "BM-V2-v2"
            code1.mkdir(parents=True)
            code2.mkdir(parents=True)
            exe1 = code1 / "BM-Launcher.exe"
            exe2 = code2 / "BM-Launcher.exe"
            exe1.write_bytes(b"mz")
            exe2.write_bytes(b"mz")

            with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local)}, clear=False):
                for k in ("BM_INSTANCE_ROOT", "BM_DEMO_FILE"):
                    os.environ.pop(k, None)

                with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(
                    sys, "executable", str(exe1)
                ):
                    hook._ensure_paths()
                root1 = Path(os.environ["BM_INSTANCE_ROOT"])
                demo1 = Path(os.environ["BM_DEMO_FILE"])

                self.assertEqual(root1, local / "BM-V2-local")
                self.assertEqual(demo1, root1 / "data" / "datos_hotel.json")
                self.assertTrue((root1 / "data").is_dir())
                self.assertTrue((root1 / "backups").is_dir())
                self.assertTrue((root1 / BM_DATOS_MARKER_NAME).is_file())
                self.assertTrue((code1 / BM_CODIGO_MARKER_NAME).is_file())

                for k in ("BM_INSTANCE_ROOT", "BM_DEMO_FILE", "BM_DEPLOY_PROFILE"):
                    os.environ.pop(k, None)
                with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(
                    sys, "executable", str(exe2)
                ):
                    hook._ensure_paths()
                root2 = Path(os.environ["BM_INSTANCE_ROOT"])
                self.assertEqual(root1, root2)
                self.assertTrue((code2 / BM_CODIGO_MARKER_NAME).is_file())
                self.assertTrue((root2 / BM_DATOS_MARKER_NAME).is_file())

    def test_bm_instance_root_explicito_se_respeta(self) -> None:
        hook = _load_runtime_hook()

        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "LA"
            custom = Path(tmp) / "SharedDatos"
            local.mkdir()
            custom.mkdir()
            code = Path(tmp) / "code"
            code.mkdir()
            exe = code / "BM-Launcher.exe"
            exe.write_bytes(b"mz")

            with mock.patch.dict(
                os.environ,
                {
                    "LOCALAPPDATA": str(local),
                    "BM_INSTANCE_ROOT": str(custom),
                },
                clear=False,
            ):
                os.environ.pop("BM_DEMO_FILE", None)
                with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(
                    sys, "executable", str(exe)
                ):
                    hook._ensure_paths()
                self.assertEqual(Path(os.environ["BM_INSTANCE_ROOT"]), custom)
                self.assertTrue((custom / BM_DATOS_MARKER_NAME).is_file())


if __name__ == "__main__":
    unittest.main()
