"""Coordinación multi-PC para el JSON AppData compartido.

Bloqueo por fichero ``{data_file}.bm_shared.lock`` + campo ``meta.revision``.
No sustituye SQLite/Postgres; coordina escritores sobre el mismo filesystem
compartido (SMB/NAS). No mantener el lock a través de UI.
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import socket
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.core.models import AppData
from app.core.storage.demo_files import get_demo_file, save_demo_files
from app.data.serializers import dict_to_appdata, load_json

_LOG = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 30.0
_DEFAULT_POLL_S = 0.05
_DEFAULT_LEASE_S = 60.0
_LEASE_GRACE_S = 5.0
_LOCK_SUFFIX = ".bm_shared.lock"


class SharedStorageError(Exception):
    """Error base de almacenamiento compartido."""


class SharedLockTimeout(SharedStorageError, TimeoutError):
    """No se adquirió el lock antes del timeout."""


class SharedRevisionConflict(SharedStorageError):
    """La revisión en memoria no coincide con la del disco."""


class SharedPathUnavailable(SharedStorageError):
    """Ruta de datos inaccesible (red caída, padre inexistente, etc.)."""


class SharedWriteAborted(SharedStorageError):
    """Escritura abortada; el JSON anterior debe permanecer intacto."""


@dataclass
class SharedLockInfo:
    user: str
    host: str
    pid: int
    operation: str
    acquired_at: str
    data_file: str
    lock_path: str
    lease_until: str


def lock_path_for(data_file: Path | str) -> Path:
    return Path(str(Path(data_file)) + _LOCK_SUFFIX)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
            )
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                ok = ctypes.windll.kernel32.GetExitCodeProcess(
                    handle, ctypes.byref(exit_code)
                )
                if not ok:
                    return False
                return int(exit_code.value) == STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        else:
            os.kill(pid, 0)
            return True
    except (OSError, AttributeError, ValueError):
        return False


def assert_data_path_usable(path: Path | str) -> Path:
    """Comprueba que el padre existe y admite escritura (probe temp).

    Sin fallback local: si falla → ``SharedPathUnavailable``.
    """
    target = Path(path)
    parent = target.parent
    try:
        if not parent.exists() or not parent.is_dir():
            raise SharedPathUnavailable(
                f"Directorio de datos inaccesible o inexistente: {parent}"
            )
        probe = parent / f".bm_shared_probe.{os.getpid()}.{time.time_ns()}"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            raise SharedPathUnavailable(
                f"No se puede escribir junto a {target}: {exc}"
            ) from exc
    except SharedPathUnavailable:
        raise
    except OSError as exc:
        raise SharedPathUnavailable(
            f"Ruta de datos no usable ({target}): {exc}"
        ) from exc
    return target


def _read_lock_payload(lock_path: Path) -> dict[str, Any] | None:
    try:
        raw = lock_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _lock_mtime_age(lock_path: Path) -> float | None:
    try:
        return time.time() - lock_path.stat().st_mtime
    except OSError:
        return None


def _should_reclaim(
    lock_path: Path,
    payload: dict[str, Any] | None,
    *,
    local_host: str,
    local_pid: int,
) -> tuple[bool, str]:
    """Decide si el lock existente puede reclamarse. Conservador."""
    if payload is None:
        age = _lock_mtime_age(lock_path)
        # Corrupt: solo tras gracia de lease (documentado)
        if age is not None and age > (_DEFAULT_LEASE_S + _LEASE_GRACE_S):
            return True, "lock corrupt and mtime past lease grace"
        return False, "lock corrupt; waiting lease grace"

    try:
        remote_pid = int(payload.get("pid") or 0)
    except (TypeError, ValueError):
        remote_pid = 0
    remote_host = str(payload.get("host") or "")

    if remote_pid == local_pid and remote_host == local_host:
        return True, "reentrant same pid+host"

    lease_until = _parse_iso(str(payload.get("lease_until") or ""))
    now = _utc_now()
    lease_expired = lease_until is not None and now > lease_until
    age = _lock_mtime_age(lock_path)
    mtime_stale = age is not None and age > (_DEFAULT_LEASE_S + _LEASE_GRACE_S)

    same_host = bool(remote_host) and remote_host == local_host
    if same_host:
        if remote_pid and not _pid_alive(remote_pid):
            return True, "same host and pid not alive"
        if lease_expired and mtime_stale:
            return True, "same host lease expired and mtime stale"
        return False, "same host lock still held"

    # Remote / different machine: NEVER reclaim solely because pid dead locally
    if lease_expired and mtime_stale:
        return True, "remote lease expired and mtime past grace"
    return False, "remote lock active or lease not expired"


def _try_unlink_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink(missing_ok=True)
    except OSError as exc:
        _LOG.warning("No se pudo eliminar lock stale %s: %s", lock_path, exc)


def acquire_shared_lock(
    data_file: Path | str,
    *,
    operation: str = "write",
    timeout: float = _DEFAULT_TIMEOUT_S,
    poll_interval: float = _DEFAULT_POLL_S,
    lease_seconds: float = _DEFAULT_LEASE_S,
) -> SharedLockInfo:
    """Adquiere ``{data_file}.bm_shared.lock`` vía O_CREAT|O_EXCL."""
    target = Path(data_file)
    try:
        assert_data_path_usable(target)
    except SharedPathUnavailable:
        raise
    except OSError as exc:
        raise SharedPathUnavailable(str(exc)) from exc

    lock_path = lock_path_for(target)
    local_host = socket.gethostname()
    local_user = getpass.getuser()
    local_pid = os.getpid()
    deadline = time.monotonic() + max(0.0, float(timeout))
    documented_corrupt = False

    while True:
        try:
            fd = os.open(
                str(lock_path),
                os.O_CREAT | os.O_EXCL | os.O_RDWR,
            )
        except FileExistsError:
            payload = _read_lock_payload(lock_path)
            if payload is None and not documented_corrupt:
                _LOG.warning(
                    "Lock corrupt/unreadable at %s; reclaim only after lease grace",
                    lock_path,
                )
                documented_corrupt = True
            reclaim, reason = _should_reclaim(
                lock_path,
                payload,
                local_host=local_host,
                local_pid=local_pid,
            )
            if reclaim:
                _LOG.info("Reclaiming shared lock %s (%s)", lock_path, reason)
                _try_unlink_lock(lock_path)
                continue
            if time.monotonic() >= deadline:
                holder = ""
                if payload:
                    holder = (
                        f" holder={payload.get('user')}@{payload.get('host')}"
                        f" pid={payload.get('pid')} op={payload.get('operation')}"
                    )
                raise SharedLockTimeout(
                    f"Timeout ({timeout}s) adquiriendo lock {lock_path}.{holder}"
                ) from None
            time.sleep(poll_interval)
            continue
        except OSError as exc:
            # Network / path gone mid-acquire
            raise SharedPathUnavailable(
                f"No se pudo crear lock en {lock_path}: {exc}"
            ) from exc

        acquired_at = _utc_now()
        lease_until = acquired_at.timestamp() + float(lease_seconds)
        lease_dt = datetime.fromtimestamp(lease_until, tz=timezone.utc)
        info = SharedLockInfo(
            user=local_user,
            host=local_host,
            pid=local_pid,
            operation=operation,
            acquired_at=_iso(acquired_at),
            data_file=str(target),
            lock_path=str(lock_path),
            lease_until=_iso(lease_dt),
        )
        try:
            body = (
                json.dumps(asdict(info), ensure_ascii=False, indent=2) + "\n"
            ).encode("utf-8")
            os.write(fd, body)
            try:
                os.fsync(fd)
            except OSError:
                pass
        except OSError as exc:
            _try_unlink_lock(lock_path)
            raise SharedPathUnavailable(
                f"No se pudo escribir payload del lock: {exc}"
            ) from exc
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
        return info


def release_shared_lock(
    data_file: Path | str,
    *,
    info: SharedLockInfo | None = None,
) -> None:
    lock_path = lock_path_for(data_file) if info is None else Path(info.lock_path)
    payload = _read_lock_payload(lock_path)
    if payload is not None and info is not None:
        same = (
            int(payload.get("pid") or 0) == info.pid
            and str(payload.get("host") or "") == info.host
        )
        if not same:
            _LOG.warning(
                "Omitiendo release: lock %s no pertenece a este proceso", lock_path
            )
            return
    _try_unlink_lock(lock_path)


@contextmanager
def shared_write_lock(
    data_file: Path | str,
    *,
    operation: str = "write",
    timeout: float = _DEFAULT_TIMEOUT_S,
    poll_interval: float = _DEFAULT_POLL_S,
    lease_seconds: float = _DEFAULT_LEASE_S,
) -> Iterator[SharedLockInfo]:
    """Context manager de bajo nivel. No retener a través de UI."""
    info = acquire_shared_lock(
        data_file,
        operation=operation,
        timeout=timeout,
        poll_interval=poll_interval,
        lease_seconds=lease_seconds,
    )
    try:
        yield info
    finally:
        release_shared_lock(data_file, info=info)


def read_disk_revision(data_file: Path | str) -> int:
    """Lee ``meta.revision`` del JSON sin hidratar AppData completo si es posible."""
    path = Path(data_file)
    try:
        if not path.is_file():
            return 0
        payload = load_json(path)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SharedPathUnavailable(f"No se pudo leer revisión de {path}: {exc}") from exc
    meta = payload.get("meta") if isinstance(payload, dict) else None
    if not isinstance(meta, dict):
        return 0
    try:
        return int(meta.get("revision", 0) or 0)
    except (TypeError, ValueError):
        return 0


def coordinated_save(
    data: AppData,
    *,
    operation: str = "persist",
    expected_revision: int | None = None,
    timeout: float = _DEFAULT_TIMEOUT_S,
) -> AppData:
    """Guarda AppData bajo lock compartido incrementando ``revision``.

    Pasos: resolve path → usable → lock → load fresh → check revision →
    bump → atomic write → verify → release.
    """
    data_file = get_demo_file()
    assert_data_path_usable(data_file)
    info = acquire_shared_lock(
        data_file, operation=operation, timeout=timeout
    )
    try:
        if data_file.is_file():
            try:
                disk = dict_to_appdata(load_json(data_file))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise SharedPathUnavailable(
                    f"No se pudo cargar AppData desde {data_file}: {exc}"
                ) from exc
        else:
            disk = AppData(revision=0)

        disk_rev = int(getattr(disk, "revision", 0) or 0)
        if expected_revision is not None:
            if disk_rev != int(expected_revision):
                raise SharedRevisionConflict(
                    f"Conflicto de revisión: esperado {expected_revision}, "
                    f"en disco {disk_rev}"
                )
        else:
            mem_rev = int(getattr(data, "revision", 0) or 0)
            if mem_rev < disk_rev:
                raise SharedRevisionConflict(
                    f"Memoria obsoleta: revisión {mem_rev} < disco {disk_rev}"
                )

        data.revision = disk_rev + 1
        try:
            save_demo_files(data)
        except Exception as exc:  # noqa: BLE001 — wrap then re-raise type
            raise SharedWriteAborted(
                f"Escritura abortada en {data_file}: {exc}"
            ) from exc

        try:
            verified = read_disk_revision(data_file)
        except SharedPathUnavailable:
            raise
        if verified != int(data.revision):
            raise SharedWriteAborted(
                f"Verificación fallida: disco revision={verified}, "
                f"esperado {data.revision}"
            )
        return data
    finally:
        release_shared_lock(data_file, info=info)
