"""Copia de seguridad en ZIP (solo lectura de disco / serialización en memoria).

No modifica archivos originales ni implementa restauración.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.models import AppData
from app.core.storage.demo_files import DEMO_FILE, PROJECT_ROOT
from app.data.serializers import appdata_to_dict
from app.ui.theme import APP_NAME, APP_VERSION

# Metadatos de exportación (si existen); se copian tal cual desde disco.
_META_CANDIDATOS: tuple[Path, ...] = (
    PROJECT_ROOT / "exports" / "semanal" / "_meta_exportaciones.json",
    PROJECT_ROOT / "exports" / "historial_compras" / "_meta.json",
)


@dataclass(frozen=True)
class ResultadoBackup:
    contenido: bytes
    nombre_archivo: str
    archivos_incluidos: tuple[str, ...]


def _arcname_relativo(ruta: Path) -> str:
    try:
        return ruta.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return ruta.name


def generar_backup_zip(data: AppData) -> ResultadoBackup:
    """Genera un ZIP en memoria con JSON originales + manifiesto.

    - Copia bytes de archivos en disco sin transformarlos.
    - Añade `datos_hotel_sesion.json` con el estado actual en memoria
      (misma forma que el serializador de la app), sin escribir en disco.
    - Añade `manifest.json`.
    """
    ahora = datetime.now()
    incluidos: list[dict] = []
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        if DEMO_FILE.is_file():
            bruto = DEMO_FILE.read_bytes()
            nombre = _arcname_relativo(DEMO_FILE)
            zf.writestr(nombre, bruto)
            incluidos.append(
                {
                    "archivo": nombre,
                    "origen": "disco",
                    "bytes": len(bruto),
                }
            )

        # Estado actual en sesión (no toca el JSON de disco).
        sesion_nombre = "datos_hotel_sesion.json"
        sesion_bytes = json.dumps(
            appdata_to_dict(data),
            ensure_ascii=False,
            indent=2,
            default=str,
        ).encode("utf-8")
        zf.writestr(sesion_nombre, sesion_bytes)
        incluidos.append(
            {
                "archivo": sesion_nombre,
                "origen": "sesion_memoria",
                "bytes": len(sesion_bytes),
            }
        )

        for meta_path in _META_CANDIDATOS:
            if not meta_path.is_file():
                continue
            bruto = meta_path.read_bytes()
            nombre = _arcname_relativo(meta_path)
            zf.writestr(nombre, bruto)
            incluidos.append(
                {
                    "archivo": nombre,
                    "origen": "disco",
                    "bytes": len(bruto),
                }
            )

        manifest = {
            "fecha": ahora.isoformat(timespec="seconds"),
            "aplicacion": APP_NAME,
            "version": APP_VERSION,
            "origen": "backup_ui",
            "nota": (
                "Copia de seguridad. No incluye restauración automática. "
                "Los JSON de disco se copiaron sin transformar. "
                "datos_hotel_sesion.json refleja AppData en memoria al generar el ZIP."
            ),
            "archivos": incluidos,
        }
        manifest_bytes = json.dumps(
            manifest, ensure_ascii=False, indent=2
        ).encode("utf-8")
        zf.writestr("manifest.json", manifest_bytes)
        incluidos_nombres = [item["archivo"] for item in incluidos] + ["manifest.json"]

    nombre_zip = f"bm_backup_{ahora.strftime('%Y%m%d_%H%M%S')}.zip"
    return ResultadoBackup(
        contenido=buffer.getvalue(),
        nombre_archivo=nombre_zip,
        archivos_incluidos=tuple(incluidos_nombres),
    )
