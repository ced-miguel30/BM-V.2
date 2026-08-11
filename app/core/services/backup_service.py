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
from app.data.serializers import appdata_to_dict
from app.ui.theme import APP_NAME, APP_VERSION

SCHEMA_VERSION = 2
APPDATA_ARCNAME = "appdata.json"
MANIFEST_NAME = "manifest.json"
DOCUMENTOS_PREFIX = "data/documentos/"

_META_CANDIDATOS: tuple[Path, ...] = (
    PROJECT_ROOT / "exports" / "semanal" / "_meta_exportaciones.json",
    PROJECT_ROOT / "exports" / "historial_compras" / "_meta.json",
)


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
    """Adjuntos en disco referenciados por AppData (solo bajo data/documentos/)."""
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
        abs_path = (PROJECT_ROOT / rel).resolve()
        try:
            abs_path.relative_to((PROJECT_ROOT / "data" / "documentos").resolve())
        except ValueError:
            continue
        if not abs_path.is_file():
            continue
        if abs_path.is_symlink():
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
) -> ResultadoBackup:
    """Genera un ZIP restaurable (schema v2) en memoria."""
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
                # Nombre estable relativo al proyecto cuando es el demo canónico
                if disk.resolve() == DEMO_FILE.resolve():
                    nombre = _arcname_relativo(DEMO_FILE)
                else:
                    nombre = f"disk_snapshot/{disk.name}"
                zf.writestr(nombre, bruto)
                incluidos.append(_entry(nombre, "disco", bruto))

        for rel, _path, bruto in _adjuntos_referenciados(data):
            zf.writestr(rel, bruto)
            incluidos.append(_entry(rel, "adjunto", bruto))

        for meta_path in _META_CANDIDATOS:
            if not meta_path.is_file() or meta_path.is_symlink():
                continue
            try:
                nombre = meta_path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
            except ValueError:
                continue
            if ".." in Path(nombre).parts:
                continue
            bruto = meta_path.read_bytes()
            zf.writestr(nombre, bruto)
            incluidos.append(_entry(nombre, "disco", bruto))

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "fecha": ahora.isoformat(timespec="seconds"),
            "aplicacion": APP_NAME,
            "version": APP_VERSION,
            "origen": "backup_ui" if kind == "manual" else kind,
            "kind": kind,
            "nota": (
                "Backup restaurable schema v2. "
                "Restaurar solo mediante restore_backup_service. "
                f"Payload canónico: {APPDATA_ARCNAME}."
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
