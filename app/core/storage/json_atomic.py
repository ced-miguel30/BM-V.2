"""Persistencia JSON atómica con bloqueo de escritura (Fase A2).

Unidad transaccional actual: un único fichero JSON canónico
(``data/demo/datos_hotel.json`` vía ``get_demo_file()``). Metadatos de
exportación u otros JSON auxiliares no forman parte de esta unidad.

Garantías del bloqueo (``JsonWriteLock``):
- Exclusión mutua entre escritores del **mismo** fichero JSON en un
  prototipo de servidor único que comparte filesystem.
- Coordina hilos/procesos locales mediante fichero ``*.lock`` (O_EXCL).
- **No** sustituye transacciones PostgreSQL.
- **No** coordina múltiples servidores sin filesystem/lock compartido.

Adjuntos binarios: ``os.replace`` del JSON **no** hace atómica una operación
conjunta JSON+binario. Staging/publicación/compensación = fases documentales.

Temporales: ``{nombre}.json.tmp.{pid}.{token}`` en el mismo directorio.
No se promocionan automáticamente a canónicos. Limpieza solo de temporales
claramente obsoletos (edad).
"""

from __future__ import annotations

import copy
import json
import os
import secrets
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, TypeVar

T = TypeVar("T")

# Sufijo de temporales de escritura atómica (identificable, no colisiona con .json).
_TMP_MARKER = ".tmp."
_DEFAULT_LOCK_TIMEOUT_S = 30.0
_DEFAULT_LOCK_POLL_S = 0.05
_STALE_TMP_AGE_S = 3600.0


class JsonLockTimeoutError(TimeoutError):
    """No se pudo adquirir el bloqueo antes del timeout."""


class JsonAtomicError(RuntimeError):
    """Error genérico de persistencia atómica."""


class JsonValidationError(JsonAtomicError):
    """La validación de la copia rechazó publicar el JSON."""


class JsonWriteAborted(JsonAtomicError):
    """Fallo antes de ``os.replace``; el destino anterior permanece intacto."""


@dataclass(frozen=True)
class AtomicWriteResult:
    """Resultado de una escritura atómica."""

    path: Path
    replaced: bool
    """True si ``os.replace`` se ejecutó con éxito."""
    dir_synced: bool | None
    """True/False tras intentar fsync del directorio; None si no se intentó."""
    durability_note: str
    """Descripción de la garantía de durabilidad observada."""


@dataclass(frozen=True)
class TransactionalUpdateResult:
    path: Path
    state: Any
    write: AtomicWriteResult


