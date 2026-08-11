"""Operaciones de backup/restore/diagnóstico para scripts de despliegue.

Reutiliza backup schema v2 y restore canónicos. Requiere
``BM_DEPLOY_ALLOW_OPS=1`` (solo scripts controlados; sin sesión Streamlit).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from app.core.deploy.config import DeployConfig, DeployConfigError
from app.core.services import backup_service as bak
from app.core.services import restore_backup_service as rst
from app.core.storage.demo_files import DEMO_FILE, get_demo_file, set_demo_file_override
from app.core.storage.json_atomic import atomic_write_json
from app.data.mock_data import crear_datos_mock
from app.data.serializers import appdata_to_dict, dict_to_appdata, load_json

_log = logging.getLogger("bm.deploy.ops")


def _require_ops(cfg: DeployConfig) -> None:
    if not cfg.allow_ops:
        raise DeployConfigError(
            "Operación ops denegada: defina BM_DEPLOY_ALLOW_OPS=1 solo en scripts "
            "de despliegue controlados."
        )
    if cfg.is_hotel and cfg.data_file_is_demo():
        raise DeployConfigError("Ops hotel no puede apuntar al demo canónico.")


def seed_productive_if_missing(cfg: DeployConfig) -> Path:
    """Crea JSON productivo inicial desde mock (nunca copia el demo canónico)."""
    if cfg.data_file_is_demo():
        raise DeployConfigError("No se puede sembrar sobre el demo canónico.")
    cfg.data_file.parent.mkdir(parents=True, exist_ok=True)
    if cfg.data_file.is_file():
        return cfg.data_file
    data = crear_datos_mock()
    atomic_write_json(cfg.data_file, appdata_to_dict(data))
    _log.info("seeded_productive path=%s", cfg.data_file)
    return cfg.data_file


def create_ops_backup(cfg: DeployConfig) -> Path:
    """Genera ZIP schema v2 en ``cfg.backups_dir`` con manifiesto verificable."""
    _require_ops(cfg)
    cfg.backups_dir.mkdir(parents=True, exist_ok=True)
    set_demo_file_override(cfg.data_file)
    try:
        if not cfg.data_file.is_file():
            raise DeployConfigError(f"No existe JSON productivo: {cfg.data_file}")
        data = dict_to_appdata(load_json(cfg.data_file))
        result = bak.generar_backup_zip(data, kind="ops", include_disk_snapshot=True)
        dest = cfg.backups_dir / result.nombre_archivo
        # Escritura atómica del ZIP
        tmp = dest.with_suffix(dest.suffix + f".tmp.{os.getpid()}")
        tmp.write_bytes(result.contenido)
        os.replace(str(tmp), str(dest))
        sidecar = dest.with_suffix(dest.suffix + ".sha256")
        sidecar.write_text(
            f"{result.sha256_zip}  {dest.name}\n", encoding="utf-8"
        )
        meta = {
            "archivo": dest.name,
            "sha256_zip": result.sha256_zip,
            "schema_version": result.schema_version,
            "data_file": str(cfg.data_file),
            "archivos_incluidos": list(result.archivos_incluidos),
        }
        dest.with_suffix(dest.suffix + ".meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        _log.info(
            "backup_ok file=%s sha256=%s",
            dest.name,
            result.sha256_zip[:12],
        )
        return dest
    finally:
        set_demo_file_override(None)


def verify_ops_backup(cfg: DeployConfig, zip_path: Path) -> rst.InspeccionBackup:
    _require_ops(cfg)
    path = Path(zip_path)
    if not path.is_file():
        raise DeployConfigError(f"Backup no encontrado: {path}")
    contenido = path.read_bytes()
    insp = rst.inspeccionar_backup(contenido, nombre=path.name)
    if not insp.ok:
        _log.error("backup_verify_fail msg=%s", insp.mensaje)
        raise DeployConfigError(f"Backup inválido: {insp.mensaje}")
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if sidecar.is_file():
        expected = sidecar.read_text(encoding="utf-8").split()[0].strip()
        actual = bak.sha256_bytes(contenido)
        if expected != actual:
            raise DeployConfigError(
                f"SHA-256 del ZIP no coincide (sidecar={expected[:12]}… "
                f"actual={actual[:12]}…)."
            )
    _log.info("backup_verify_ok file=%s", path.name)
    return insp


def restore_ops_backup(
    cfg: DeployConfig,
    zip_path: Path,
    *,
    confirm: str,
) -> rst.ResultadoRestauracion:
    """Restore controlado con confirmación explícita y preventivo canónico."""
    _require_ops(cfg)
    if confirm.strip().upper() != "RESTORE":
        raise DeployConfigError(
            "Restore cancelado: pase --confirm RESTORE para confirmar explícitamente."
        )
    if cfg.data_file_is_demo() or cfg.data_file.resolve() == DEMO_FILE.resolve():
        raise DeployConfigError("Restore ops rechazado: destino es el demo canónico.")

    path = Path(zip_path)
    contenido = path.read_bytes()
    verify_ops_backup(cfg, path)

    set_demo_file_override(cfg.data_file)
    os.environ["BM_DEMO_FILE"] = str(cfg.data_file.resolve())
    try:
        result = rst.restaurar_desde_bytes(
            contenido,
            nombre_backup=path.name,
            destino_json=cfg.data_file,
            project_root=cfg.project_root,
            recargar_sesion=False,
        )
        if not result.ok:
            raise DeployConfigError(
                f"Restore fallido ({result.estado}): {result.mensaje}"
            )
        _log.info(
            "restore_ok backup=%s preventivo=%s",
            path.name,
            result.backup_preventivo,
        )
        return result
    finally:
        set_demo_file_override(None)


def assert_not_demo_path(path: Path) -> None:
    if path.resolve() == DEMO_FILE.resolve():
        raise DeployConfigError(f"Operación prohibida sobre demo: {path}")
    if get_demo_file().resolve() == DEMO_FILE.resolve() and path.resolve() == DEMO_FILE.resolve():
        raise DeployConfigError("get_demo_file() apunta al demo canónico en ops hotel.")
