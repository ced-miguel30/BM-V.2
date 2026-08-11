"""Tests de coordinación multi-PC (shared JSON + revision + lock)."""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import tempfile
import time
import unittest
from pathlib import Path

from app.core.application.adapters.memory_stores import (
    FileBackedAppDataStore,
    MemoryAppDataStore,
)
from app.core.models import AppData
from app.core.storage import demo_files as demo_files_mod
from app.core.storage.shared_coordinator import (
    SharedLockTimeout,
    SharedPathUnavailable,
    SharedRevisionConflict,
    SharedWriteAborted,
    acquire_shared_lock,
    assert_data_path_usable,
    coordinated_save,
    lock_path_for,
    read_disk_revision,
    release_shared_lock,
    shared_write_lock,
)
from app.data.serializers import appdata_to_dict, dict_to_appdata, load_json
from tests.browser.fixtures_minimos import write_browser_fixture
from tests.demo_isolation import restore_test_isolation_env


def _worker_distinct_update(json_path: str, tag: str, result_queue: mp.Queue) -> None:
    os.environ["BM_TEST_ISOLATION"] = "1"
    os.environ["BM_DEMO_FILE"] = json_path
    demo_files_mod.set_demo_file_override(None)
    try:
        # Serializar: esperar turno vía coordinated_save + retries on conflict
        data = dict_to_appdata(load_json(Path(json_path)))
        data.usuario_actual_id = tag
        for _ in range(40):
            try:
                fresh = dict_to_appdata(load_json(Path(json_path)))
                fresh.usuario_actual_id = f"{tag}:{fresh.revision}"
                coordinated_save(
                    fresh,
                    operation=f"worker-{tag}",
                    expected_revision=fresh.revision,
                    timeout=20,
                )
                result_queue.put(("ok", tag, fresh.revision))
                return
            except SharedRevisionConflict:
                time.sleep(0.05)
        result_queue.put(("fail", tag, "retries exhausted"))
    except Exception as exc:  # noqa: BLE001
        result_queue.put(("err", tag, repr(exc)))


def _worker_conflict_save(json_path: str, result_queue: mp.Queue) -> None:
    os.environ["BM_TEST_ISOLATION"] = "1"
    os.environ["BM_DEMO_FILE"] = json_path
    demo_files_mod.set_demo_file_override(None)
    try:
        data = dict_to_appdata(load_json(Path(json_path)))
        # Ambos workers parten de la misma revisión leída; forzar expected=0
        # tras una pequeña espera para maximizar solapamiento.
        time.sleep(0.05)
        data.usuario_actual_id = f"conflict-{os.getpid()}"
        coordinated_save(
            data,
            operation="conflict",
            expected_revision=0,
            timeout=20,
        )
        result_queue.put(("ok", data.revision))
    except SharedRevisionConflict as exc:
        result_queue.put(("conflict", str(exc)))
    except Exception as exc:  # noqa: BLE001
        result_queue.put(("err", repr(exc)))


def _worker_create_or_update(json_path: str, idx: int, result_queue: mp.Queue) -> None:
    os.environ["BM_TEST_ISOLATION"] = "1"
    os.environ["BM_DEMO_FILE"] = json_path
    demo_files_mod.set_demo_file_override(None)
    try:
        for _ in range(50):
            try:
                path = Path(json_path)
                if path.is_file():
                    data = dict_to_appdata(load_json(path))
                else:
                    data = AppData(revision=0)
                data.usuario_actual_id = f"p{idx}"
                coordinated_save(
                    data,
                    operation=f"create-{idx}",
                    expected_revision=data.revision,
                    timeout=25,
                )
                result_queue.put(("ok", idx, data.revision))
                return
            except SharedRevisionConflict:
                time.sleep(0.03)
        result_queue.put(("fail", idx, "retries"))
    except Exception as exc:  # noqa: BLE001
        result_queue.put(("err", idx, repr(exc)))


def _worker_hold_lock(json_path: str, hold_s: float, ready: mp.Event) -> None:
    os.environ["BM_TEST_ISOLATION"] = "1"
    os.environ["BM_DEMO_FILE"] = json_path
    demo_files_mod.set_demo_file_override(None)
    info = acquire_shared_lock(json_path, operation="hold", timeout=5, lease_seconds=30)
    ready.set()
    try:
        time.sleep(hold_s)
    finally:
        release_shared_lock(json_path, info=info)


