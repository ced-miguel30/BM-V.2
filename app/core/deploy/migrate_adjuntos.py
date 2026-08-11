"""Migración opcional de adjuntos repo → instancia (solo preview/copia)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.core.deploy.config import DeployConfig, DeployConfigError
from app.core.storage.demo_files import PROJECT_ROOT


@dataclass(frozen=True)
class MigracionAdjuntoItem:
    rel: str
    origen: Path
    destino: Path
    existe_destino: bool


def plan_migracion_adjuntos(cfg: DeployConfig) -> list[MigracionAdjuntoItem]:
    """Lista copias repo→instancia sin borrar origen. No toca el demo."""
    if not cfg.is_hotel or cfg.instance_root is None:
        raise DeployConfigError("migrate-adjuntos requiere perfil hotel e instancia.")
    origen_root = (PROJECT_ROOT / "data" / "documentos").resolve()
    destino_root = cfg.documentos_dir.resolve()
    if not origen_root.is_dir():
        return []
    items: list[MigracionAdjuntoItem] = []
    for path in origen_root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(origen_root).as_posix()
        dest = (destino_root / rel).resolve()
        try:
            dest.relative_to(destino_root)
        except ValueError:
            continue
        items.append(
            MigracionAdjuntoItem(
                rel=f"data/documentos/{rel}",
                origen=path,
                destino=dest,
                existe_destino=dest.is_file(),
            )
        )
    return items


def ejecutar_migracion_adjuntos(
    cfg: DeployConfig,
    *,
    apply: bool,
) -> list[MigracionAdjuntoItem]:
    """Si apply=False solo preview. Si apply=True copia (no borra origen)."""
    plan = plan_migracion_adjuntos(cfg)
    if not apply:
        return plan
    for item in plan:
        if item.existe_destino:
            continue
        item.destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item.origen, item.destino)
    return plan
