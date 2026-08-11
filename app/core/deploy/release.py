"""Construcción de carpeta de release Python administrada (sin .exe)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.core.deploy.config import DeployConfigError
from app.core.storage.demo_files import PROJECT_ROOT

# Árbol mínimo a copiar (código + plantillas). Sin datos/backups/logs/venv.
_INCLUDE_TOP = (
    "app",
    "deploy",
    "docs",
    "requirements.txt",
    "requirements-dev.txt",
    "run_tests.py",
    "run_browser_tests.py",
    "README.md",
    "PLAN.md",
    ".gitattributes",
)
_SKIP_DIR_NAMES = {
    "__pycache__",
    ".venv",
    "venv",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
}


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build_release_folder(destino: Path, *, overwrite: bool = False) -> Path:
    """Copia revisable del código aprobado a ``destino`` (sin .venv ni datos)."""
    dest = Path(destino).resolve()
    if dest.exists():
        if not overwrite:
            raise DeployConfigError(f"Destino de release ya existe: {dest}")
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    for name in _INCLUDE_TOP:
        src = PROJECT_ROOT / name
        if not src.exists():
            continue
        target = dest / name
        if src.is_dir():
            shutil.copytree(
                src,
                target,
                ignore=shutil.ignore_patterns(*_SKIP_DIR_NAMES, "*.pyc"),
            )
        else:
            shutil.copy2(src, target)

    # Demo de solo referencia (lectura); no siembra productiva
    demo_src = PROJECT_ROOT / "data" / "demo"
    if demo_src.is_dir():
        demo_dst = dest / "data" / "demo"
        demo_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(demo_src, demo_dst)

    # No copiar data/documentos ni exports productivos
    (dest / "data" / "documentos").mkdir(parents=True, exist_ok=True)
    (dest / "exports").mkdir(parents=True, exist_ok=True)
    (dest / "exports" / ".gitkeep").write_text("", encoding="utf-8")

    # Plantilla config
    example = PROJECT_ROOT / "deploy" / "config.example.env"
    if example.is_file():
        shutil.copy2(example, dest / "deploy" / "config.example.env")

    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "python": sys.version.split()[0],
        "requirements_sha256": _hash_file(PROJECT_ROOT / "requirements.txt"),
        "nota": (
            "Release Python administrada (estrategia C). "
            "Crear .venv e instalar requirements.txt en el equipo destino. "
            "Sin .exe. Instancia productiva fuera de esta carpeta."
        ),
        "dependency_lock": (
            "Brecha: no hay requirements.lock/pip-tools. "
            "Usar requirements.txt con versiones mínimas; "
            "documentar pip freeze tras piloto si se exige pin exacto."
        ),
    }
    (dest / "RELEASE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return dest


def _hash_file(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def simulate_code_rollback(app_a: Path, app_b: Path, *, active_link: Path) -> Path:
    """Simula rollback de código: active_link deja de apuntar a B y vuelve a A.

    ``active_link`` es un directorio «current» reemplazado por copia de A.
    No toca BM_INSTANCE_ROOT.
    """
    a, b, cur = Path(app_a).resolve(), Path(app_b).resolve(), Path(active_link).resolve()
    if not a.is_dir() or not b.is_dir():
        raise DeployConfigError("simulate_code_rollback requiere carpetas A y B.")
    if cur.exists():
        shutil.rmtree(cur)
    shutil.copytree(a, cur, ignore=shutil.ignore_patterns(*_SKIP_DIR_NAMES, "*.pyc"))
    return cur
