"""Restauración segura de backups schema v2 (Fase C2).

Flujo: inspeccionar → preflight → backup preventivo → aplicar en staging →
sustituir destinos autorizados. JSON + adjuntos **no** son una transacción
atómica conjunta; el orden es adjuntos staged → JSON atómico; ante fallo se
intenta recuperar desde el ZIP pre_restore.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.core.services.backup_service import (
    APPDATA_ARCNAME,
    DOCUMENTOS_PREFIX,
    MANIFEST_NAME,
    SCHEMA_VERSION,
    generar_backup_zip,
    sha256_bytes,
)
from app.core.storage.demo_files import DEMO_FILE, PROJECT_ROOT, get_demo_file
from app.core.storage.json_atomic import atomic_write_json
from app.data.serializers import dict_to_appdata, load_json
from app.data.mock_data import crear_datos_mock

RESTORE_OK = "ok"
RESTORE_RECHAZADO = "rechazado"
RESTORE_FALLIDO_SIN_CAMBIOS = "fallido_sin_cambios"
RESTORE_FALLIDO_RECUPERADO = "fallido_recuperado"
RESTORE_INCIERTO = "incierto"

_ALLOWED_PREFIXES = (
    APPDATA_ARCNAME,
    "datos_hotel_sesion.json",
    MANIFEST_NAME,
    DOCUMENTOS_PREFIX,
    "data/demo/",
    "disk_snapshot/",
    "exports/",
)


@dataclass
class InspeccionBackup:
    ok: bool
    mensaje: str
    schema_version: int | None = None
    fecha: str | None = None
    version_app: str | None = None
    kind: str | None = None
    archivos: list[dict] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    appdata_arcname: str | None = None


@dataclass
class ResultadoRestauracion:
    ok: bool
    estado: str
    mensaje: str
    operacion_id: str
    backup_nombre: str | None = None
    fecha: str | None = None
    version_detectada: str | None = None
    archivos_validados: list[str] = field(default_factory=list)
    archivos_restaurados: list[str] = field(default_factory=list)
    backup_preventivo: str | None = None
    advertencias: list[str] = field(default_factory=list)
    error: str | None = None


def _isolation_activa() -> bool:
    flag = os.environ.get("BM_TEST_ISOLATION", "").strip().lower()
    return flag in ("1", "true", "yes")


def destino_es_demo_protegido(destino: Path | None = None) -> bool:
    """True si escribir en ``destino`` violaría la protección del demo canónico."""
    target = (destino or get_demo_file()).resolve()
    if target == DEMO_FILE.resolve() and _isolation_activa():
        return True
    return False


def _zip_safe_member(name: str) -> bool:
    if not name or name.endswith("/"):
        return True  # dirs ok to skip
    n = name.replace("\\", "/")
    if n.startswith("/") or (len(n) > 1 and n[1] == ":"):
        return False
    parts = Path(n).parts
    if any(p == ".." for p in parts):
        return False
    if n == MANIFEST_NAME or n == APPDATA_ARCNAME or n == "datos_hotel_sesion.json":
        return True
    return any(n.startswith(p) for p in _ALLOWED_PREFIXES if p.endswith("/")) or n in (
        APPDATA_ARCNAME,
        "datos_hotel_sesion.json",
        MANIFEST_NAME,
    )


def _leer_manifest(zf: zipfile.ZipFile) -> dict:
    try:
        raw = zf.read(MANIFEST_NAME)
    except KeyError as exc:
        raise ValueError("Falta manifest.json en el backup.") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("manifest.json corrupto o no es JSON.") from exc


def inspeccionar_backup(
    contenido: bytes,
    *,
    nombre: str = "backup.zip",
) -> InspeccionBackup:
    """Lee y valida el ZIP sin restaurar."""
    advertencias: list[str] = []
    try:
        if not contenido:
            return InspeccionBackup(False, "Backup vacío.")
        with zipfile.ZipFile(io.BytesIO(contenido)) as zf:
            if zf.testzip() is not None:
                return InspeccionBackup(False, "ZIP corrupto (testzip).")
            # Symlinks / absolute via ZipInfo
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if not _zip_safe_member(name):
                    return InspeccionBackup(
                        False,
                        f"Entrada peligrosa o no permitida: {name}",
                    )
                # External attr: Unix symlink bit (rarely set on Windows zips)
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    return InspeccionBackup(False, f"Enlace simbólico rechazado: {name}")

            try:
                manifest = _leer_manifest(zf)
            except ValueError as exc:
                return InspeccionBackup(False, str(exc))

            schema = manifest.get("schema_version")
            if schema != SCHEMA_VERSION:
                return InspeccionBackup(
                    False,
                    f"Versión de esquema incompatible: {schema!r} "
                    f"(se requiere {SCHEMA_VERSION}). "
                    "Los backups legacy sin hashes no son restaurables.",
                )

            archivos = list(manifest.get("archivos") or [])
            if not archivos:
                return InspeccionBackup(False, "Manifiesto sin lista de archivos.")

            names_in_zip = {i.filename.replace("\\", "/") for i in zf.infolist()}
            for item in archivos:
                arc = (item.get("archivo") or "").replace("\\", "/")
                expected = item.get("sha256")
                if not arc or not expected:
                    return InspeccionBackup(
                        False, f"Entrada de manifiesto incompleta: {arc or '?'}"
                    )
                if not _zip_safe_member(arc):
                    return InspeccionBackup(False, f"Ruta no permitida en manifiesto: {arc}")
                if arc not in names_in_zip:
                    return InspeccionBackup(False, f"Archivo obligatorio ausente: {arc}")
                bruto = zf.read(arc)
                if len(bruto) != int(item.get("bytes", -1)):
                    return InspeccionBackup(
                        False, f"Tamaño incorrecto para {arc}"
                    )
                if sha256_bytes(bruto) != expected:
                    return InspeccionBackup(
                        False, f"Hash SHA-256 incorrecto para {arc}"
                    )

            appdata_name = None
            if APPDATA_ARCNAME in names_in_zip:
                appdata_name = APPDATA_ARCNAME
            elif "datos_hotel_sesion.json" in names_in_zip:
                appdata_name = "datos_hotel_sesion.json"
                advertencias.append(
                    "Usando datos_hotel_sesion.json (sin appdata.json)."
                )
            else:
                return InspeccionBackup(
                    False, f"Falta payload canónico ({APPDATA_ARCNAME})."
                )

            # Validar carga AppData
            payload = json.loads(zf.read(appdata_name).decode("utf-8"))
            data = dict_to_appdata(payload)
            # Referencias a adjuntos
            for arch in getattr(data, "archivos_documentales", []) or []:
                if not getattr(arch, "activo", True):
                    continue
                rel = (arch.ruta_relativa or "").replace("\\", "/").lstrip("/")
                if not rel:
                    continue
                if not rel.startswith(DOCUMENTOS_PREFIX):
                    advertencias.append(
                        f"Adjunto fuera de data/documentos/ omitido en check: {rel}"
                    )
                    continue
                if rel not in names_in_zip:
                    return InspeccionBackup(
                        False,
                        f"Referencia a adjunto inexistente en el backup: {rel}",
                    )

            return InspeccionBackup(
                True,
                "Backup válido.",
                schema_version=int(schema),
                fecha=manifest.get("fecha"),
                version_app=manifest.get("version"),
                kind=manifest.get("kind") or manifest.get("origen"),
                archivos=archivos,
                advertencias=advertencias,
                appdata_arcname=appdata_name,
            )
    except zipfile.BadZipFile:
        return InspeccionBackup(False, "No es un ZIP válido.")
    except Exception as exc:  # noqa: BLE001
        return InspeccionBackup(False, f"Inspección fallida: {exc}")


def _dir_backups_preventivos(destino_json: Path) -> Path:
    return destino_json.parent / "backups" / "pre_restore"


def _aplicar_adjuntos(
    zf: zipfile.ZipFile,
    *,
    root: Path,
    miembros: list[str],
) -> list[str]:
    """Escribe adjuntos bajo root/data/documentos. Devuelve rutas relativas."""
    restaurados: list[str] = []
    docs_root = (root / "data" / "documentos").resolve()
    docs_root.mkdir(parents=True, exist_ok=True)
    for name in miembros:
        if not name.startswith(DOCUMENTOS_PREFIX):
            continue
        target = (root / name).resolve()
        try:
            target.relative_to(docs_root)
        except ValueError as exc:
            raise RuntimeError(f"Adjunto fuera de destino autorizado: {name}") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        # Escribir a temp y replace
        tmp = target.with_suffix(target.suffix + f".restore_tmp.{os.getpid()}")
        tmp.write_bytes(zf.read(name))
        os.replace(str(tmp), str(target))
        restaurados.append(name)
    return restaurados


def restaurar_desde_bytes(
    contenido: bytes,
    *,
    nombre_backup: str = "backup.zip",
    destino_json: Path | None = None,
    project_root: Path | None = None,
    recargar_sesion: bool = False,
) -> ResultadoRestauracion:
    """Restaura un backup validado sobre el almacén activo (o override de test)."""
    op_id = str(uuid.uuid4())
    dest = (destino_json or get_demo_file()).resolve()
    root = (project_root or PROJECT_ROOT).resolve()
    ahora = datetime.now().isoformat(timespec="seconds")

    if destino_es_demo_protegido(dest):
        return ResultadoRestauracion(
            False,
            RESTORE_RECHAZADO,
            "Destino demo protegido: restauración abortada.",
            op_id,
            backup_nombre=nombre_backup,
            fecha=ahora,
            error="demo_protegido",
        )

    insp = inspeccionar_backup(contenido, nombre=nombre_backup)
    if not insp.ok:
        return ResultadoRestauracion(
            False,
            RESTORE_RECHAZADO,
            insp.mensaje,
            op_id,
            backup_nombre=nombre_backup,
            fecha=ahora,
            advertencias=list(insp.advertencias),
            error=insp.mensaje,
        )

    validados = [a.get("archivo", "") for a in insp.archivos]
    staging: Path | None = None
    prerestore_path: Path | None = None
    tocados_adjuntos = False

    try:
        # Cargar estado actual para pre_restore
        from app.core.storage.demo_files import load_demo_files

        if dest.is_file():
            try:
                current = dict_to_appdata(load_json(dest))
            except Exception:  # noqa: BLE001
                current = crear_datos_mock()
        else:
            try:
                current = load_demo_files()
            except Exception:  # noqa: BLE001
                current = crear_datos_mock()

        pre = generar_backup_zip(current, kind="pre_restore", include_disk_snapshot=True)
        pre_dir = _dir_backups_preventivos(dest)
        pre_dir.mkdir(parents=True, exist_ok=True)
        prerestore_path = pre_dir / f"{op_id}_{pre.nombre_archivo}"
        prerestore_path.write_bytes(pre.contenido)
        # Validar preventivo
        pre_insp = inspeccionar_backup(pre.contenido, nombre=pre.nombre_archivo)
        if not pre_insp.ok:
            return ResultadoRestauracion(
                False,
                RESTORE_FALLIDO_SIN_CAMBIOS,
                f"No se pudo validar el backup preventivo: {pre_insp.mensaje}",
                op_id,
                backup_nombre=nombre_backup,
                fecha=ahora,
                archivos_validados=validados,
                error=pre_insp.mensaje,
            )

        staging = Path(tempfile.mkdtemp(prefix=f"bm_restore_{op_id}_"))
        with zipfile.ZipFile(io.BytesIO(contenido)) as zf:
            app_name = insp.appdata_arcname or APPDATA_ARCNAME
            payload = json.loads(zf.read(app_name).decode("utf-8"))
            # Revalidar carga
            dict_to_appdata(payload)
            staged_json = staging / "appdata.json"
            staged_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

            # Aplicar adjuntos primero
            adj_names = [
                a["archivo"]
                for a in insp.archivos
                if str(a.get("archivo", "")).startswith(DOCUMENTOS_PREFIX)
            ]
            if adj_names:
                tocados_adjuntos = True
                restaurados_adj = _aplicar_adjuntos(zf, root=root, miembros=adj_names)
            else:
                restaurados_adj = []

            # JSON atómico al destino
            try:
                atomic_write_json(dest, payload)
            except Exception as exc:
                # Intentar recuperar JSON desde preventivo
                recuperado = False
                try:
                    with zipfile.ZipFile(prerestore_path) as pz:
                        pre_payload = json.loads(
                            pz.read(APPDATA_ARCNAME).decode("utf-8")
                        )
                    atomic_write_json(dest, pre_payload)
                    recuperado = True
                except Exception:  # noqa: BLE001
                    recuperado = False
                estado = (
                    RESTORE_FALLIDO_RECUPERADO
                    if recuperado
                    else RESTORE_INCIERTO
                )
                return ResultadoRestauracion(
                    False,
                    estado,
                    f"Fallo al escribir JSON: {exc}",
                    op_id,
                    backup_nombre=nombre_backup,
                    fecha=ahora,
                    version_detectada=insp.version_app,
                    archivos_validados=validados,
                    archivos_restaurados=restaurados_adj,
                    backup_preventivo=str(prerestore_path.name),
                    advertencias=list(insp.advertencias),
                    error=str(exc),
                )

        if recargar_sesion:
            try:
                from app.core.storage.session_store import reload_from_disk

                reload_from_disk()
            except Exception:  # noqa: BLE001
                pass

        return ResultadoRestauracion(
            True,
            RESTORE_OK,
            "Restauración completada.",
            op_id,
            backup_nombre=nombre_backup,
            fecha=ahora,
            version_detectada=insp.version_app,
            archivos_validados=validados,
            archivos_restaurados=[APPDATA_ARCNAME] + restaurados_adj,
            backup_preventivo=str(prerestore_path.name) if prerestore_path else None,
            advertencias=list(insp.advertencias)
            + (
                [
                    "JSON y adjuntos no son una transacción atómica conjunta; "
                    "se aplicaron adjuntos y después el JSON."
                ]
                if tocados_adjuntos
                else []
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return ResultadoRestauracion(
            False,
            RESTORE_FALLIDO_SIN_CAMBIOS
            if not tocados_adjuntos
            else RESTORE_INCIERTO,
            f"Restauración fallida: {exc}",
            op_id,
            backup_nombre=nombre_backup,
            fecha=ahora,
            archivos_validados=validados,
            backup_preventivo=prerestore_path.name if prerestore_path else None,
            error=str(exc),
        )
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