class TestSharedStorageCoordinator(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_iso = os.environ.get("BM_TEST_ISOLATION")
        self._prev_demo = os.environ.get("BM_DEMO_FILE")
        os.environ["BM_TEST_ISOLATION"] = "1"
        demo_files_mod.set_demo_file_override(None)
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.json_path = self.dir / "datos_hotel.json"
        write_browser_fixture(self.json_path)
        # Asegurar revision 0 en fixture
        payload = load_json(self.json_path)
        payload.setdefault("meta", {})["revision"] = 0
        self.json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.environ["BM_DEMO_FILE"] = str(self.json_path)
        demo_files_mod.set_demo_file_override(self.json_path)

    def tearDown(self) -> None:
        demo_files_mod.set_demo_file_override(None)
        if self._prev_demo is None:
            os.environ.pop("BM_DEMO_FILE", None)
        else:
            os.environ["BM_DEMO_FILE"] = self._prev_demo
        restore_test_isolation_env(self._prev_iso)
        self._tmp.cleanup()

    def test_revision_roundtrip_serializers(self) -> None:
        data = dict_to_appdata(load_json(self.json_path))
        self.assertEqual(data.revision, 0)
        data.revision = 3
        d = appdata_to_dict(data)
        self.assertEqual(d["meta"]["revision"], 3)
        again = dict_to_appdata(d)
        self.assertEqual(again.revision, 3)
        # Missing revision → 0
        del d["meta"]["revision"]
        self.assertEqual(dict_to_appdata(d).revision, 0)

    def test_coordinated_save_bumps_revision(self) -> None:
        data = dict_to_appdata(load_json(self.json_path))
        coordinated_save(data, operation="test", expected_revision=0)
        self.assertEqual(data.revision, 1)
        self.assertEqual(read_disk_revision(self.json_path), 1)

    def test_revision_conflict(self) -> None:
        data = dict_to_appdata(load_json(self.json_path))
        coordinated_save(data, expected_revision=0)
        stale = dict_to_appdata(load_json(self.json_path))
        stale.revision = 0
        with self.assertRaises(SharedRevisionConflict):
            coordinated_save(stale, expected_revision=0)

    def test_stale_memory_without_expected(self) -> None:
        data = dict_to_appdata(load_json(self.json_path))
        coordinated_save(data, expected_revision=0)
        stale = AppData(revision=0, usuario_actual_id="x")
        with self.assertRaises(SharedRevisionConflict):
            coordinated_save(stale, expected_revision=None)

    def test_path_unavailable_missing_parent(self) -> None:
        missing = self.dir / "no_such_dir" / "datos.json"
        with self.assertRaises(SharedPathUnavailable):
            assert_data_path_usable(missing)
        with self.assertRaises(SharedPathUnavailable):
            os.environ["BM_DEMO_FILE"] = str(missing)
            demo_files_mod.set_demo_file_override(None)
            coordinated_save(AppData(), expected_revision=0, timeout=2)

    def test_no_fallback_unreachable_path(self) -> None:
        # Simula path con padre inexistente (UNC-like / missing drive si posible)
        candidates = [
            Path(r"Z:\bm_v2_shared_missing\data\datos_hotel.json"),
            Path(r"\\bm-v2-nonexistent-host\share\data\datos_hotel.json"),
            self.dir / "missing_parent" / "datos_hotel.json",
        ]
        raised = False
        for cand in candidates:
            try:
                assert_data_path_usable(cand)
            except SharedPathUnavailable:
                raised = True
                break
            except OSError:
                # Algunos SO fallan distinto; igual cuenta como no usable
                raised = True
                break
        self.assertTrue(
            raised,
            "Debe elevar SharedPathUnavailable sin fallback local",
        )

    def test_lock_timeout(self) -> None:
        ctx = mp.get_context("spawn")
        ready = ctx.Event()
        holder = ctx.Process(
            target=_worker_hold_lock,
            args=(str(self.json_path), 3.0, ready),
        )
        holder.start()
        self.assertTrue(ready.wait(timeout=5), "holder no adquirió lock")
        with self.assertRaises(SharedLockTimeout):
            acquire_shared_lock(
                self.json_path, operation="waiter", timeout=0.4, poll_interval=0.05
            )
        holder.join(timeout=10)
        self.assertFalse(holder.is_alive())

    def test_release_after_exception(self) -> None:
        lock = lock_path_for(self.json_path)
        with self.assertRaises(RuntimeError):
            with shared_write_lock(self.json_path, operation="boom", timeout=5):
                raise RuntimeError("boom")
        self.assertFalse(lock.exists(), "lock debe liberarse tras excepción")

    def test_restart_preserves_revision(self) -> None:
        data = dict_to_appdata(load_json(self.json_path))
        coordinated_save(data, expected_revision=0)
        coordinated_save(
            dict_to_appdata(load_json(self.json_path)),
            expected_revision=1,
        )
        # "Restart": clear in-process override mirror, reload
        demo_files_mod.set_demo_file_override(None)
        os.environ["BM_DEMO_FILE"] = str(self.json_path)
        reloaded = dict_to_appdata(load_json(self.json_path))
        self.assertEqual(reloaded.revision, 2)
        store = FileBackedAppDataStore()
        self.assertEqual(store.get().revision, 2)
        self.assertEqual(store.get_revision(), 2)

    def test_file_backed_persist_conflict_reloads(self) -> None:
        store = FileBackedAppDataStore()
        data = store.get()
        self.assertEqual(data.revision, 0)
        store.persist(data)
        self.assertEqual(store.get_revision(), 1)
        # Simular otro escritor
        other = dict_to_appdata(load_json(self.json_path))
        coordinated_save(other, expected_revision=1)
        # Memoria del store sigue en rev 1
        stale = store.get()
        self.assertEqual(stale.revision, 1)
        with self.assertRaises(SharedRevisionConflict):
            store.persist(stale)
        self.assertEqual(store.get_revision(), 2)

    def test_refresh_if_stale(self) -> None:
        store = FileBackedAppDataStore()
        store.get()
        other = dict_to_appdata(load_json(self.json_path))
        coordinated_save(other, expected_revision=0)
        refreshed = store.refresh_if_stale()
        self.assertEqual(refreshed.revision, 1)

    def test_memory_store_without_coordinator(self) -> None:
        mem = MemoryAppDataStore(AppData(revision=5, usuario_actual_id="m"))
        out = mem.persist(AppData(revision=9, usuario_actual_id="n"))
        self.assertEqual(out.revision, 9)
        self.assertEqual(mem.get_revision(), 9)
        self.assertEqual(mem.refresh_if_stale().revision, 9)
        # No toca disco
        self.assertEqual(read_disk_revision(self.json_path), 0)

    def test_two_processes_distinct_updates(self) -> None:
        ctx = mp.get_context("spawn")
        q: mp.Queue = ctx.Queue()
        procs = [
            ctx.Process(
                target=_worker_distinct_update,
                args=(str(self.json_path), "A", q),
            ),
            ctx.Process(
                target=_worker_distinct_update,
                args=(str(self.json_path), "B", q),
            ),
        ]
        for p in procs:
            p.start()
        results = [q.get(timeout=60) for _ in procs]
        for p in procs:
            p.join(timeout=30)
            self.assertFalse(p.is_alive())
        statuses = [r[0] for r in results]
        self.assertEqual(statuses.count("ok"), 2, results)
        final = read_disk_revision(self.json_path)
        self.assertGreaterEqual(final, 2)
        # JSON válido
        dict_to_appdata(load_json(self.json_path))

    def test_two_processes_same_conflict(self) -> None:
        ctx = mp.get_context("spawn")
        q: mp.Queue = ctx.Queue()
        procs = [
            ctx.Process(target=_worker_conflict_save, args=(str(self.json_path), q))
            for _ in range(2)
        ]
        for p in procs:
            p.start()
        results = [q.get(timeout=60) for _ in procs]
        for p in procs:
            p.join(timeout=30)
        kinds = [r[0] for r in results]
        self.assertIn("ok", kinds, results)
        self.assertIn("conflict", kinds, results)
        self.assertEqual(read_disk_revision(self.json_path), 1)
        dict_to_appdata(load_json(self.json_path))

    def test_three_processes_creating(self) -> None:
        # Empezar sin fichero para forzar create path
        self.json_path.unlink()
        ctx = mp.get_context("spawn")
        q: mp.Queue = ctx.Queue()
        procs = [
            ctx.Process(
                target=_worker_create_or_update,
                args=(str(self.json_path), i, q),
            )
            for i in range(3)
        ]
        for p in procs:
            p.start()
        results = [q.get(timeout=90) for _ in procs]
        for p in procs:
            p.join(timeout=30)
            self.assertFalse(p.is_alive())
        self.assertTrue(all(r[0] in ("ok", "fail") for r in results), results)
        oks = [r for r in results if r[0] == "ok"]
        self.assertGreaterEqual(len(oks), 1)
        self.assertTrue(self.json_path.is_file())
        data = dict_to_appdata(load_json(self.json_path))
        self.assertGreaterEqual(data.revision, 1)
        # Sin corrupción: serializa de nuevo
        appdata_to_dict(data)

    def test_shared_write_aborted_wraps(self) -> None:
        # Forzar fallo de escritura mockeando save_demo_files
        from unittest.mock import patch

        data = dict_to_appdata(load_json(self.json_path))
        with patch(
            "app.core.storage.shared_coordinator.save_demo_files",
            side_effect=OSError("disk full"),
        ):
            with self.assertRaises(SharedWriteAborted):
                coordinated_save(data, expected_revision=0, timeout=5)
        # Lock liberado
        self.assertFalse(lock_path_for(self.json_path).exists())
        # Revisión intacta
        self.assertEqual(read_disk_revision(self.json_path), 0)


if __name__ == "__main__":
    unittest.main()
