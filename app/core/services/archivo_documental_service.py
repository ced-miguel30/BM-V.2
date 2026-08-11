"""Almacenamiento de archivos documentales (Fase 9).

- Escribe el original una sola vez.
- Calcula SHA-256.
- No modifica ni sobrescribe el fichero existente.
- Sin OCR ni extracción de datos.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.application.context import AppContext
from app.core.application.id_generator import next_id
from app.core.models import AppData, ArchivoDocumental
from app.core.storage.instance_paths import (
    get_documentos_root,
    logical_documentos_rel,
    resolve_adjunto_path,
)
from app.core.storage.session_store import get_data, persist_data

MAX_BYTES = 25 * 1024 * 1024  # 25 MiB


@dataclass
class ResultadoArchivo:
    ok: bool
    mensaje: str
    archivo: ArchivoDocumental | None = None


class _CompatSessionUow:
    def get_data(self) -> AppData:
        return get_data()

    def commit(self, data: AppData | None = None) -> AppData:
        return persist_data(data if data is not None else get_data())


def _ctx(ctx: AppContext | None = None) -> AppContext:
    if ctx is not None:
        return ctx
    from app.core.application.actor import actor_desde_appdata
    from app.core.application.clock import SystemClock

    uow = _CompatSessionUow()
    return AppContext(
        uow=uow,
        actor=actor_desde_appdata(uow.get_data()),
        clock=SystemClock(),
    )


def _registrar_actividad(ctx: AppContext, accion: str, detalle: str) -> None:
    from app.core.application.auditoria import registrar_actividad

    registrar_actividad(ctx, accion, detalle, commit=False)


def sha256_bytes(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def _sanitizar_nombre(nombre: str) -> str:
    base = Path(nombre or "archivo").name
    base = re.sub(r"[^\w.\- ()áéíóúÁÉÍÓÚñÑ]+", "_", base, flags=re.UNICODE)
    base = base.strip(" ._") or "archivo"
    return base[:180]


def _mime(nombre: str, mime_hint: str | None) -> str:
    if mime_hint and "/" in mime_hint:
        return mime_hint.strip()
    guess, _ = mimetypes.guess_type(nombre)
    return guess or "application/octet-stream"


def ruta_absoluta(archivo: ArchivoDocumental) -> Path:
    """Resuelve el path físico (instancia en hotel; compat lectura histórica)."""
    return resolve_adjunto_path(archivo.ruta_relativa, for_write=False)


def listar_archivos(
    ctx: AppContext | None = None, *, solo_activos: bool = True
) -> list[ArchivoDocumental]:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)

    data = _ctx(ctx).uow.get_data()
    items = list(getattr(data, "archivos_documentales", []) or [])
    if solo_activos:
        items = [a for a in items if a.activo]
    return sorted(
        items,
        key=lambda a: a.creado_en or datetime.min,
        reverse=True,
    )


def buscar_por_id(
    data: AppData, archivo_id: str
) -> ArchivoDocumental | None:
    return next(
        (
            a
            for a in getattr(data, "archivos_documentales", []) or []
            if a.id == archivo_id
        ),
        None,
    )


def registrar_archivo(
    contenido: bytes,
    nombre_original: str,
    *,
    mime_type: str | None = None,
    documento_id: str | None = None,
    notas: str | None = None,
    ctx: AppContext | None = None,
    base_dir: Path | None = None,
) -> ResultadoArchivo:
    """Persiste bytes en disco (una sola escritura) y metadatos en AppData."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)
    if denied:
        return ResultadoArchivo(False, denied)

    c = _ctx(ctx)
    data = c.uow.get_data()
    if not hasattr(data, "archivos_documentales") or data.archivos_documentales is None:
        data.archivos_documentales = []

    if not contenido:
        return ResultadoArchivo(False, "El archivo está vacío.")
    if len(contenido) > MAX_BYTES:
        return ResultadoArchivo(
            False, f"El archivo supera el límite de {MAX_BYTES // (1024 * 1024)} MiB."
        )

    nombre = _sanitizar_nombre(nombre_original)
    digest = sha256_bytes(contenido)
    # Deduplicación informativa: mismo hash ya registrado y activo.
    for existente in data.archivos_documentales:
        if existente.activo and existente.sha256 == digest:
            return ResultadoArchivo(
                False,
                f"Ya existe un archivo activo con el mismo SHA-256 ({existente.id}).",
                archivo=existente,
            )

    arch_id = next_id("adoc", [a.id for a in data.archivos_documentales])
    root = Path(base_dir) if base_dir is not None else get_documentos_root(for_write=True)
    carpeta = root / arch_id
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / nombre
    if destino.exists():
        return ResultadoArchivo(
            False, "Conflicto: el destino ya existe (inmutabilidad)."
        )

    # Escritura: temp + replace cuando es posible
    tmp = destino.with_suffix(destino.suffix + f".tmp.{os.getpid()}")
    try:
        tmp.write_bytes(contenido)
        os.replace(str(tmp), str(destino))
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        return ResultadoArchivo(False, f"No se pudo escribir el adjunto: {exc}")
    # Verificar integridad inmediata
    leido = destino.read_bytes()
    if sha256_bytes(leido) != digest:
        destino.unlink(missing_ok=True)
        return ResultadoArchivo(False, "Fallo de verificación SHA-256 tras escribir.")

    rel = logical_documentos_rel(arch_id, nombre)

    creado = c.clock.now() if getattr(c, "clock", None) else datetime.now()
    actor_id = getattr(getattr(c, "actor", None), "id", None)

    meta = ArchivoDocumental(
        id=arch_id,
        nombre_original=nombre,
        mime_type=_mime(nombre, mime_type),
        tamanio_bytes=len(contenido),
        sha256=digest,
        ruta_relativa=rel,
        usuario_id=actor_id,
        creado_en=creado,
        documento_id=documento_id,
        notas=(notas or "").strip() or None,
        activo=True,
    )
    data.archivos_documentales.append(meta)
    _registrar_actividad(
        c,
        "Registrar archivo documental",
        f"{arch_id} · {nombre} · sha256={digest[:12]}…",
    )
    c.uow.commit(data)
    return ResultadoArchivo(True, f"Archivo «{nombre}» registrado ({arch_id}).", meta)


