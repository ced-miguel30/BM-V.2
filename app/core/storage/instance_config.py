"""Configuración de cliente para raíz compartida multi-PC.

El fichero de cliente guarda **solo** la ruta ``shared_root`` (nunca copias
de datos). Los datos viven bajo la instancia compartida
(``shared_root/data/datos_hotel.json``, backups/, etc.).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.core.storage.demo_files import DEMO_FILE

ENV_INSTANCE_ROOT = "BM_INSTANCE_ROOT"
ENV_DEMO_FILE = "BM_DEMO_FILE"
ENV_SHARED_ROOT = "BM_SHARED_ROOT"

DATA_FILE_NAME = "datos_hotel.json"


class InstanceConfigError(ValueError):
    """Configuración de instancia compartida inválida."""


def client_config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "BM-V2-client"
    return Path.home() / ".bm-v2-client"


def client_config_path() -> Path:
    return client_config_dir() / "config.json"


def load_client_config() -> dict[str, Any]:
    path = client_config_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    shared = raw.get("shared_root")
    if isinstance(shared, str) and shared.strip():
        out["shared_root"] = shared.strip()
    return out


def save_client_config(*, shared_root: str | Path) -> Path:
    """Persiste solo ``shared_root`` (sin datos de hotel)."""
    root = str(Path(shared_root))
    cfg_dir = client_config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = client_config_path()
    payload = {"shared_root": root}
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    # Escritura atómica local del config de cliente
    fd, tmp_name = tempfile.mkstemp(prefix="bm_client_", suffix=".json", dir=str(cfg_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return path


def validate_shared_root(path: Path | str) -> Path:
    """Probe R/W bajo la raíz compartida; crea subdirs mínimas si hacen falta."""
    root = Path(path).expanduser()
    try:
        root = root.resolve()
    except OSError as exc:
        raise InstanceConfigError(f"shared_root no resoluble: {exc}") from exc

    try:
        root.mkdir(parents=True, exist_ok=True)
        data_dir = root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / f".bm_shared_root_probe.{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise InstanceConfigError(
            f"shared_root no usable (R/W): {root} ({exc})"
        ) from exc
    return root


def resolve_data_file_from_shared_root(shared_root: Path | str) -> Path:
    return Path(shared_root) / "data" / DATA_FILE_NAME


def resolve_shared_root() -> Path | None:
    """Precedencia de la raíz de instancia compartida.

    1. ``BM_INSTANCE_ROOT``
    2. ``BM_SHARED_ROOT`` (raíz de instancia; ``BM_DEMO_FILE`` puede
       seguir apuntando al JSON exacto en tests)
    3. ``shared_root`` del config de cliente
    4. ``None`` → default vía ``get_demo_file()`` / demo del repo
    """
    inst = (os.environ.get(ENV_INSTANCE_ROOT) or "").strip()
    if inst:
        return Path(os.path.expandvars(os.path.expanduser(inst))).resolve()

    shared = (os.environ.get(ENV_SHARED_ROOT) or "").strip()
    if shared:
        return Path(os.path.expandvars(os.path.expanduser(shared))).resolve()

    cfg = load_client_config()
    cfg_root = cfg.get("shared_root")
    if isinstance(cfg_root, str) and cfg_root.strip():
        return Path(
            os.path.expandvars(os.path.expanduser(cfg_root.strip()))
        ).resolve()

    return None


def _default_local_instance_root() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "BM-V2-local"
    return Path.home() / "BM-V2-local"


def _is_default_local_instance(root: Path | str) -> bool:
    try:
        return Path(root).expanduser().resolve() == _default_local_instance_root().resolve()
    except OSError:
        return False


def bootstrap_client_shared_root() -> Path | None:
    """Aplica al arranque el ``shared_root`` guardado en este PC (BM-V2-client).

    Cada ordenador guarda su propia config en ``%LOCALAPPDATA%\\BM-V2-client\\config.json``.
    La ruta final (p. ej. ``D:\\Jose Manuel\\...\\2-BM-DATOS`` o UNC) puede ser la misma
    en todos; lo que cambia es el usuario/PC donde vive el config.

    El runtime hook del exe fija por defecto ``BM-V2-local``; si hay ``shared_root``
    de cliente, lo pisa (salvo ``BM_SHARED_ROOT`` explícito o un
    ``BM_INSTANCE_ROOT`` que ya no sea el default local).
    """
    forced_shared = (os.environ.get(ENV_SHARED_ROOT) or "").strip()
    if forced_shared:
        return apply_shared_root(forced_shared)

    cfg = load_client_config()
    shared = cfg.get("shared_root")
    if not isinstance(shared, str) or not shared.strip():
        return None

    current = (os.environ.get(ENV_INSTANCE_ROOT) or "").strip()
    if current:
        try:
            cur = Path(os.path.expandvars(os.path.expanduser(current)))
            want = Path(os.path.expandvars(os.path.expanduser(shared.strip())))
            if cur.resolve() == want.resolve():
                return apply_shared_root(want)
        except OSError:
            pass
        if not _is_default_local_instance(current):
            # Atajo / soporte ya apuntó a otra carpeta: no pisar.
            return None

    return apply_shared_root(shared.strip())


def apply_shared_root(path: Path | str) -> Path:
    """Valida y fija env de proceso a la instancia compartida.

    Establece ``BM_INSTANCE_ROOT`` y ``BM_DEMO_FILE`` →
    ``shared/data/datos_hotel.json``. Rechaza el path demo canónico
    como producción.
    """
    root = validate_shared_root(path)
    data_file = resolve_data_file_from_shared_root(root).resolve()
    demo_resolved = DEMO_FILE.resolve()
    if data_file == demo_resolved or root.resolve() == DEMO_FILE.parent.resolve():
        raise InstanceConfigError(
            "No se admite el path demo canónico (data/demo) como shared_root "
            "de producción."
        )

    os.environ[ENV_INSTANCE_ROOT] = str(root)
    os.environ[ENV_DEMO_FILE] = str(data_file)
    # Perfil hotel: adjuntos bajo shared_root/data/documentos
    os.environ.setdefault("BM_DEPLOY_PROFILE", "hotel")
    if (os.environ.get("BM_DEPLOY_PROFILE") or "").strip().lower() != "hotel":
        os.environ["BM_DEPLOY_PROFILE"] = "hotel"
    (root / "data" / "documentos").mkdir(parents=True, exist_ok=True)
    (root / "backups").mkdir(parents=True, exist_ok=True)
    # Limpia override in-process si existiera, para que get_demo_file vea el env
    from app.core.storage.demo_files import set_demo_file_override
    from app.core.storage.instance_paths import set_documentos_root_override

    set_demo_file_override(None)
    set_documentos_root_override(None)
    return root
