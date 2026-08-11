"""Configuración de despliegue local (variables BM_*).

Perfiles:
- ``dev`` (default): comportamiento histórico; ``BM_DEMO_FILE`` opcional.
- ``hotel``: exige datos productivos fuera del demo canónico; sin fallback silencioso.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.core.storage.demo_files import DEMO_DIR, DEMO_FILE, PROJECT_ROOT

PROFILE_DEV = "dev"
PROFILE_HOTEL = "hotel"
_VALID_PROFILES = frozenset({PROFILE_DEV, PROFILE_HOTEL})

ENV_PROFILE = "BM_DEPLOY_PROFILE"
ENV_INSTANCE_ROOT = "BM_INSTANCE_ROOT"
ENV_DEMO_FILE = "BM_DEMO_FILE"
ENV_ALLOW_OPS = "BM_DEPLOY_ALLOW_OPS"
ENV_FLET_VIEW = "BM_FLET_VIEW"
ENV_SKIP_WEEKLY = "BM_SKIP_WEEKLY_EXPORT"
ENV_CONFIG_FILE = "BM_DEPLOY_CONFIG"


class DeployConfigError(ValueError):
    """Configuración de despliegue inválida o incompleta."""


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


def _expand(raw: str) -> str:
    return os.path.expandvars(os.path.expanduser(raw.strip()))


def load_env_file(path: Path) -> dict[str, str]:
    """Lee ``KEY=VALUE`` simples (sin secretos obligatorios). No ejecuta shell."""
    out: dict[str, str] = {}
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            raise DeployConfigError(f"Línea inválida en {path}: {s!r}")
        key, _, val = s.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if not key:
            raise DeployConfigError(f"Clave vacía en {path}")
        out[key] = val
    return out


def apply_env_file(path: Path, *, override: bool = False) -> dict[str, str]:
    """Aplica un fichero env al proceso. Por defecto no pisa variables ya definidas."""
    loaded = load_env_file(path)
    for key, val in loaded.items():
        if override or key not in os.environ or os.environ.get(key, "") == "":
            os.environ[key] = _expand(val)
    return loaded


@dataclass(frozen=True)
class DeployConfig:
    profile: str
    project_root: Path
    instance_root: Path | None
    data_file: Path
    backups_dir: Path
    logs_dir: Path
    exports_dir: Path
    documentos_dir: Path
    demo_file: Path
    allow_ops: bool
    flet_view: str
    skip_weekly_export: bool
    temp_dir: Path | None = None

    @property
    def is_hotel(self) -> bool:
        return self.profile == PROFILE_HOTEL

    def data_file_is_demo(self) -> bool:
        try:
            return self.data_file.resolve() == DEMO_FILE.resolve()
        except OSError:
            return False


def _resolve_profile() -> str:
    raw = (os.environ.get(ENV_PROFILE) or PROFILE_DEV).strip().lower()
    if raw not in _VALID_PROFILES:
        raise DeployConfigError(
            f"{ENV_PROFILE} inválido: {raw!r}. Use {PROFILE_DEV} o {PROFILE_HOTEL}."
        )
    return raw


def _resolve_instance_root() -> Path | None:
    raw = (os.environ.get(ENV_INSTANCE_ROOT) or "").strip()
    if not raw:
        return None
    return Path(_expand(raw)).resolve()


def _forbid_demo_as_prod(path: Path) -> None:
    resolved = path.resolve()
    if resolved == DEMO_FILE.resolve():
        raise DeployConfigError(
            "Perfil hotel: el JSON productivo no puede ser el demo canónico "
            f"({DEMO_FILE}). Defina {ENV_DEMO_FILE} o {ENV_INSTANCE_ROOT}."
        )
    try:
        resolved.relative_to(DEMO_DIR.resolve())
    except ValueError:
        return
    raise DeployConfigError(
        "Perfil hotel: el JSON productivo no puede residir bajo data/demo/. "
        f"Ruta rechazada: {resolved}"
    )


def resolve_data_file(profile: str, instance_root: Path | None) -> Path:
    """Resuelve el JSON efectivo sin caer en el demo en perfil hotel."""
    env_raw = (os.environ.get(ENV_DEMO_FILE) or "").strip()
    if env_raw:
        path = Path(_expand(env_raw)).resolve()
    elif instance_root is not None:
        path = (instance_root / "data" / "datos_hotel.json").resolve()
        os.environ[ENV_DEMO_FILE] = str(path)
    elif profile == PROFILE_HOTEL:
        raise DeployConfigError(
            f"Perfil hotel exige {ENV_DEMO_FILE} o {ENV_INSTANCE_ROOT}. "
            "No se usa el demo como almacén productivo."
        )
    else:
        path = DEMO_FILE.resolve()

    if profile == PROFILE_HOTEL:
        _forbid_demo_as_prod(path)
    return path


def load_deploy_config(*, apply_config_file: bool = True) -> DeployConfig:
    """Carga y valida la configuración de despliegue del proceso actual."""
    if apply_config_file:
        cfg_path = (os.environ.get(ENV_CONFIG_FILE) or "").strip()
        if cfg_path:
            p = Path(_expand(cfg_path))
            if not p.is_file():
                raise DeployConfigError(f"No existe {ENV_CONFIG_FILE}={p}")
            apply_env_file(p)
        else:
            default_cfg = PROJECT_ROOT / "deploy" / "config.env"
            if default_cfg.is_file():
                apply_env_file(default_cfg)

    profile = _resolve_profile()
    instance_root = _resolve_instance_root()
    data_file = resolve_data_file(profile, instance_root)

    if instance_root is not None:
        backups = instance_root / "backups"
        logs = instance_root / "logs"
        exports = instance_root / "exports"
        documentos = instance_root / "data" / "documentos"
        temp = instance_root / "temp"
    else:
        # Dev / sin instancia: carpetas locales revisables bajo deploy/local (no Git).
        local = PROJECT_ROOT / "deploy" / "local"
        backups = local / "backups"
        logs = local / "logs"
        exports = PROJECT_ROOT / "exports"
        documentos = PROJECT_ROOT / "data" / "documentos"
        temp = local / "temp"

    if profile == PROFILE_HOTEL and instance_root is None:
        # BM_DEMO_FILE puede apuntar fuera; adjuntos/exports aún exigen instancia.
        raise DeployConfigError(
            f"Perfil hotel exige {ENV_INSTANCE_ROOT} para externalizar "
            "adjuntos, exports, backups y logs."
        )

    return DeployConfig(
        profile=profile,
        project_root=PROJECT_ROOT.resolve(),
        instance_root=instance_root,
        data_file=data_file,
        backups_dir=backups.resolve(),
        logs_dir=logs.resolve(),
        exports_dir=exports.resolve(),
        documentos_dir=documentos.resolve(),
        demo_file=DEMO_FILE.resolve(),
        allow_ops=_truthy(os.environ.get(ENV_ALLOW_OPS)),
        flet_view=(os.environ.get(ENV_FLET_VIEW) or "desktop").strip().lower() or "desktop",
        skip_weekly_export=_truthy(os.environ.get(ENV_SKIP_WEEKLY)),
        temp_dir=temp.resolve(),
    )


def ensure_instance_dirs(cfg: DeployConfig) -> None:
    """Crea carpetas de instancia con errores claros si faltan permisos."""
    targets = [
        cfg.backups_dir,
        cfg.logs_dir,
        cfg.data_file.parent,
        cfg.exports_dir,
        cfg.documentos_dir,
    ]
    if cfg.temp_dir is not None:
        targets.append(cfg.temp_dir)
    if cfg.instance_root is not None:
        targets.append(cfg.instance_root)
        targets.append(cfg.instance_root / "data")
    for d in targets:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DeployConfigError(
                f"No se pudo crear o acceder a la carpeta {d}: {exc}"
            ) from exc
    # Comprobar escritura mínima
    probe = cfg.logs_dir / ".bm_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise DeployConfigError(
            f"Permiso de escritura insuficiente en {cfg.logs_dir}: {exc}"
        ) from exc
    if cfg.is_hotel:
        # Guard: no usar mutables del repo
        repo_docs = (PROJECT_ROOT / "data" / "documentos").resolve()
        repo_exports = (PROJECT_ROOT / "exports").resolve()
        if cfg.documentos_dir.resolve() == repo_docs:
            raise DeployConfigError(
                "Perfil hotel: documentos_dir no puede ser el del repositorio."
            )
        if cfg.exports_dir.resolve() == repo_exports:
            raise DeployConfigError(
                "Perfil hotel: exports_dir no puede ser el del repositorio."
            )


def assert_hotel_data_ready(cfg: DeployConfig, *, require_exists: bool) -> None:
    if not cfg.is_hotel:
        return
    if cfg.data_file_is_demo():
        raise DeployConfigError("Perfil hotel apunta al demo canónico.")
    parent = cfg.data_file.parent
    if not parent.is_dir():
        raise DeployConfigError(
            f"Falta la carpeta de datos productivos: {parent}. "
            "Ejecute prepare antes de arrancar."
        )
    if require_exists and not cfg.data_file.is_file():
        raise DeployConfigError(
            f"Falta el JSON productivo: {cfg.data_file}. "
            "Ejecute prepare o restaure un backup."
        )