def verificar_integridad(
    archivo_id: str, *, ctx: AppContext | None = None
) -> ResultadoArchivo:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)
    if denied:
        return ResultadoArchivo(False, denied)

    c = _ctx(ctx)
    data = c.uow.get_data()
    arch = buscar_por_id(data, archivo_id)
    if arch is None:
        return ResultadoArchivo(False, "Archivo no encontrado.")
    path = ruta_absoluta(arch)
    if not path.is_file():
        return ResultadoArchivo(False, f"Fichero ausente en disco: {arch.ruta_relativa}", arch)
    actual = sha256_bytes(path.read_bytes())
    if actual != arch.sha256:
        return ResultadoArchivo(
            False,
            f"Integridad rota: esperado {arch.sha256}, obtenido {actual}.",
            arch,
        )
    return ResultadoArchivo(True, "Integridad OK (SHA-256 coincide).", arch)


def desactivar_archivo(
    archivo_id: str, *, ctx: AppContext | None = None
) -> ResultadoArchivo:
    """Soft-delete de metadatos. No borra el fichero en disco."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)
    if denied:
        return ResultadoArchivo(False, denied)

    c = _ctx(ctx)
    data = c.uow.get_data()
    arch = buscar_por_id(data, archivo_id)
    if arch is None:
        return ResultadoArchivo(False, "Archivo no encontrado.")
    if not arch.activo:
        return ResultadoArchivo(False, "El archivo ya está inactivo.", arch)
    arch.activo = False
    _registrar_actividad(c, "Desactivar archivo documental", archivo_id)
    c.uow.commit(data)
    return ResultadoArchivo(True, "Archivo desactivado (fichero conservado).", arch)


def leer_bytes(
    archivo_id: str, *, ctx: AppContext | None = None
) -> tuple[bytes | None, str]:
    """Lectura del original. No modifica el fichero."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)
    if denied:
        return None, denied

    c = _ctx(ctx)
    arch = buscar_por_id(c.uow.get_data(), archivo_id)
    if arch is None:
        return None, "Archivo no encontrado."
    path = ruta_absoluta(arch)
    if not path.is_file():
        return None, "Fichero ausente en disco."
    return path.read_bytes(), ""


def enlazar_documento(
    archivo_id: str,
    documento_id: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoArchivo:
    """Asocia el archivo a una cabecera documental futura (F10+)."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import usecase_deny_message

    denied = usecase_deny_message(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)
    if denied:
        return ResultadoArchivo(False, denied)

    c = _ctx(ctx)
    data = c.uow.get_data()
    arch = buscar_por_id(data, archivo_id)
    if arch is None:
        return ResultadoArchivo(False, "Archivo no encontrado.")
    if not (documento_id or "").strip():
        return ResultadoArchivo(False, "documento_id vacío.")
    arch.documento_id = documento_id.strip()
    _registrar_actividad(
        c, "Enlazar archivo a documento", f"{archivo_id} → {documento_id}"
    )
    c.uow.commit(data)
    return ResultadoArchivo(True, "Archivo enlazado.", arch)
