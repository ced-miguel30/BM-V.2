"""Bloqueo de proceso escritor (política operativa de un único escritor).

Complementa ``JsonWriteLock`` (exclusión durante una escritura atómica).
Este candado cubre toda la sesión Flet o Streamlit y evita dos UI sobre el
mismo JSON productivo. No convierte el JSON en almacén multiusuario seguro.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.deploy.config import DeployConfig


class WriterLockError(RuntimeError):
    """No se puede adquirir o respetar el candado de escritor."""


@dataclass(frozen=True)
class WriterLockInfo:
    role: str
    pid: int
    data_file: str
    acquired_at: str
    lock_path: str


def lock_path_for(data_file: Path) -> Path:
    return Path(str(Path(data_file).resolve()) + ".bm_writer.lock")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Existe pero no tenemos permiso para señalizar → asumir vivo.
        return True
    except OSError:
        # En Windows, pid inexistente suele ser OSError; vivo puede ser AccessDenied.
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:  # noqa: BLE001
            return False
    return True


def read_lock(lock_path: Path) -> WriterLockInfo | None:
    if not lock_path.is_file():
        return None
    try:
        raw = json.loads(lock_path.read_text(encoding="utf-8"))
        return WriterLockInfo(
            role=str(raw.get("role") or ""),
            pid=int(raw.get("pid") or 0),
            data_file=str(raw.get("data_file") or ""),
            acquired_at=str(raw.get("acquired_at") or ""),
            lock_path=str(lock_path),
        )
    except (OSError, ValueError, json.JSONDecodeError, TypeError):
        return None


def acquire_writer_lock(
    cfg: DeployConfig,
    *,
    role: str,
    force_stale: bool = True,
) -> WriterLockInfo:
    """Adquiere el candado exclusivo para ``cfg.data_file``."""
    data = cfg.data_file.resolve()
    path = lock_path_for(data)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = read_lock(path)
    if existing is not None:
        if existing.pid == os.getpid() and existing.role == role:
            return existing
        if force_stale and not _pid_alive(existing.pid):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                raise WriterLockError(
                    f"Candado obsoleto no eliminable ({path}): {exc}"
                ) from exc
        else:
            raise WriterLockError(
                "Ya hay un proceso escritor activo sobre los datos productivos. "
                f"rol={existing.role!r} pid={existing.pid} desde={existing.acquired_at}. "
                "Política: un único proceso escritor (Flet o Streamlit, no ambos). "
                "Cierre la otra aplicación o ejecute release-writer si el proceso murió."
            )

    payload = {
        "role": role,
        "pid": os.getpid(),
        "data_file": str(data),
        "acquired_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        # Creación exclusiva del candado definitivo.
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, tmp.read_bytes())
        finally:
            os.close(fd)
    except FileExistsError as exc:
        other = read_lock(path)
        raise WriterLockError(
            "Conflicto al adquirir el candado de escritor. "
            f"Otro proceso lo sostiene: {other}"
        ) from exc
    except OSError as exc:
        raise WriterLockError(f"No se pudo crear el candado {path}: {exc}") from exc
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass

    info = read_lock(path)
    if info is None:
        raise WriterLockError(f"Candado ilegible tras crear: {path}")
    return info


def release_writer_lock(
    cfg: DeployConfig,
    *,
    role: str | None = None,
    only_own: bool = True,
    force: bool = False,
) -> bool:
    """Libera el candado. Devuelve True si se eliminó."""
    path = lock_path_for(cfg.data_file)
    info = read_lock(path)
    if info is None:
        return False
    if force:
        path.unlink(missing_ok=True)
        return True
    if only_own and info.pid != os.getpid():
        if role is not None and info.role != role:
            raise WriterLockError(
                f"El candado pertenece a rol={info.role!r} pid={info.pid}; no se libera."
            )
        raise WriterLockError(
            f"El candado pertenece a pid={info.pid}; use --force-dead si el proceso murió."
        )
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise WriterLockError(f"No se pudo eliminar {path}: {exc}") from exc
    return True


def force_release_if_dead(cfg: DeployConfig) -> bool:
    path = lock_path_for(cfg.data_file)
    info = read_lock(path)
    if info is None:
        return False
    if _pid_alive(info.pid):
        raise WriterLockError(
            f"Proceso escritor aún vivo (pid={info.pid}, rol={info.role}). "
            "Cierre la aplicación antes de forzar."
        )
    path.unlink(missing_ok=True)
    return True


def assert_no_foreign_writer(cfg: DeployConfig, *, role: str) -> WriterLockInfo | None:
    """En perfil hotel, exige candado propio o ausencia de escritor ajeno."""
    path = lock_path_for(cfg.data_file)
    info = read_lock(path)
    if info is None:
        return None
    if info.pid == os.getpid():
        return info
    if not _pid_alive(info.pid):
        path.unlink(missing_ok=True)
        return None
    raise WriterLockError(
        "Segundo proceso escritor detectado. "
        f"Activo: rol={info.role!r} pid={info.pid}. "
        f"Intento: rol={role!r} pid={os.getpid()}. "
        "No inicie Flet y Streamlit a la vez sobre el mismo JSON."
    )
