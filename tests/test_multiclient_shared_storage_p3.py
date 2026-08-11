"""Simulación multi-cliente (3 PCs) sobre una carpeta compartida temporal."""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import socket
import tempfile
import time
import unittest
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.models import AppData
from app.core.storage import demo_files as demo_files_mod
from app.core.storage.instance_config import DATA_FILE_NAME
from app.core.storage.shared_coordinator import (
    SharedLockTimeout,
    SharedPathUnavailable,
    SharedRevisionConflict,
    acquire_shared_lock,
    coordinated_save,
    lock_path_for,
    read_disk_revision,
    release_shared_lock,
)
from app.data.serializers import dict_to_appdata, load_json
from tests.auth_harness import HARNESS_SESSION
from tests.browser.fixtures_minimos import write_browser_fixture
from tests.demo_isolation import restore_test_isolation_env


def _iso_future(seconds: float = 120.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _iso_past(seconds: float = 120.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _setup_worker(json_path: str) -> None:
    """Configura env + composition Flet en un worker de proceso."""
    os.environ["BM_TEST_ISOLATION"] = "1"
    os.environ["BM_DEMO_FILE"] = json_path
    demo_files_mod.set_demo_file_override(None)
    from app.bootstrap import configure_for_flet, reset_container
    from app.core.auth.session import set_test_session

    reset_container()
    configure_for_flet(data_path=json_path)
    set_test_session(HARNESS_SESSION)


def _worker_create_product(json_path: str, nombre: str, codigo: str) -> dict:
    _setup_worker(json_path)
    from app.core.services.stock_service import crear_producto
    from app.core.storage.session_store import get_data

    result = crear_producto(
        nombre, "Ud", 1.0, codigo=codigo, tipo_articulo="consumible"
    )
    data = get_data()
    return {
        "ok": bool(result.ok),
        "mensaje": result.mensaje,
        "revision": int(data.revision),
        "nombres": [p.nombre for p in data.productos],
        "codigos": [getattr(p, "codigo", None) for p in data.productos],
    }


def _worker_reload_and_list(json_path: str) -> dict:
    _setup_worker(json_path)
    from app.bootstrap import get_container

    data = get_container().app_data_store.reload_from_disk()
    return {
        "revision": int(data.revision),
        "nombres": [p.nombre for p in data.productos],
        "codigos": [getattr(p, "codigo", None) for p in data.productos],
    }


def _worker_edit_product(
    json_path: str, producto_id: str, nuevo_nombre: str
) -> dict:
    """Edita un producto; reintenta ante SharedRevisionConflict."""
    _setup_worker(json_path)
    from app.bootstrap import get_container
    from app.core.services.stock_service import editar_producto

    last_err = ""
    for _ in range(40):
        try:
            get_container().app_data_store.reload_from_disk()
            r = editar_producto(producto_id, nombre=nuevo_nombre)
            if not r.ok:
                return {"status": "fail", "mensaje": r.mensaje}
            rev = int(get_container().app_data_store.get().revision)
            return {"status": "ok", "revision": rev, "nombre": nuevo_nombre}
        except SharedRevisionConflict as exc:
            last_err = str(exc)
            time.sleep(0.05)
    return {"status": "conflict_exhausted", "mensaje": last_err}


def _worker_same_revision_persist(json_path: str, tag: str) -> dict:
    os.environ["BM_TEST_ISOLATION"] = "1"
    os.environ["BM_DEMO_FILE"] = json_path
    demo_files_mod.set_demo_file_override(None)
    try:
        data = dict_to_appdata(load_json(Path(json_path)))
        expected = int(data.revision)
        time.sleep(0.08)
        data.usuario_actual_id = f"{tag}-{os.getpid()}"
        coordinated_save(
            data,
            operation=f"same-rev-{tag}",
            expected_revision=expected,
            timeout=20,
        )
        return {"status": "ok", "revision": int(data.revision), "tag": tag}
    except SharedRevisionConflict as exc:
        return {"status": "conflict", "mensaje": str(exc), "tag": tag}
    except Exception as exc:  # noqa: BLE001
        return {"status": "err", "mensaje": repr(exc), "tag": tag}


def _worker_hold_lock(json_path: str, hold_s: float, ready: mp.Event) -> None:
    os.environ["BM_TEST_ISOLATION"] = "1"
    os.environ["BM_DEMO_FILE"] = json_path
    demo_files_mod.set_demo_file_override(None)
    info = acquire_shared_lock(
        json_path, operation="hold", timeout=5, lease_seconds=30
    )
    ready.set()
    try:
        time.sleep(hold_s)
    finally:
        release_shared_lock(json_path, info=info)


def _write_fake_lock(
    data_file: Path,
    *,
    host: str,
    pid: int,
    lease_until: str,
    operation: str = "fake",
) -> Path:
    lock = lock_path_for(data_file)
    payload = {
        "user": "test",
        "host": host,
        "pid": pid,
        "operation": operation,
        "acquired_at": _iso_past(10),
        "data_file": str(data_file),
        "lock_path": str(lock),
        "lease_until": lease_until,
    }
    lock.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return lock


class TestMulticlientSharedStorageP3(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_iso = os.environ.get("BM_TEST_ISOLATION")
        self._prev_demo = os.environ.get("BM_DEMO_FILE")
        os.environ["BM_TEST_ISOLATION"] = "1"
        demo_files_mod.set_demo_file_override(None)

        self._tmp = tempfile.TemporaryDirectory()
        self.instance_root = Path(self._tmp.name)
        self.data_dir = self.instance_root / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.json_path = self.data_dir / DATA_FILE_NAME
        write_browser_fixture(self.json_path)
        payload = load_json(self.json_path)
        payload.setdefault("meta", {})["revision"] = 0
        self.json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.environ["BM_DEMO_FILE"] = str(self.json_path)
        demo_files_mod.set_demo_file_override(self.json_path)

        # Product IDs del fixture browser
        data = dict_to_appdata(load_json(self.json_path))
        self.product_ids = [p.id for p in data.productos]
        self.assertGreaterEqual(len(self.product_ids), 2)

    def tearDown(self) -> None:
        demo_files_mod.set_demo_file_override(None)
        if self._prev_demo is None:
            os.environ.pop("BM_DEMO_FILE", None)
        else:
            os.environ["BM_DEMO_FILE"] = self._prev_demo
        restore_test_isolation_env(self._prev_iso)
        self._tmp.cleanup()

    def test_01_client_a_creates_client_b_sees(self) -> None:
        json_s = str(self.json_path)
        with ProcessPoolExecutor(max_workers=2) as pool:
            fut_a = pool.submit(
                _worker_create_product, json_s, "Producto Multi A", "MCA-01"
            )
            created = fut_a.result(timeout=60)
            self.assertTrue(created["ok"], created)
            self.assertIn("Producto Multi A", created["nombres"])

            fut_b = pool.submit(_worker_reload_and_list, json_s)
            seen = fut_b.result(timeout=60)

        self.assertIn("Producto Multi A", seen["nombres"])
        self.assertIn("MCA-01", seen["codigos"])
        self.assertGreaterEqual(seen["revision"], 1)
        self.assertGreaterEqual(read_disk_revision(self.json_path), 1)

    def test_02_concurrent_distinct_product_updates(self) -> None:
        json_s = str(self.json_path)
        id_a, id_b = self.product_ids[0], self.product_ids[1]
        name_a, name_b = "Nombre Concurrente A", "Nombre Concurrente B"
        rev_before = read_disk_revision(self.json_path)

        with ProcessPoolExecutor(max_workers=2) as pool:
            futs = [
                pool.submit(_worker_edit_product, json_s, id_a, name_a),
                pool.submit(_worker_edit_product, json_s, id_b, name_b),
            ]
            results = [f.result(timeout=90) for f in as_completed(futs)]

        statuses = [r["status"] for r in results]
        self.assertEqual(statuses.count("ok"), 2, results)

        final = dict_to_appdata(load_json(self.json_path))
        by_id = {p.id: p.nombre for p in final.productos}
        self.assertEqual(by_id[id_a], name_a)
        self.assertEqual(by_id[id_b], name_b)
        self.assertGreater(final.revision, rev_before)
        self.assertGreaterEqual(final.revision, rev_before + 2)

    def test_03_same_expected_revision_one_conflict(self) -> None:
        json_s = str(self.json_path)
        with ProcessPoolExecutor(max_workers=2) as pool:
            futs = [
                pool.submit(_worker_same_revision_persist, json_s, "A"),
                pool.submit(_worker_same_revision_persist, json_s, "B"),
            ]
            results = [f.result(timeout=60) for f in as_completed(futs)]

        kinds = [r["status"] for r in results]
        self.assertIn("ok", kinds, results)
        self.assertIn("conflict", kinds, results)
        self.assertEqual(kinds.count("ok"), 1, results)
        self.assertEqual(read_disk_revision(self.json_path), 1)
        dict_to_appdata(load_json(self.json_path))

    def test_04_lock_held_other_times_out(self) -> None:
        ctx = mp.get_context("spawn")
        ready = ctx.Event()
        holder = ctx.Process(
            target=_worker_hold_lock,
            args=(str(self.json_path), 3.0, ready),
        )
        holder.start()
        try:
            self.assertTrue(ready.wait(timeout=5), "holder no adquirió lock")
            with self.assertRaises(SharedLockTimeout):
                acquire_shared_lock(
                    self.json_path,
                    operation="waiter",
                    timeout=0.4,
                    poll_interval=0.05,
                )
        finally:
            holder.join(timeout=10)
            self.assertFalse(holder.is_alive())

    def test_05_reclaim_dead_pid_same_host(self) -> None:
        local_host = socket.gethostname()
        # PID inventado que no debería estar vivo
        dead_pid = 2_147_000_001
        _write_fake_lock(
            self.json_path,
            host=local_host,
            pid=dead_pid,
            lease_until=_iso_future(300),
            operation="dead-pid",
        )
        info = acquire_shared_lock(
            self.json_path, operation="reclaim", timeout=2, poll_interval=0.05
        )
        try:
            self.assertEqual(info.host, local_host)
            self.assertEqual(info.pid, os.getpid())
        finally:
            release_shared_lock(self.json_path, info=info)
        self.assertFalse(lock_path_for(self.json_path).exists())

    def test_05b_no_reclaim_remote_future_lease(self) -> None:
        _write_fake_lock(
            self.json_path,
            host="remote-pc-other-host",
            pid=12345,
            lease_until=_iso_future(300),
            operation="remote-hold",
        )
        with self.assertRaises(SharedLockTimeout):
            acquire_shared_lock(
                self.json_path,
                operation="try-reclaim",
                timeout=0.5,
                poll_interval=0.05,
            )
        # Lock remoto intacto
        self.assertTrue(lock_path_for(self.json_path).exists())
        lock_path_for(self.json_path).unlink(missing_ok=True)

    def test_06_path_unavailable_missing_parent(self) -> None:
        missing = self.instance_root / "no_such_parent" / "datos_hotel.json"
        os.environ["BM_DEMO_FILE"] = str(missing)
        demo_files_mod.set_demo_file_override(None)
        with self.assertRaises(SharedPathUnavailable):
            coordinated_save(
                AppData(revision=0),
                expected_revision=0,
                timeout=2,
            )


if __name__ == "__main__":
    unittest.main()
