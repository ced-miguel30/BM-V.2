"""Tests de configuración de raíz compartida (instance_config)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.core.storage.demo_files import DEMO_FILE
from app.core.storage.instance_config import (
    ENV_DEMO_FILE,
    ENV_INSTANCE_ROOT,
    ENV_SHARED_ROOT,
    InstanceConfigError,
    apply_shared_root,
    bootstrap_client_shared_root,
    resolve_data_file_from_shared_root,
    save_client_config,
    validate_shared_root,
)


class TestInstanceConfig(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_inst = os.environ.get(ENV_INSTANCE_ROOT)
        self._prev_demo = os.environ.get(ENV_DEMO_FILE)
        self._prev_shared = os.environ.get(ENV_SHARED_ROOT)
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._prev_local = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = str(self.root / "LA")
        (self.root / "LA").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self._prev_inst is None:
            os.environ.pop(ENV_INSTANCE_ROOT, None)
        else:
            os.environ[ENV_INSTANCE_ROOT] = self._prev_inst
        if self._prev_demo is None:
            os.environ.pop(ENV_DEMO_FILE, None)
        else:
            os.environ[ENV_DEMO_FILE] = self._prev_demo
        if self._prev_shared is None:
            os.environ.pop(ENV_SHARED_ROOT, None)
        else:
            os.environ[ENV_SHARED_ROOT] = self._prev_shared
        if self._prev_local is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._prev_local
        self._tmp.cleanup()

    def test_validate_shared_root_creates_data_and_probes(self) -> None:
        root = validate_shared_root(self.root / "shared")
        self.assertTrue(root.is_dir())
        data_dir = root / "data"
        self.assertTrue(data_dir.is_dir())
        self.assertEqual(root, (self.root / "shared").resolve())

    def test_validate_shared_root_unusable(self) -> None:
        # Fichero donde se espera un directorio
        as_file = self.root / "not_a_dir"
        as_file.write_text("x", encoding="utf-8")
        with self.assertRaises(InstanceConfigError):
            validate_shared_root(as_file)

    def test_apply_shared_root_sets_env(self) -> None:
        shared = self.root / "inst"
        out = apply_shared_root(shared)
        self.assertEqual(out, shared.resolve())
        self.assertEqual(Path(os.environ[ENV_INSTANCE_ROOT]), shared.resolve())
        expected_data = resolve_data_file_from_shared_root(shared).resolve()
        self.assertEqual(Path(os.environ[ENV_DEMO_FILE]).resolve(), expected_data)

    def test_apply_shared_root_refuses_demo_canonical(self) -> None:
        demo_parent = DEMO_FILE.parent.resolve()
        with self.assertRaises(InstanceConfigError) as ctx:
            apply_shared_root(demo_parent)
        self.assertIn("demo canónico", str(ctx.exception).lower())

    def test_bootstrap_client_shared_root_pisa_default_local(self) -> None:
        """Config de este PC gana sobre BM-V2-local del runtime hook."""
        shared = self.root / "JoseManuel" / "2-BM-DATOS"
        shared.mkdir(parents=True)
        (shared / "data").mkdir()
        (shared / "data" / "datos_hotel.json").write_text("{}", encoding="utf-8")
        save_client_config(shared_root=shared)

        local_default = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local"
        local_default.mkdir(parents=True)
        (local_default / "data").mkdir(parents=True, exist_ok=True)
        os.environ[ENV_INSTANCE_ROOT] = str(local_default)
        os.environ[ENV_DEMO_FILE] = str(local_default / "data" / "datos_hotel.json")

        out = bootstrap_client_shared_root()
        self.assertEqual(out, shared.resolve())
        self.assertEqual(Path(os.environ[ENV_INSTANCE_ROOT]).resolve(), shared.resolve())
        self.assertEqual(
            Path(os.environ[ENV_DEMO_FILE]).resolve(),
            (shared / "data" / "datos_hotel.json").resolve(),
        )

    def test_bootstrap_respeta_instance_root_no_default(self) -> None:
        shared_cfg = self.root / "cfg-datos"
        shared_cfg.mkdir()
        (shared_cfg / "data").mkdir()
        save_client_config(shared_root=shared_cfg)

        other = self.root / "otra-raiz"
        other.mkdir()
        (other / "data").mkdir()
        os.environ[ENV_INSTANCE_ROOT] = str(other)
        os.environ.pop(ENV_SHARED_ROOT, None)

        out = bootstrap_client_shared_root()
        self.assertIsNone(out)
        self.assertEqual(Path(os.environ[ENV_INSTANCE_ROOT]).resolve(), other.resolve())


if __name__ == "__main__":
    unittest.main()
