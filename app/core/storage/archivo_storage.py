"""Almacenamiento local de adjuntos con staging y compensación (A6 / Plan v3 §5).

No declara atomicidad conjunta JSON+binario. Publicación binaria y commit JSON
son pasos separados; si el JSON falla tras publicar, se compensan los binarios
de la transacción.
"""

from __future__ import annotations

import os
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

ALLOWED_EXTENSIONS = frozenset({
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff",
    ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt",
})
MAX_BYTES_DEFAULT = 25 * 1024 * 1024
_STAGING_MARKER = ".staging."
_ORPHAN_AGE_S = 3600.0


class ArchivoStorageError(RuntimeError):
    """Error de almacenamiento de adjuntos."""


class ArchivoValidationError(ArchivoStorageError, ValueError):
    """Validación de nombre, extensión, tamaño o path."""


@dataclass
class StagingHandle:
    storage_key: str
    staging_path: Path
    final_path: Path
    sha256: str
    tamanio_bytes: int
    nombre_original_seguro: str
    mime_type: str


@dataclass
class PublishBatch:
    """Binarios publicados en una operación pendiente de commit JSON."""

    published_keys: list[str] = field(default_factory=list)
    published_paths: list[Path] = field(default_factory=list)


def generar_storage_key() -> str:
    """Identidad lógica estable; no deriva del nombre de usuario."""
    return secrets.token_hex(16)


def sanitizar_nombre_original(nombre: str) -> str:
    base = Path(nombre or "archivo").name  # elimina path traversal
    if base in {"", ".", ".."} or ".." in base:
        raise ArchivoValidationError("Nombre de archivo no permitido.")
    base = re.sub(r"[^\w.\- ()áéíóúÁÉÍÓÚñÑ]+", "_", base, flags=re.UNICODE)
    base = base.strip(" ._") or "archivo"
    return base[:180]


def validar_adjunto(
    nombre_original: str,
    contenido: bytes,
    *,
    max_bytes: int = MAX_BYTES_DEFAULT,
    allowed_extensions: frozenset[str] = ALLOWED_EXTENSIONS,
) -> str:
    if not contenido:
        raise ArchivoValidationError("El archivo está vacío.")
    if len(contenido) > max_bytes:
        raise ArchivoValidationError(
            f"El archivo supera el límite de {max_bytes // (1024 * 1024)} MiB."
        )
    seguro = sanitizar_nombre_original(nombre_original)
    ext = Path(seguro).suffix.lower()
    if ext not in allowed_extensions:
        raise ArchivoValidationError(f"Extensión no permitida: {ext or '(sin extensión)'}")
    return seguro


def _fsync_file(path: Path) -> None:
    with open(path, "rb") as fh:
        try:
            os.fsync(fh.fileno())
        except (OSError, AttributeError):
            pass


