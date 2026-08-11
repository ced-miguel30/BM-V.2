"""Copia de seguridad ZIP restaurable (schema v2) y helpers compartidos.

Schema v2 añade SHA-256 por archivo, ``schema_version``, adjuntos bajo
``data/documentos/`` y payload canónico ``appdata.json``.

Los ZIP legacy (sin ``schema_version`` / sin hashes) **no** se consideran
restaurables con garantías de integridad.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.models import AppData
from app.core.storage.demo_files import DEMO_FILE, PROJECT_ROOT, get_demo_file
from app.core.storage.instance_paths import (
    DOCUMENTOS_PREFIX,
    resolve_adjunto_path,
)
from app.data.serializers import appdata_to_dict
from app.ui.theme import APP_NAME, APP_VERSION

SCHEMA_VERSION = 2
APPDATA_ARCNAME = "appdata.json"
MANIFEST_NAME = "manifest.json"

# Política P2: los exports son regenerables → NO se incluyen en el backup
# canónico por defecto (opción B). Solo JSON + adjuntos + manifiesto.
INCLUDE_EXPORTS_IN_BACKUP_DEFAULT = False


@dataclass(frozen=True)
class ResultadoBackup:
    contenido: bytes
    nombre_archivo: str
    archivos_incluidos: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    sha256_zip: str = ""


def sha256_bytes(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def _arcname_relativo(ruta: Path) -> str:
    try:
        return ruta.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return ruta.name


def _entry(archivo: str, origen: str, bruto: bytes) -> dict:
    return {
        "archivo": archivo,
        "origen": origen,
        "bytes": len(bruto),
        "sha256": sha256_bytes(bruto),
    }


def _adjuntos_referenciados(data: AppData) -> list[tuple[str, Path, bytes]]:
    """Adjuntos en disco referenciados por AppData (prefijo lógico data/documentos/)."""
    out: list[tuple[str, Path, bytes]] = []
    vistos: set[str] = set()
    for arch in getattr(data, "archivos_documentales", []) or []:
        rel = (getattr(arch, "ruta_relativa", None) or "").replace("\\", "/").lstrip("/")
        if not rel or rel in vistos:
            continue
        if not rel.startswith(DOCUMENTOS_PREFIX):
            continue
        if ".." in Path(rel).parts:
            continue
        abs_path: Path | None = None
        try:
            candidate = resolve_adjunto_path(rel, for_write=False)
            if candidate.is_file() and not candidate.is_symlink():
                abs_path = candidate
        except Exception:  # noqa: BLE001
            abs_path = None
        if abs_path is None:
            # Compat: tests que parchean PROJECT_ROOT de este módulo
            candidate = (PROJECT_ROOT / rel).resolve()
            try:
                candidate.relative_to((PROJECT_ROOT / "data" / "documentos").resolve())
            except ValueError:
                continue
            if candidate.is_file() and not candidate.is_symlink():
                abs_path = candidate
        if abs_path is None:
            continue
        bruto = abs_path.read_bytes()
        vistos.add(rel)
        out.append((rel, abs_path, bruto))
    return out


def _ops_backup_permitido() -> bool:
    import os

    flag = os.environ.get("BM_DEPLOY_ALLOW_OPS", "").strip().lower()
    return flag in ("1", "true", "yes", "on")


def generar_backup_zip(
    data: AppData,
    *,
    kind: str = "manual",
    include_disk_snapshot: bool = True,
    include_exports: bool = INCLUDE_EXPORTS_IN_BACKUP_DEFAULT,
) -> ResultadoBackup:
    """Genera un ZIP restaurable (schema v2) en memoria.

    Por defecto **no** incluye exports (regenerables). Incluye JSON (memoria +
    snapshot opcional) y adjuntos referenciados bajo ``data/documentos/``.
    """
    # Preventivos C2/C3: el caso de uso padre ya autorizó; no re-exigir export.
    # kind=ops: solo scripts de despliegue con BM_DEPLOY_ALLOW_OPS=1.
    if kind not in ("pre_restore", "pre_reset", "ops"):
        from app.core.auth.permissions import Permiso
        from app.core.auth.usecase_guard import require_usecase

        require_usecase(Permiso.EXPORTAR_BACKUP)
    elif kind == "ops" and not _ops_backup_permitido():
        raise PermissionError(
            "Backup ops requiere BM_DEPLOY_ALLOW_OPS=1 (scripts de despliegue)."
        )

    ahora = datetime.now()
    incluidos: list[dict] = []
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Payload canónico para restauración (estado en memoria).
        appdata_bytes = json.dumps(
            appdata_to_dict(data),
            ensure_ascii=False,
            indent=2,
            default=str,
        ).encode("utf-8")
        zf.writestr(APPDATA_ARCNAME, appdata_bytes)
        incluidos.append(_entry(APPDATA_ARCNAME, "sesion_memoria", appdata_bytes))

        # Compat: también como datos_hotel_sesion.json
        sesion_nombre = "datos_hotel_sesion.json"
        zf.writestr(sesion_nombre, appdata_bytes)
        incluidos.append(_entry(sesion_nombre, "sesion_memoria", appdata_bytes))

        if include_disk_snapshot:
            disk = get_demo_file()
            if disk.is_file() and not disk.is_symlink():
                bruto = disk.read_bytes()
                if disk.resolve() == DEMO_FILE.resolve():
                    nombre = _arcname_relativo(DEMO_FILE)
                else:
                    nombre = f"disk_snapshot/{disk.name}"
                zf.writestr(nombre, bruto)
                incluidos.append(_entry(nombre, "disco", bruto))

        for rel, _path, bruto in _adjuntos_referenciados(data):
            zf.writestr(rel, bruto)
            incluidos.append(_entry(rel, "adjunto", bruto))

        if include_exports:
            # Opt-in explícito: metas bajo exports de la raíz de exports efectiva.
            from app.core.storage.instance_paths import get_exports_root

            exports_root = get_exports_root(for_write=False)
            for meta_path in (
                exports_root / "semanal" / "_meta_exportaciones.json",
                exports_root / "historial_compras" / "_meta.json",
            ):
                if not meta_path.is_file() or meta_path.is_symlink():
                    continue
                try:
                    nombre = meta_path.resolve().relative_to(exports_root.resolve()).as_posix()
                    nombre = f"exports/{nombre}"
                except ValueError:
                    continue
                if ".." in Path(nombre).parts:
                    continue
                bruto = meta_path.read_bytes()
                zf.writestr(nombre, bruto)
                incluidos.append(_entry(nombre, "export_meta", bruto))

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "fecha": ahora.isoformat(timespec="seconds"),
            "aplicacion": APP_NAME,
            "version": APP_VERSION,
            "origen": "backup_ui" if kind == "manual" else kind,
            "kind": kind,
            "include_exports": bool(include_exports),
            "nota": (
                "Backup restaurable schema v2. "
                "Restaurar solo mediante restore_backup_service. "
                f"Payload canónico: {APPDATA_ARCNAME}. "
                "Exports excluidos por defecto (regenerables)."
            ),
            "archivos": incluidos,
        }
        manifest_bytes = json.dumps(
            manifest, ensure_ascii=False, indent=2
        ).encode("utf-8")
        zf.writestr(MANIFEST_NAME, manifest_bytes)

    contenido = buffer.getvalue()
    nombres = tuple([item["archivo"] for item in incluidos] + [MANIFEST_NAME])
    prefijo = "bm_prerestore" if kind == "pre_restore" else "bm_backup"
    nombre_zip = f"{prefijo}_{ahora.strftime('%Y%m%d_%H%M%S')}.zip"
    return ResultadoBackup(
        contenido=contenido,
        nombre_archivo=nombre_zip,
        archivos_incluidos=nombres,
        schema_version=SCHEMA_VERSION,
        sha256_zip=sha256_bytes(contenido),
    )
