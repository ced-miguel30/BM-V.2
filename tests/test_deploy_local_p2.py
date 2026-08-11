"""P2 — instancia completa: adjuntos, exports, backup integral, release.

Todo bajo TemporaryDirectory. No toca el demo canónico.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["BM_TEST_ISOLATION"] = "1"

from app.bootstrap import reset_container
from app.core.auth.session import AuthSession, set_test_session
from app.core.deploy import config as deploy_config
from app.core.deploy.cli import main as cli_main
from app.core.deploy.release import build_release_folder, simulate_code_rollback
from app.core.models import ArchivoDocumental
from app.core.services import archivo_documental_service as ads
from app.core.services import backup_service as bak
from app.core.services import export_service
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    PROJECT_ROOT,
    set_demo_file_override,
    sha256_demo_file,
)
from app.core.storage.instance_paths import (
    InstancePathError,
    get_documentos_root,
    get_exports_root,
    resolve_adjunto_path,
    set_documentos_root_override,
)
from app.core.storage.json_atomic import atomic_write_json
from app.data.mock_data import crear_datos_mock
from app.data.serializers import appdata_to_dict, dict_to_appdata
from tests.auth_harness import restore_harness_session


_ENV_KEYS = (
    "BM_DEPLOY_PROFILE",
    "BM_INSTANCE_ROOT",
    "BM_DEMO_FILE",
    "BM_DEPLOY_ALLOW_OPS",
    "BM_DEPLOY_CONFIG",
    "BM_DEPLOY_WRITER_HELD",
    "BM_DEPLOY_WRITER_PID",
    "BM_FLET_VIEW",
)


def _clean_env() -> dict[str, str | None]:
    prev = {k: os.environ.get(k) for k in _ENV_KEYS}
    for k in _ENV_KEYS:
        os.environ.pop(k, None)
    return prev


def _restore_env(prev: dict[str, str | None]) -> None:
    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _sesion_dir() -> AuthSession:
    return AuthSession(
        authenticated=True,
        actor_type="usuario",
        actor_id="u_dir",
        actor_label="Dirección Test",
        role="direccion",
        session_id="p2-test",
        login_at="2026-01-01T00:00:00",
    )


class DeployP2TestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._prev = _clean_env()
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)
        self.app_dir = self.root / "app copy"
        self.instance = self.root / "instance space"
        self.instance.mkdir(parents=True)
        set_demo_file_override(None)
        reset_container()
        set_test_session(_sesion_dir())
        self.addCleanup(restore_harness_session)
        self.addCleanup(reset_container)
        self.addCleanup(set_demo_file_override, None)
        self.addCleanup(set_documentos_root_override, None)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(_restore_env, self._prev)

    def _hotel(self) -> None:
        os.environ["BM_DEPLOY_PROFILE"] = "hotel"
        os.environ["BM_INSTANCE_ROOT"] = str(self.instance)
        os.environ["BM_DEPLOY_ALLOW_OPS"] = "1"

    def test_hotel_paths_outside_repo(self) -> None:
        self._hotel()
        self.assertEqual(cli_main(["prepare"]), 0)
        cfg = deploy_config.load_deploy_config(apply_config_file=False)
        self.assertTrue(str(cfg.documentos_dir).startswith(str(self.instance.resolve())))
        self.assertTrue(str(cfg.exports_dir).startswith(str(self.instance.resolve())))
        self.assertNotEqual(
            cfg.documentos_dir.resolve(),
            (PROJECT_ROOT / "data" / "documentos").resolve(),
        )
        self.assertNotEqual(
            cfg.exports_dir.resolve(),
            (PROJECT_ROOT / "exports").resolve(),
        )

    def test_adjunto_write_and_historical_read(self) -> None:
        before = sha256_demo_file(DEMO_FILE)
        self._hotel()
        cli_main(["prepare"])
        cfg = deploy_config.load_deploy_config(apply_config_file=False)
        set_demo_file_override(cfg.data_file)
        os.environ["BM_DEMO_FILE"] = str(cfg.data_file)

        # Histórico en repo (solo lectura compat)
        legacy_rel = "data/documentos/adoc_legacy/legacy.pdf"
        legacy_path = PROJECT_ROOT / legacy_rel
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_bytes(b"%PDF-legacy-p2")
        self.addCleanup(lambda: shutil.rmtree(legacy_path.parent, ignore_errors=True))

        resolved_legacy = resolve_adjunto_path(legacy_rel, for_write=False)
        self.assertEqual(resolved_legacy.read_bytes(), b"%PDF-legacy-p2")

        # Nuevo en instancia
        r = ads.registrar_archivo(b"%PDF-new-p2", "factura (1).pdf")
        self.assertTrue(r.ok, r.mensaje)
        self.assertTrue(r.archivo.ruta_relativa.startswith("data/documentos/"))
        self.assertFalse(r.archivo.ruta_relativa.startswith("C:"))
        phys = resolve_adjunto_path(r.archivo.ruta_relativa)
        self.assertTrue(str(phys).startswith(str(self.instance.resolve())))
        self.assertTrue(phys.is_file())
        # No escribió en repo documentos (salvo legacy previo)
        repo_new = PROJECT_ROOT / r.archivo.ruta_relativa
        self.assertFalse(repo_new.is_file())
        self.assertEqual(sha256_demo_file(DEMO_FILE), before)

    def test_path_traversal_rejected(self) -> None:
        self._hotel()
        cli_main(["prepare"])
        with self.assertRaises(InstancePathError):
            resolve_adjunto_path("data/documentos/../demo/datos_hotel.json")
        with self.assertRaises(InstancePathError):
            resolve_adjunto_path(r"C:\Users\Someone\secret.pdf")

    def test_export_goes_to_instance(self) -> None:
        self._hotel()
        cli_main(["prepare"])
        cfg = deploy_config.load_deploy_config(apply_config_file=False)
        set_demo_file_override(cfg.data_file)
        exports = get_exports_root(for_write=True)
        self.assertTrue(str(exports.resolve()).startswith(str(self.instance.resolve())))
        path = export_service._guardar_en_exports("actividad_test.xlsx", b"PK\x03\x04fake")
        self.assertTrue(str(path.resolve()).startswith(str(self.instance.resolve())))
        self.assertFalse(str(path.resolve()).startswith(str((PROJECT_ROOT / "exports").resolve())))

    def test_backup_includes_adjunto_excludes_exports_by_default(self) -> None:
        self._hotel()
        cli_main(["prepare"])
        cfg = deploy_config.load_deploy_config(apply_config_file=False)
        set_demo_file_override(cfg.data_file)
        ads.registrar_archivo(b"%PDF-bak", "albaran.pdf")
        # Crear export regenerable
        export_service._guardar_en_exports("ruido.xlsx", b"export-bytes")
        data = dict_to_appdata(
            json.loads(cfg.data_file.read_text(encoding="utf-8"))
        )
        # recargar desde store vía override
        from app.core.storage.demo_files import load_demo_files

        data = load_demo_files()
        result = bak.generar_backup_zip(data, kind="ops", include_disk_snapshot=True)
        names = set(result.archivos_incluidos)
        self.assertTrue(any(n.startswith("data/documentos/") for n in names))
        self.assertFalse(any(n.startswith("exports/") for n in names))
        self.assertIn("appdata.json", names)
        self.assertIn("manifest.json", names)

    def test_restore_integral_json_and_adjunto(self) -> None:
        before = sha256_demo_file(DEMO_FILE)
        self._hotel()
        cli_main(["prepare"])
        cfg = deploy_config.load_deploy_config(apply_config_file=False)
        set_demo_file_override(cfg.data_file)
        os.environ["BM_DEMO_FILE"] = str(cfg.data_file)
        r = ads.registrar_archivo(b"%PDF-restore-me", "doc.pdf")
        self.assertTrue(r.ok)
        self.assertEqual(cli_main(["backup"]), 0)
        zpath = sorted(cfg.backups_dir.glob("bm_backup_*.zip"))[-1]

        # Destruir adjunto y mutar JSON
        phys = resolve_adjunto_path(r.archivo.ruta_relativa)
        phys.unlink()
        atomic_write_json(cfg.data_file, appdata_to_dict(crear_datos_mock()))

        self.assertEqual(
            cli_main(["restore", str(zpath), "--confirm", "RESTORE"]),
            0,
        )
        self.assertTrue(resolve_adjunto_path(r.archivo.ruta_relativa).is_file())
        restored = json.loads(cfg.data_file.read_text(encoding="utf-8"))
        ids = [a["id"] for a in restored.get("archivos_documentales") or []]
        self.assertIn(r.archivo.id, ids)
        self.assertEqual(sha256_demo_file(DEMO_FILE), before)

    def test_restore_rejects_outside_instance(self) -> None:
        self._hotel()
        cli_main(["prepare"])
        cfg = deploy_config.load_deploy_config(apply_config_file=False)
        set_demo_file_override(cfg.data_file)
        cli_main(["backup"])
        zpath = sorted(cfg.backups_dir.glob("bm_backup_*.zip"))[-1]
        from app.core.services import restore_backup_service as rst

        outside = self.root / "outside" / "datos.json"
        outside.parent.mkdir(parents=True)
        outside.write_text("{}", encoding="utf-8")
        res = rst.restaurar_desde_bytes(
            zpath.read_bytes(),
            nombre_backup=zpath.name,
            destino_json=outside,
            project_root=cfg.instance_root,
        )
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "fuera_de_instancia")

    def test_second_writer_still_blocked(self) -> None:
        from app.core.deploy.writer_lock import (
            WriterLockError,
            acquire_writer_lock,
            lock_path_for,
        )
        from unittest import mock

        self._hotel()
        cli_main(["prepare"])
        cfg = deploy_config.load_deploy_config(apply_config_file=False)
        acquire_writer_lock(cfg, role="flet_launcher")
        try:
            lock = lock_path_for(cfg.data_file)
            payload = json.loads(lock.read_text(encoding="utf-8"))
            payload["pid"] = os.getpid() + 424242
            payload["role"] = "streamlit"
            lock.write_text(json.dumps(payload), encoding="utf-8")
            with mock.patch(
                "app.core.deploy.writer_lock._pid_alive", return_value=True
            ):
                with self.assertRaises(WriterLockError):
                    acquire_writer_lock(cfg, role="streamlit")
        finally:
            lock_path_for(cfg.data_file).unlink(missing_ok=True)

    def test_release_build_and_code_rollback_keeps_instance(self) -> None:
        self._hotel()
        cli_main(["prepare"])
        cfg = deploy_config.load_deploy_config(apply_config_file=False)
        set_demo_file_override(cfg.data_file)
        ads.registrar_archivo(b"%PDF-keep", "keep.pdf")
        marker = cfg.data_file
        marker_bytes = marker.read_bytes()
        adj_rel = [
            a.ruta_relativa
            for a in dict_to_appdata(
                json.loads(cfg.data_file.read_text(encoding="utf-8"))
            ).archivos_documentales
        ][0]

        release_a = self.root / "release A"
        release_b = self.root / "release B"
        build_release_folder(release_a, overwrite=True)
        build_release_folder(release_b, overwrite=True)
        self.assertTrue((release_a / "RELEASE_MANIFEST.json").is_file())
        self.assertFalse((release_a / ".venv").exists())
        current = self.root / "current app"
        shutil.copytree(release_b, current)
        # rollback código B → A
        simulate_code_rollback(release_a, release_b, active_link=current)
        self.assertTrue((current / "app").is_dir())
        # datos intactos
        self.assertEqual(marker.read_bytes(), marker_bytes)
        self.assertTrue(resolve_adjunto_path(adj_rel).is_file())

    def test_clean_machine_simulation_with_spaces(self) -> None:
        before = sha256_demo_file(DEMO_FILE)
        self._hotel()
        other = self.root / "wd space"
        other.mkdir()
        prev = Path.cwd()
        try:
            os.chdir(other)
            self.assertEqual(cli_main(["prepare"]), 0)
            cfg = deploy_config.load_deploy_config(apply_config_file=False)
            set_demo_file_override(cfg.data_file)
            ads.registrar_archivo(b"%PDF-sim", "sim.pdf")
            export_service._guardar_en_exports("sim.xlsx", b"xlsx")
            self.assertEqual(cli_main(["backup"]), 0)
            self.assertEqual(cli_main(["diagnose"]), 0)
            # launcher build
            from app.presentation.flet.main_launcher import build_app_handler
            import flet as ft

            handler = build_app_handler()
            app = ft.run(handler, export_asgi_app=True)
            self.assertIsNotNone(app)
            import app.main as sm

            self.assertTrue(hasattr(sm, "main"))
            zpath = sorted(cfg.backups_dir.glob("bm_backup_*.zip"))[-1]
            self.assertEqual(cli_main(["verify-backup", str(zpath)]), 0)
            # mutar y restore
            atomic_write_json(cfg.data_file, appdata_to_dict(crear_datos_mock()))
            self.assertEqual(
                cli_main(["restore", str(zpath), "--confirm", "RESTORE"]),
                0,
            )
        finally:
            os.chdir(prev)
        self.assertEqual(sha256_demo_file(DEMO_FILE), before)
        self.assertEqual(before, DEMO_CONTENT_SHA256_CANONICO)

    def test_migrate_adjuntos_preview_no_delete(self) -> None:
        self._hotel()
        cli_main(["prepare"])
        # crear legacy
        legacy = PROJECT_ROOT / "data" / "documentos" / "mig_p2" / "x.pdf"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_bytes(b"mig")
        self.addCleanup(lambda: shutil.rmtree(legacy.parent, ignore_errors=True))
        self.assertEqual(cli_main(["migrate-adjuntos"]), 0)
        dest = self.instance / "data" / "documentos" / "mig_p2" / "x.pdf"
        self.assertFalse(dest.is_file())  # preview
        self.assertEqual(cli_main(["migrate-adjuntos", "--apply"]), 0)
        self.assertTrue(dest.is_file())
        self.assertTrue(legacy.is_file())  # origen conservado


if __name__ == "__main__":
    unittest.main()