class LocalArchivoStorage:
    """Storage bajo un directorio raíz (tests: TemporaryDirectory)."""

    def __init__(self, root: Path | str, *, max_bytes: int = MAX_BYTES_DEFAULT) -> None:
        self.root = Path(root).resolve()
        self.max_bytes = max_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for_key(self, storage_key: str) -> Path:
        key = (storage_key or "").strip()
        if not key or "/" in key or "\\" in key or ".." in key or key.startswith("."):
            raise ArchivoValidationError("storage_key inválida.")
        dest = (self.root / key).resolve()
        if not str(dest).startswith(str(self.root)):
            raise ArchivoValidationError("Path traversal bloqueado.")
        return dest

    def stage(
        self,
        contenido: bytes,
        nombre_original: str,
        *,
        mime_type: str | None = None,
        storage_key: str | None = None,
    ) -> StagingHandle:
        import hashlib
        import mimetypes

        seguro = validar_adjunto(
            nombre_original, contenido, max_bytes=self.max_bytes
        )
        key = storage_key or generar_storage_key()
        final = self.path_for_key(key)
        if final.exists():
            raise ArchivoStorageError(f"Destino ya existe para key {key}")
        staging = final.parent / f"{final.name}{_STAGING_MARKER}{os.getpid()}.{secrets.token_hex(4)}"
        staging.parent.mkdir(parents=True, exist_ok=True)
        staging.write_bytes(contenido)
        _fsync_file(staging)
        digest = hashlib.sha256(contenido).hexdigest()
        if hashlib.sha256(staging.read_bytes()).hexdigest() != digest:
            staging.unlink(missing_ok=True)
            raise ArchivoStorageError("Integridad SHA-256 fallida en staging.")
        mime = mime_type
        if not mime or "/" not in mime:
            mime = mimetypes.guess_type(seguro)[0] or "application/octet-stream"
        return StagingHandle(
            storage_key=key,
            staging_path=staging,
            final_path=final,
            sha256=digest,
            tamanio_bytes=len(contenido),
            nombre_original_seguro=seguro,
            mime_type=mime,
        )

    def publish(self, handle: StagingHandle) -> Path:
        if not handle.staging_path.exists():
            raise ArchivoStorageError("Staging ausente; no se puede publicar.")
        if handle.final_path.exists():
            handle.staging_path.unlink(missing_ok=True)
            raise ArchivoStorageError("Destino final ya existe.")
        os.replace(str(handle.staging_path), str(handle.final_path))
        return handle.final_path

    def rollback_published(self, batch: PublishBatch) -> list[str]:
        """Compensa binarios publicados si el commit JSON no llegó a hacerse.

        No borra si el path ya no existe. Devuelve keys compensadas.
        """
        done: list[str] = []
        for key, path in zip(batch.published_keys, batch.published_paths):
            try:
                p = Path(path)
                if p.exists() and p.is_file():
                    p.unlink()
                    done.append(key)
            except OSError:
                continue
        batch.published_keys.clear()
        batch.published_paths.clear()
        return done

    def discard_staging(self, handle: StagingHandle) -> None:
        handle.staging_path.unlink(missing_ok=True)

    def publish_batch(self, handles: list[StagingHandle]) -> PublishBatch:
        batch = PublishBatch()
        try:
            for h in handles:
                self.publish(h)
                batch.published_keys.append(h.storage_key)
                batch.published_paths.append(h.final_path)
            return batch
        except Exception:
            self.rollback_published(batch)
            for h in handles:
                self.discard_staging(h)
            raise

    def list_orphan_files(
        self,
        referenced_keys: set[str],
        *,
        min_age_s: float = _ORPHAN_AGE_S,
        now: float | None = None,
    ) -> list[Path]:
        """Ficheros en root no referenciados y no staging recientes."""
        clock = now if now is not None else time.time()
        orphans: list[Path] = []
        if not self.root.exists():
            return orphans
        for p in self.root.iterdir():
            if not p.is_file():
                continue
            name = p.name
            if _STAGING_MARKER in name:
                continue
            if name in referenced_keys:
                continue
            try:
                age = clock - p.stat().st_mtime
            except OSError:
                continue
            if age >= min_age_s:
                orphans.append(p)
        return orphans

    def cleanup_orphans(
        self,
        referenced_keys: set[str],
        *,
        min_age_s: float = _ORPHAN_AGE_S,
    ) -> list[str]:
        removed: list[str] = []
        for p in self.list_orphan_files(referenced_keys, min_age_s=min_age_s):
            try:
                p.unlink()
                removed.append(p.name)
            except OSError:
                continue
        return removed

    def cleanup_stale_staging(self, *, min_age_s: float = _ORPHAN_AGE_S) -> int:
        n = 0
        now = time.time()
        if not self.root.exists():
            return 0
        for p in self.root.iterdir():
            if p.is_file() and _STAGING_MARKER in p.name:
                try:
                    if now - p.stat().st_mtime >= min_age_s:
                        p.unlink()
                        n += 1
                except OSError:
                    continue
        return n
