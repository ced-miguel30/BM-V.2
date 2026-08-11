"""P1 despliegue local — paths, perfil hotel, escritor único, backup ops.

Todo el I/O usa TemporaryDirectory. No toca el demo canónico.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["BM_TEST_ISOLATION"] = "1"

from app.core.deploy import config as deploy_config
from app.core.deploy import ops
from app.core.deploy.cli import main as cli_main
from app.core.deploy.writer_lock import (
    WriterLockError,
    acquire_writer_lock,
    lock_path_for,
    read_lock,
    release_writer_lock,
)
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    get_demo_file,
    set_demo_file_override,
    sha256_demo_file,
)
from app.core.storage.json_atomic import atomic_write_json
from app.data.serializers import appdata_to_dict
from app.data.mock_data import crear_datos_mock


def _clean_env(keys: tuple[str, ...]) -> dict[str, str | None]:
    prev = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    return prev


def _restore_env(prev: dict[str, str | None]) -> None:
    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


_ENV_KEYS = (
    "BM_DEPLOY_PROFILE",
    "BM_INSTANCE_ROOT",
    "BM_DEMO_FILE",
    "BM_DEPLOY_ALLOW_OPS",
    "BM_DEPLOY_CONFIG",
    "BM_DEPLOY_WRITER_HELD",
    "BM_DEPLOY_WRITER_PID",
    "BM_DEPLOY_WRITER_ROLE",
    "BM_FLET_VIEW",
)


class DeployP1TestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._prev = _clean_env(_ENV_KEYS)
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)
        # Ruta con espacios
        self.instance = self.root / "hotel instance"
        self.instance.mkdir(parents=True)
        set_demo_file_override(None)
        self.addCleanup(set_demo_file_override, None)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(_restore_env, self._prev)
        self.addCleanup(lambda: os.environ.pop("BM_DEPLOY_ALLOW_OPS", None))

    def _hotel_env(self) -> Path:
        os.environ["BM_DEPLOY_PROFILE"] = "hotel"
        os.environ["BM_INSTANCE_ROOT"] = str(self.instance)
        os.environ["BM_DEPLOY_ALLOW_OPS"] = "1"
        data = self.instance / "data" / "datos_hotel.json"
        return data

    def test_hotel_rejects_missing_paths(self) -> None:
        os.environ["BM_DEPLOY_PROFILE"] = "hotel"
        with self.assertRaises(deploy_config.DeployConfigError):
            deploy_config.load_deploy_config(apply_config_file=False)

    def test_hotel_rejects_demo_fallback_and_demo_path(self) -> None:
        os.environ["BM_DEPLOY_PROFILE"] = "hotel"
        os.environ["BM_DEMO_FILE"] = str(DEMO_FILE)
        with self.assertRaises(deploy_config.DeployConfigError):
            deploy_config.load_deploy_config(apply_config_file=False)

    def test_resolve_independent_of_cwd_and_spaces(self) -> None:
        data = self._hotel_env()
        other = self.root / "other cwd"
        other.mkdir()
        prev = Path.cwd()
        try:
            os.chdir(other)
            cfg = deploy_config.load_deploy_config(apply_config_file=False)
            self.assertEqual(cfg.data_file, data.resolve())
            self.assertIn(" ", str(cfg.instance_root))
            self.assertFalse(cfg.data_file_is_demo())
        finally:
            os.chdir(prev)

    def test_prepare_seeds_without_touching_demo(self) -> None:
        before = sha256_demo_file(DEMO_FILE)
        data = self._hotel_env()
        self.assertEqual(
            cli_main(["prepare"]),
            0,
        )
        self.assertTrue(data.is_file())
        self.assertEqual(sha256_demo_file(DEMO_FILE), before)
        self.assertEqual(before, DEMO_CONTENT_SHA256_CANONICO)

    def test_writer_lock_blocks_second_role(self) -> None:
        self._hotel_env()
        cli_main(["prepare"])
        cfg = deploy_config.load_deploy_config(apply_config_file=False)
        acquire_writer_lock(cfg, role="flet_launcher")
        try:
            with mock.patch(
                "app.core.deploy.writer_lock._pid_alive", return_value=True
            ):
                # Simular otro PID vivo en el candado
                lock = lock_path_for(cfg.data_file)
                payload = json.loads(lock.read_text(encoding="utf-8"))
                payload["pid"] = os.getpid() + 99999
                payload["role"] = "streamlit"
                lock.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(WriterLockError):
                    acquire_writer_lock(cfg, role="streamlit")
        finally:
            lock_path_for(cfg.data_file).unlink(missing_ok=True)

    def test_backup_verify_restore_and_corrupt_rejected(self) -> None:
        before = sha256_demo_file(DEMO_FILE)
        data = self._hotel_env()
        self.assertEqual(cli_main(["prepare"]), 0)
        # Mutar productivo de forma observable
        data_obj = crear_datos_mock()
        if data_obj.productos:
            data_obj.productos[0].nombre = "Producto P1 Deploy"
        atomic_write_json(data, appdata_to_dict(data_obj))

        self.assertEqual(cli_main(["backup"]), 0)
        cfg = deploy_config.load_deploy_config(apply_config_file=False)
        zips = sorted(cfg.backups_dir.glob("bm_backup_*.zip"))
        self.assertTrue(zips)
        zpath = zips[-1]
        self.assertEqual(cli_main(["verify-backup", str(zpath)]), 0)

        # Corrupto
        bad = cfg.backups_dir / "bm_backup_corrupt.zip"
        bad.write_bytes(zpath.read_bytes()[:-20] + b"XXXXCORRUPTXXXX")
        self.assertEqual(cli_main(["verify-backup", str(bad)]), 2)

        # Cambiar datos y restaurar
        atomic_write_json(data, appdata_to_dict(crear_datos_mock()))
        self.assertEqual(
            cli_main(["restore", str(zpath), "--confirm", "RESTORE"]),
            0,
        )
        restored = json.loads(data.read_text(encoding="utf-8"))
        nombres = [p.get("nombre") for p in restored.get("productos") or []]
        self.assertIn("Producto P1 Deploy", nombres)
        # Preventivo bajo data/backups/pre_restore junto al JSON
        pre_dir = data.parent / "backups" / "pre_restore"
        self.assertTrue(pre_dir.is_dir())
        self.assertEqual(sha256_demo_file(DEMO_FILE), before)

    def test_restore_requires_confirm(self) -> None:
        self._hotel_env()
        cli_main(["prepare"])
        cli_main(["backup"])
        cfg = deploy_config.load_deploy_config(apply_config_file=False)
        zpath = sorted(cfg.backups_dir.glob("bm_backup_*.zip"))[-1]
        self.assertEqual(cli_main(["restore", str(zpath), "--confirm", "no"]), 2)

    def test_cli_diagnose_no_secrets_or_economy(self) -> None:
        self._hotel_env()
        cli_main(["prepare"])
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli_main(["diagnose"])
        self.assertEqual(code, 0)
        out = buf.getvalue().lower()
        for banned in ("password", "hash", "coste", "precio", "secret"):
            self.assertNotIn(banned, out)
        self.assertIn("data_file=", out)
        self.assertIn("data_is_demo=false", out)
        # No volcar contenido JSON
        self.assertNotIn("productos", out)

    def test_get_demo_file_follows_bm_demo_file(self) -> None:
        data = self._hotel_env()
        cli_main(["prepare"])
        cfg = deploy_config.load_deploy_config(apply_config_file=False)
        self.assertEqual(get_demo_file(), cfg.data_file)
        self.assertEqual(get_demo_file(), data.resolve())

    def test_missing_folder_errors(self) -> None:
        os.environ["BM_DEPLOY_PROFILE"] = "hotel"
        ghost_root = self.root / "missing root"
        os.environ["BM_INSTANCE_ROOT"] = str(ghost_root)
        ghost = ghost_root / "data" / "datos_hotel.json"
        os.environ["BM_DEMO_FILE"] = str(ghost)
        cfg = deploy_config.load_deploy_config(apply_config_file=False)
        with self.assertRaises(deploy_config.DeployConfigError):
            deploy_config.assert_hotel_data_ready(cfg, require_exists=True)

    def test_ops_backup_denied_without_flag(self) -> None:
        data = self._hotel_env()
        os.environ.pop("BM_DEPLOY_ALLOW_OPS", None)
        cli_main(["prepare"])
        # prepare doesn't need ops; backup via ops module should fail
        cfg = deploy_config.load_deploy_config(apply_config_file=False)
        cfg = deploy_config.DeployConfig(
            profile=cfg.profile,
            project_root=cfg.project_root,
            instance_root=cfg.instance_root,
            data_file=cfg.data_file,
            backups_dir=cfg.backups_dir,
            logs_dir=cfg.logs_dir,
            exports_dir=cfg.exports_dir,
            documentos_dir=cfg.documentos_dir,
            demo_file=cfg.demo_file,
            allow_ops=False,
            flet_view=cfg.flet_view,
            skip_weekly_export=cfg.skip_weekly_export,
        )
        with self.assertRaises(deploy_config.DeployConfigError):
            ops.create_ops_backup(cfg)
        self.assertTrue(data.is_file())

    def test_no_hardcoded_hotel_paths_in_module(self) -> None:
        deploy_root = ROOT / "app" / "core" / "deploy"
        for path in deploy_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("C:\\Users", text)
            self.assertNotIn("/Users/", text)

    def test_subprocess_cli_from_other_cwd(self) -> None:
        self._hotel_env()
        other = self.root / "wd space"
        other.mkdir()
        env = os.environ.copy()
        env["BM_TEST_ISOLATION"] = "1"
        env["BM_DEPLOY_PROFILE"] = "hotel"
        env["BM_INSTANCE_ROOT"] = str(self.instance)
        env["BM_DEPLOY_ALLOW_OPS"] = "1"
        env["PYTHONPATH"] = str(ROOT)
        env.pop("BM_DEPLOY_CONFIG", None)
        r = subprocess.run(
            [sys.executable, "-m", "app.core.deploy.cli", "prepare"],
            cwd=str(other),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.instance / "data" / "datos_hotel.json").is_file())


class DeployP1ArchitectureGuard(unittest.TestCase):
    def test_deploy_scripts_exist(self) -> None:
        win = ROOT / "deploy" / "windows"
        for name in (
            "prepare_env.cmd",
            "start_launcher.cmd",
            "start_streamlit.cmd",
            "backup.cmd",
            "verify_backup.cmd",
            "restore.cmd",
            "diagnose.cmd",
            "release_writer.cmd",
        ):
            self.assertTrue((win / name).is_file(), name)
        self.assertTrue((ROOT / "deploy" / "config.example.env").is_file())


if __name__ == "__main__":
    unittest.main()
