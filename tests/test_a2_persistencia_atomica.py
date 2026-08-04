"""Fase A2 — persistencia JSON atómica y JsonWriteLock."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.storage import demo_files as demo_files_mod
from app.core.storage.json_atomic import (
    AtomicWriteResult,
    JsonLockTimeoutError,
    JsonValidationError,
    JsonWriteAborted,
    JsonWriteLock,
    atomic_write_json,
    cleanup_stale_temps,
    is_atomic_temp_name,
    serialize_json_dict,
    transactional_update,
)
from app.data import serializers as serializers_mod
from tests.demo_isolation import protected_demo_path, restore_test_isolation_env


class TestA2AtomicWrite(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_env = os.environ.get("BM_TEST_ISOLATION")
        os.environ["BM_TEST_ISOLATION"] = "1"
        demo_files_mod.set_demo_file_override(None)
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.path = self.dir / "estado.json"

    def tearDown(self) -> None:
        demo_files_mod.set_demo_file_override(None)
        # No locks ni temps abandonados
        leftovers = [
            p
            for p in self.dir.iterdir()
            if p.suffix == ".lock" or is_atomic_temp_name(p.name)
        ]
        self._tmp.cleanup()
        restore_test_isolation_env(self._prev_env)
        self.assertEqual(
            leftovers,
            [],
            f"Quedaron locks/temporales: {leftovers}",
        )

    def test_escritura_atomica_correcta_y_json_valido(self) -> None:
        result = atomic_write_json(self.path, {"hola": "niño", "n": 1})
        self.assertTrue(result.replaced)
        self.assertTrue(self.path.is_file())
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["hola"], "niño")
        self.assertEqual(data["n"], 1)
        # UTF-8 / ensure_ascii=False
        raw = self.path.read_bytes()
        self.assertIn("niño".encode("utf-8"), raw)
        self.assertNotIn(b"\\u", raw)

    def test_validacion_falla_conserva_anterior_y_limpia_tmp(self) -> None:
        atomic_write_json(self.path, {"v": 1})
        before = self.path.read_bytes()

        def bad(_data: dict) -> None:
            raise JsonValidationError("inválido")

        with self.assertRaises(JsonValidationError):
            atomic_write_json(self.path, {"v": 2}, validate=bad)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(
            [p for p in self.dir.iterdir() if is_atomic_temp_name(p.name)],
            [],
        )

    def test_serializacion_falla_conserva_anterior(self) -> None:
        atomic_write_json(self.path, {"v": 1})
        before = self.path.read_bytes()

        with patch(
            "app.core.storage.json_atomic.serialize_json_dict",
            side_effect=TypeError("no serializable"),
        ):
            with self.assertRaises(JsonWriteAborted):
                atomic_write_json(self.path, {"v": 2})
        self.assertEqual(self.path.read_bytes(), before)

    def test_fallo_escritura_temporal_conserva_anterior(self) -> None:
        atomic_write_json(self.path, {"v": 1})
        before = self.path.read_bytes()
        real_open = open

        def boom_open(path, mode="r", *args, **kwargs):  # noqa: ANN001
            if mode == "xb":
                raise OSError("disk full")
            return real_open(path, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=boom_open):
            with self.assertRaises(OSError):
                atomic_write_json(self.path, {"v": 2})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(any(is_atomic_temp_name(p.name) for p in self.dir.iterdir()))

    def test_fallo_flush_antes_de_fsync_conserva_anterior(self) -> None:
        atomic_write_json(self.path, {"v": 1})
        before = self.path.read_bytes()
        real_open = open

        def open_flush_boom(path, mode="r", *args, **kwargs):  # noqa: ANN001
            fh = real_open(path, mode, *args, **kwargs)
            if mode == "xb":
                def _boom_flush() -> None:
                    raise OSError("flush failed")

                fh.flush = _boom_flush  # type: ignore[method-assign]
            return fh

        with patch("builtins.open", side_effect=open_flush_boom):
            with self.assertRaises(OSError):
                atomic_write_json(self.path, {"v": 2})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(any(is_atomic_temp_name(p.name) for p in self.dir.iterdir()))

    def test_fallo_fsync_antes_de_replace_conserva_anterior(self) -> None:
        atomic_write_json(self.path, {"v": 1})
        before = self.path.read_bytes()
        calls = {"n": 0}
        real_fsync = os.fsync

        def flaky_fsync(fd: int) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("fsync temp failed")
            return real_fsync(fd)

        with patch("os.fsync", side_effect=flaky_fsync):
            with self.assertRaises(OSError):
                atomic_write_json(self.path, {"v": 2})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(any(is_atomic_temp_name(p.name) for p in self.dir.iterdir()))

    def test_os_replace_mismo_directorio_y_fallo_conserva_anterior(self) -> None:
        atomic_write_json(self.path, {"v": 1})
        before = self.path.read_bytes()
        seen: dict[str, Path] = {}

        real_replace = os.replace

        def tracking_replace(src: str, dst: str) -> None:
            seen["src"] = Path(src)
            seen["dst"] = Path(dst)
            raise OSError("replace denied")

        with patch("os.replace", side_effect=tracking_replace):
            with self.assertRaises(JsonWriteAborted):
                atomic_write_json(self.path, {"v": 2})

        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(seen["src"].parent, seen["dst"].parent)
        self.assertEqual(seen["dst"], self.path.resolve())
        self.assertFalse(any(is_atomic_temp_name(p.name) for p in self.dir.iterdir()))

        # Éxito: replace recibe mismo directorio
        seen.clear()

        def ok_replace(src: str, dst: str) -> None:
            seen["src"] = Path(src)
            seen["dst"] = Path(dst)
            return real_replace(src, dst)

        with patch("os.replace", side_effect=ok_replace):
            atomic_write_json(self.path, {"v": 3})
        self.assertEqual(seen["src"].parent, self.path.resolve().parent)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["v"], 3)

    def test_dir_sync_fallo_tras_replace_no_es_rollback(self) -> None:
        with patch(
            "app.core.storage.json_atomic._fsync_directory", return_value=False
        ):
            result = atomic_write_json(self.path, {"ok": True})
        self.assertTrue(result.replaced)
        self.assertIs(result.dir_synced, False)
        self.assertIn("replace_ok_dir_sync", result.durability_note)
        self.assertTrue(self.path.is_file())

    def test_save_json_usa_escritura_atomica(self) -> None:
        serializers_mod.save_json(self.path, {"via": "save_json"})
        self.assertEqual(
            json.loads(self.path.read_text(encoding="utf-8"))["via"], "save_json"
        )


class TestA2Lock(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_env = os.environ.get("BM_TEST_ISOLATION")
        os.environ["BM_TEST_ISOLATION"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.path = self.dir / "estado.json"
        atomic_write_json(self.path, {"n": 0})

    def tearDown(self) -> None:
        leftovers = [
            p
            for p in Path(self._tmp.name).iterdir()
            if p.suffix == ".lock" or is_atomic_temp_name(p.name)
        ]
        self._tmp.cleanup()
        restore_test_isolation_env(self._prev_env)
        self.assertEqual(leftovers, [])

    def test_lock_se_libera_tras_excepcion(self) -> None:
        try:
            with JsonWriteLock(self.path, timeout=2.0):
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        # Debe poder adquirirse de nuevo
        with JsonWriteLock(self.path, timeout=2.0):
            pass
        self.assertFalse(Path(str(self.path.resolve()) + ".lock").exists())

    def test_timeout_bloqueo_ocupado(self) -> None:
        held = threading.Event()
        release = threading.Event()

        def holder() -> None:
            with JsonWriteLock(self.path, timeout=5.0):
                held.set()
                release.wait(timeout=5.0)

        t = threading.Thread(target=holder)
        t.start()
        self.assertTrue(held.wait(timeout=2.0))
        with self.assertRaises(JsonLockTimeoutError):
            JsonWriteLock(self.path, timeout=0.2, poll_interval=0.05).acquire()
        release.set()
        t.join(timeout=5.0)

    def test_dos_escritores_sin_lost_update(self) -> None:
        barrier = threading.Barrier(2)
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                barrier.wait(timeout=5.0)

                def mutate(state: dict) -> dict:
                    state["n"] = int(state.get("n", 0)) + 1
                    return state

                transactional_update(self.path, mutate, lock_timeout=10.0)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=15.0)
        t2.join(timeout=15.0)
        self.assertEqual(errors, [])
        final = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(final["n"], 2)

    def test_segundo_escritor_releee_dentro_del_lock(self) -> None:
        """B solo entra tras A; lee el valor fresco 10 y deja 11."""
        reads: list[int] = []
        gate = threading.Event()

        def writer_a() -> None:
            def mutate(state: dict) -> dict:
                state["n"] = 10
                return state

            transactional_update(self.path, mutate)
            gate.set()

        def writer_b() -> None:
            self.assertTrue(gate.wait(timeout=5.0))

            def mutate(state: dict) -> dict:
                reads.append(int(state.get("n", 0)))
                state["n"] = int(state.get("n", 0)) + 1
                return state

            transactional_update(self.path, mutate, lock_timeout=10.0)

        ta = threading.Thread(target=writer_a)
        tb = threading.Thread(target=writer_b)
        ta.start()
        tb.start()
        ta.join(timeout=10.0)
        tb.join(timeout=10.0)
        self.assertEqual(reads, [10])
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["n"], 11)


class TestA2TransactionalCopy(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_env = os.environ.get("BM_TEST_ISOLATION")
        os.environ["BM_TEST_ISOLATION"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "estado.json"
        atomic_write_json(self.path, {"items": [1], "n": 0})

    def tearDown(self) -> None:
        self._tmp.cleanup()
        restore_test_isolation_env(self._prev_env)

    def test_fallo_no_muta_estado_original_en_memoria(self) -> None:
        original = {"items": [1], "n": 0}

        def mutator(state: dict) -> dict:
            state["items"].append(99)
            state["n"] = 5
            raise RuntimeError("abort mutate")

        with self.assertRaises(RuntimeError):
            transactional_update(
                self.path,
                mutator,
                reader=lambda _p: original,
            )
        self.assertEqual(original, {"items": [1], "n": 0})
        self.assertEqual(
            json.loads(self.path.read_text(encoding="utf-8")),
            {"items": [1], "n": 0},
        )

    def test_validacion_en_transactional_no_publica(self) -> None:
        def mutate(state: dict) -> dict:
            state["n"] = 99
            return state

        def validate(state: dict) -> None:
            raise JsonValidationError("no")

        with self.assertRaises(JsonValidationError):
            transactional_update(self.path, mutate, validate=validate)
        self.assertEqual(
            json.loads(self.path.read_text(encoding="utf-8"))["n"], 0
        )


class TestA2IsolationCompat(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_env = os.environ.get("BM_TEST_ISOLATION")
        os.environ["BM_TEST_ISOLATION"] = "1"
        demo_files_mod.set_demo_file_override(None)

    def tearDown(self) -> None:
        demo_files_mod.set_demo_file_override(None)
        restore_test_isolation_env(self._prev_env)

    def test_demo_canonica_bloqueada(self) -> None:
        with self.assertRaises(RuntimeError):
            serializers_mod.save_json(
                protected_demo_path(), {"probe": "a2"}
            )

    def test_temporales_permitidos_bajo_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "datos_hotel.json"
            result = atomic_write_json(dest, {"tmp": True})
            self.assertIsInstance(result, AtomicWriteResult)
            self.assertTrue(dest.is_file())
            dest.unlink()

    def test_cleanup_stale_temps_no_toca_canonico(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            canon = d / "estado.json"
            atomic_write_json(canon, {"keep": True})
            stale = d / f"estado.json.tmp.{os.getpid()}.deadbeef"
            stale.write_text("{}", encoding="utf-8")
            old = time.time() - 7200
            os.utime(stale, (old, old))
            removed = cleanup_stale_temps(d, max_age_seconds=3600)
            self.assertEqual(removed, [stale])
            self.assertTrue(canon.is_file())
            self.assertFalse(stale.exists())

    def test_decimal_no_pasa_por_float(self) -> None:
        from decimal import Decimal

        raw = serialize_json_dict({"precio": Decimal("1.234567")})
        text = raw.decode("utf-8")
        self.assertIn("1.234567", text)
        self.assertNotIn("1.234566", text)


if __name__ == "__main__":
    unittest.main()
