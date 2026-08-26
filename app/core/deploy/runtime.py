"""Arranque runtime de despliegue (perfil hotel / candado escritor)."""

from __future__ import annotations

import atexit
import logging
import os

from app.core.deploy.config import (
    DeployConfig,
    assert_hotel_data_ready,
    ensure_instance_dirs,
    load_deploy_config,
)
from app.core.deploy.writer_lock import (
    WriterLockError,
    acquire_writer_lock,
    assert_no_foreign_writer,
    lock_path_for,
    read_lock,
    release_writer_lock,
)

_log = logging.getLogger("bm.deploy")
_atexit_registered = False


def _register_release(cfg: DeployConfig, role: str) -> None:
    global _atexit_registered

    def _cleanup() -> None:
        try:
            release_writer_lock(cfg, role=role, only_own=True)
        except WriterLockError:
            pass

    if not _atexit_registered:
        atexit.register(_cleanup)
        _atexit_registered = True


def _parent_holds_lock(cfg: DeployConfig) -> bool:
    """True si el CLI padre ya sostiene el candado (hijo no debe re-adquirir)."""
    if (os.environ.get("BM_DEPLOY_WRITER_HELD") or "").strip() != "1":
        return False
    try:
        parent_pid = int(os.environ.get("BM_DEPLOY_WRITER_PID") or "0")
    except ValueError:
        return False
    info = read_lock(lock_path_for(cfg.data_file))
    return info is not None and info.pid == parent_pid


def prepare_runtime(
    *,
    role: str,
    acquire_lock: bool = True,
    require_data_file: bool = True,
) -> DeployConfig:
    """Valida perfil y, en hotel, adquiere el candado de escritor único.

    En ``dev`` es casi no-op (solo carga config). No altera el demo.
    Antes de cargar el perfil hotel, reaplica ``shared_root`` del config de
    cliente de este PC (si existe), para no quedarse en BM-V2-local vacío.
    """
    from app.core.storage.instance_config import (
        InstanceConfigError,
        bootstrap_client_shared_root,
    )

    try:
        applied = bootstrap_client_shared_root()
        if applied is not None:
            _log.info("client_shared_root_applied root=%s", applied)
    except InstanceConfigError:
        raise
    except Exception as exc:  # noqa: BLE001
        _log.warning("bootstrap_client_shared_root: %s", exc)

    cfg = load_deploy_config()
    if not cfg.is_hotel:
        return cfg

    ensure_instance_dirs(cfg)
    assert_hotel_data_ready(cfg, require_exists=require_data_file)

    if acquire_lock:
        if _parent_holds_lock(cfg):
            _log.info(
                "writer_lock_inherited role=%s data=%s",
                role,
                cfg.data_file,
            )
            return cfg
        assert_no_foreign_writer(cfg, role=role)
        acquire_writer_lock(cfg, role=role)
        _register_release(cfg, role)
        _log.info(
            "writer_lock_acquired role=%s data=%s",
            role,
            cfg.data_file,
        )
    return cfg


def diagnose_lines(cfg: DeployConfig) -> list[str]:
    from app.ui.theme import APP_VERSION
    import platform
    import sys

    lines = [
        f"app_version={APP_VERSION}",
        f"python={sys.version.split()[0]}",
        f"platform={platform.platform()}",
        f"profile={cfg.profile}",
        f"project_root={cfg.project_root}",
        f"instance_root={cfg.instance_root}",
        f"data_file={cfg.data_file}",
        f"data_exists={cfg.data_file.is_file()}",
        f"data_is_demo={cfg.data_file_is_demo()}",
        f"backups_dir={cfg.backups_dir}",
        f"logs_dir={cfg.logs_dir}",
        f"documentos_dir={cfg.documentos_dir}",
        f"exports_dir={cfg.exports_dir}",
        f"demo_file={cfg.demo_file}",
        f"allow_ops={cfg.allow_ops}",
        f"flet_view={cfg.flet_view}",
    ]
    return lines