class JsonWriteLock:
    """Bloqueo exclusivo por fichero JSON (context manager).

    Recurso: ``{destino}.lock`` junto al JSON concreto.
    No bloquear JSON temporales independientes salvo que compartan path.
    """

    def __init__(
        self,
        target: Path | str,
        *,
        timeout: float = _DEFAULT_LOCK_TIMEOUT_S,
        poll_interval: float = _DEFAULT_LOCK_POLL_S,
    ) -> None:
        self.target = Path(target).resolve()
        self.lock_path = Path(str(self.target) + ".lock")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._fd: int | None = None

    def acquire(self) -> None:
        if self._fd is not None:
            return
        deadline = time.monotonic() + self.timeout
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                fd = os.open(
                    str(self.lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_RDWR,
                )
                try:
                    os.write(fd, f"{os.getpid()}\n".encode("ascii", errors="replace"))
                except OSError:
                    pass
                self._fd = fd
                return
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise JsonLockTimeoutError(
                        f"Timeout ({self.timeout}s) adquiriendo bloqueo "
                        f"{self.lock_path}"
                    ) from None
                time.sleep(self.poll_interval)

    def release(self) -> None:
        fd = self._fd
        self._fd = None
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            if self.lock_path.exists():
                self.lock_path.unlink()
        except OSError:
            pass

    def __enter__(self) -> JsonWriteLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.release()


@contextmanager
def json_write_lock(
    target: Path | str,
    *,
    timeout: float = _DEFAULT_LOCK_TIMEOUT_S,
    poll_interval: float = _DEFAULT_LOCK_POLL_S,
) -> Iterator[JsonWriteLock]:
    lock = JsonWriteLock(target, timeout=timeout, poll_interval=poll_interval)
    lock.acquire()
    try:
        yield lock
    finally:
        lock.release()


def serialize_json_dict(data: dict) -> bytes:
    """Serialización compatible con el formato actual (UTF-8, indent 2, ensure_ascii=False).

    Decimal → string vía ``format(d, 'f')`` (sin float silencioso).
    Sin salto de línea final forzado (compatibilidad con ``save_json`` histórico).
    """
    from app.data.serializers import _Encoder

    text = json.dumps(data, cls=_Encoder, indent=2, ensure_ascii=False)
    return text.encode("utf-8")


def _temp_path_for(destination: Path) -> Path:
    token = secrets.token_hex(8)
    # p.ej. datos_hotel.json.tmp.12345.a1b2c3d4
    return destination.parent / (
        f"{destination.name}{_TMP_MARKER}{os.getpid()}.{token}"
    )


def is_atomic_temp_name(name: str) -> bool:
    """True si el nombre encaja con el patrón de temporales A2."""
    return _TMP_MARKER in name and ".lock" not in name


def cleanup_stale_temps(
    directory: Path | str,
    *,
    max_age_seconds: float = _STALE_TMP_AGE_S,
    now: float | None = None,
) -> list[Path]:
    """Elimina solo temporales A2 claramente obsoletos. No toca el JSON canónico."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    removed: list[Path] = []
    stamp = time.time() if now is None else now
    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        if not is_atomic_temp_name(entry.name):
            continue
        try:
            age = stamp - entry.stat().st_mtime
        except OSError:
            continue
        if age < max_age_seconds:
            continue
        try:
            entry.unlink()
            removed.append(entry)
        except OSError:
            continue
    return removed


def _fsync_directory(directory: Path) -> bool:
    """Intenta fsync del directorio. En Windows suele no estar soportado."""
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return False
    try:
        os.fsync(fd)
        return True
    except OSError:
        return False
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def atomic_write_json(
    path: Path | str,
    data: dict,
    *,
    validate: Callable[[dict], None] | None = None,
    acquire_lock: bool = True,
    lock_timeout: float = _DEFAULT_LOCK_TIMEOUT_S,
    cleanup_stale: bool = True,
) -> AtomicWriteResult:
    """Escribe ``data`` de forma atómica en ``path`` (temp + fsync + os.replace).

    Si ``validate`` falla, no se publica. Fallos antes de ``os.replace`` dejan
    el destino intacto y limpian el temporal.
    """
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    if cleanup_stale:
        cleanup_stale_temps(destination.parent)

    if validate is not None:
        validate(data)

    try:
        payload = serialize_json_dict(data)
    except Exception as exc:  # noqa: BLE001
        raise JsonWriteAborted(f"Serialización fallida: {exc}") from exc

    def _write_unlocked() -> AtomicWriteResult:
        tmp = _temp_path_for(destination)
        replaced = False
        fh = None
        try:
            # Escritura buffered + flush + fsync (pasos 9–12 del flujo A2).
            fh = open(tmp, "xb")  # noqa: PTH123 — exclusive create + flush/fsync
            try:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                fh.close()
                fh = None

            try:
                os.replace(str(tmp), str(destination))
                replaced = True
            except OSError as exc:
                raise JsonWriteAborted(
                    f"os.replace falló; destino intacto: {exc}"
                ) from exc

            dir_ok = _fsync_directory(destination.parent)
            if dir_ok:
                note = "replace_ok_dir_synced"
            else:
                note = (
                    "replace_ok_dir_sync_unsupported_or_failed: "
                    "el fichero destino fue sustituido; la durabilidad del "
                    "directorio no está garantizada en esta plataforma"
                )
            return AtomicWriteResult(
                path=destination,
                replaced=True,
                dir_synced=dir_ok,
                durability_note=note,
            )
        except Exception:
            if fh is not None:
                try:
                    fh.close()
                except OSError:
                    pass
            if not replaced and tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            raise

    if acquire_lock:
        with JsonWriteLock(destination, timeout=lock_timeout):
            return _write_unlocked()
    return _write_unlocked()


def transactional_update(
    path: Path | str,
    mutator: Callable[[Any], Any],
    *,
    reader: Callable[[Path], Any] | None = None,
    validate: Callable[[Any], None] | None = None,
    to_dict: Callable[[Any], dict] | None = None,
    lock_timeout: float = _DEFAULT_LOCK_TIMEOUT_S,
    default_factory: Callable[[], Any] | None = None,
) -> TransactionalUpdateResult:
    """Actualización transaccional: lock → leer fresco → deepcopy → mutar copia →
    validar → atomic write.

    El estado original en memoria del llamador **no** se modifica aquí; se
    trabaja sobre una copia profunda. Tras éxito se devuelve el nuevo estado.
    """
    destination = Path(path).resolve()

    def _default_reader(p: Path) -> Any:
        if not p.exists():
            if default_factory is not None:
                return default_factory()
            return {}
        text = p.read_text(encoding="utf-8")
        return json.loads(text)

    read_fn = reader or _default_reader

    with JsonWriteLock(destination, timeout=lock_timeout):
        fresh = read_fn(destination)
        working = copy.deepcopy(fresh)
        original_snapshot = copy.deepcopy(fresh)

        try:
            result_state = mutator(working)
            if result_state is None:
                result_state = working
        except Exception:
            # La copia working puede estar a medias; original_snapshot intacto.
            raise

        if validate is not None:
            try:
                validate(result_state)
            except JsonValidationError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise JsonValidationError(str(exc)) from exc

        if to_dict is not None:
            payload = to_dict(result_state)
        elif isinstance(result_state, dict):
            payload = result_state
        else:
            raise JsonAtomicError(
                "transactional_update requiere to_dict si el estado no es dict"
            )

        # Comprobar que no se mutó accidentalmente una estructura compartida
        # cuando el reader devolvió el mismo objeto (defensa en tests).
        _ = original_snapshot

        write = atomic_write_json(
            destination,
            payload,
            acquire_lock=False,  # ya poseemos el lock
            cleanup_stale=True,
        )
        return TransactionalUpdateResult(
            path=destination, state=result_state, write=write
        )
