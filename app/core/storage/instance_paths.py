"""Rutas de instancia productivas vs árbol del repositorio.

Perfil ``hotel``: mutables bajo ``BM_INSTANCE_ROOT``.
Perfil ``dev`` (default): conserva rutas históricas bajo ``PROJECT_ROOT``.

Las referencias persistidas de adjuntos son **lógicas**
(``data/documentos/...``), nunca paths absolutos personales.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.core.storage.demo_files import DEMO_DIR, DEMO_FILE, PROJECT_ROOT

DOCUMENTOS_PREFIX = "data/documentos/"
PROFILE_DEV = "dev"
PROFILE_HOTEL = "hotel"

ENV_PROFILE = "BM_DEPLOY_PROFILE"
ENV_INSTANCE_ROOT = "BM_INSTANCE_ROOT"


class InstancePathError(ValueError):
    """Ruta de instancia inválida, traversal o escritura prohibida."""


def deploy_profile() -> str:
    raw = (os.environ.get(ENV_PROFILE) or PROFILE_DEV).strip().lower()
    return raw if raw in (PROFILE_DEV, PROFILE_HOTEL) else PROFILE_DEV


def is_hotel_profile() -> bool:
    return deploy_profile() == PROFILE_HOTEL


def _expand(raw: str) -> str:
    return os.path.expandvars(os.path.expanduser(raw.strip()))


def instance_root() -> Path | None:
    raw = (os.environ.get(ENV_INSTANCE_ROOT) or "").strip()
    if not raw:
        return None
    return Path(_expand(raw)).resolve()


def require_instance_root_hotel() -> Path:
    root = instance_root()
    if is_hotel_profile() and root is None:
        raise InstancePathError(
            f"Perfil hotel exige {ENV_INSTANCE_ROOT} para adjuntos/exports."
        )
    if root is None:
        raise InstancePathError("BM_INSTANCE_ROOT no definido.")
    return root


_documentos_root_override: Path | None = None


def set_documentos_root_override(path: Path | str | None) -> None:
    """Override de tests: ``base_dir`` actúa como raíz física de documentos."""
    global _documentos_root_override
    if path is None:
        _documentos_root_override = None
    else:
        _documentos_root_override = Path(path).resolve()


def get_documentos_root(*, for_write: bool = False) -> Path:
    """Raíz física de adjuntos (sin el prefijo lógico data/documentos)."""
    if _documentos_root_override is not None:
        return _documentos_root_override
    if is_hotel_profile():
        root = require_instance_root_hotel() / "data" / "documentos"
        if for_write:
            _assert_not_repo_mutable(root)
        return root
    return (PROJECT_ROOT / "data" / "documentos").resolve()


def get_exports_root(*, for_write: bool = False) -> Path:
    if is_hotel_profile():
        root = require_instance_root_hotel() / "exports"
        if for_write:
            _assert_not_repo_mutable(root)
        return root
    return (PROJECT_ROOT / "exports").resolve()


def get_backups_root() -> Path:
    if is_hotel_profile():
        return require_instance_root_hotel() / "backups"
    local = PROJECT_ROOT / "deploy" / "local" / "backups"
    return local.resolve()


def get_logs_root() -> Path:
    if is_hotel_profile():
        return require_instance_root_hotel() / "logs"
    return (PROJECT_ROOT / "deploy" / "local" / "logs").resolve()


def get_temp_root() -> Path:
    if is_hotel_profile():
        return require_instance_root_hotel() / "temp"
    return (PROJECT_ROOT / "deploy" / "local" / "temp").resolve()


def normalize_documentos_rel(ruta: str) -> str:
    """Normaliza referencia lógica; rechaza absolutos y traversal."""
    raw = (ruta or "").replace("\\", "/").strip()
    if not raw:
        raise InstancePathError("ruta_relativa vacía.")
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        raise InstancePathError(
            "No se permiten paths absolutos en referencias de adjuntos."
        )
    parts = Path(raw).parts
    if any(p == ".." for p in parts):
        raise InstancePathError(f"Path traversal rechazado: {ruta!r}")
    rel = raw.lstrip("/")
    if not rel.startswith(DOCUMENTOS_PREFIX):
        # Compat: IDs sueltos o claves A6 bajo documentos/
        if rel.startswith("documentos/"):
            rel = "data/" + rel
        elif "/" not in rel:
            rel = DOCUMENTOS_PREFIX + rel
        else:
            # p.ej. adoc1/x.pdf histórico en tests
            rel = DOCUMENTOS_PREFIX + rel.lstrip("/")
    if not rel.startswith(DOCUMENTOS_PREFIX):
        raise InstancePathError(
            f"Adjunto fuera de {DOCUMENTOS_PREFIX}: {ruta!r}"
        )
    return rel


def logical_documentos_rel(arch_id: str, nombre: str) -> str:
    safe_id = Path(arch_id).name
    safe_name = Path(nombre).name
    if not safe_id or safe_id in {".", ".."} or ".." in safe_id:
        raise InstancePathError("arch_id inválido.")
    if not safe_name or safe_name in {".", ".."}:
        raise InstancePathError("nombre de archivo inválido.")
    return f"{DOCUMENTOS_PREFIX}{safe_id}/{safe_name}"


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _assert_not_repo_mutable(path: Path) -> None:
    """En hotel, ninguna escritura productiva bajo mutables del clon."""
    if not is_hotel_profile():
        return
    repo = PROJECT_ROOT.resolve()
    target = path.resolve()
    if target == DEMO_FILE.resolve() or _under(target, DEMO_DIR.resolve()):
        raise InstancePathError("Escritura sobre demo prohibida.")
    inst = instance_root()
    repo_docs = (repo / "data" / "documentos").resolve()
    repo_exports = (repo / "exports").resolve()
    if _under(target, repo_docs):
        if inst is None or not _under(target, (inst / "data" / "documentos").resolve()):
            raise InstancePathError(
                "Perfil hotel: no escribir en data/documentos del repositorio."
            )
    if _under(target, repo_exports):
        if inst is None or not _under(target, (inst / "exports").resolve()):
            raise InstancePathError(
                "Perfil hotel: no escribir en exports/ del repositorio."
            )


def resolve_adjunto_path(
    ruta_relativa: str,
    *,
    for_write: bool = False,
) -> Path:
    """Resuelve físicamente una referencia lógica de adjunto.

    Lectura (hotel): instancia primero; si falta, compatibilidad con
    ``PROJECT_ROOT/data/documentos/...`` (histórico), sin migrar.
    Escritura (hotel): solo instancia.
    Tests: ``set_documentos_root_override`` redefine la raíz física.
    """
    rel = normalize_documentos_rel(ruta_relativa)
    suffix = rel[len(DOCUMENTOS_PREFIX) :]
    docs_root = get_documentos_root(for_write=for_write)
    path = (docs_root / suffix).resolve()
    if not _under(path, docs_root):
        raise InstancePathError(f"Path traversal rechazado: {ruta_relativa!r}")

    if for_write:
        _assert_not_repo_mutable(path)
        return path

    if path.is_file():
        return path

    # Compat lectura histórica (solo si no hay override de tests)
    if (
        _documentos_root_override is None
        and is_hotel_profile()
        and instance_root() is not None
    ):
        legacy = (PROJECT_ROOT / rel).resolve()
        legacy_root = (PROJECT_ROOT / "data" / "documentos").resolve()
        if _under(legacy, legacy_root) and legacy.is_file():
            return legacy
    return path


def assert_hotel_not_writing_repo_exports(path: Path) -> None:
    if not is_hotel_profile():
        return
    repo_exports = (PROJECT_ROOT / "exports").resolve()
    target = path.resolve()
    if _under(target, repo_exports):
        inst = instance_root()
        if inst is None or not _under(target, (inst / "exports").resolve()):
            raise InstancePathError(
                f"Perfil hotel: exports productivos deben ir bajo la instancia, no {target}."
            )


def storage_roots_for_backup() -> tuple[Path, ...]:
    """Raíces físicas donde buscar bytes de adjuntos para backup."""
    roots: list[Path] = []
    if is_hotel_profile() and instance_root() is not None:
        roots.append((instance_root() / "data" / "documentos").resolve())
    roots.append((PROJECT_ROOT / "data" / "documentos").resolve())
    # únicos preservando orden
    seen: set[Path] = set()
    out: list[Path] = []
    for r in roots:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return tuple(out)
