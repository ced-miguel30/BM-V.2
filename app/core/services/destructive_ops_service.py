"""Barrera y operaciones destructivas de datos (Fase C3).

No sustituye F16 (roles). Confirma intención, exige backup preventivo C2
antes de mutaciones masivas y protege el demo canónico bajo BM_TEST_ISOLATION.

Limitación: no hay autorización real por roles; la Zona de peligro vive en
Configuración con confirmación reforzada. Atomicidad conjunta JSON+adjuntos
no está garantizada (igual que C2).
"""

from __future__ import annotations

import json
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.core.services.backup_service import APPDATA_ARCNAME, generar_backup_zip
from app.core.services.restore_backup_service import (
    RESTORE_FALLIDO_RECUPERADO,
    RESTORE_FALLIDO_SIN_CAMBIOS,
    RESTORE_INCIERTO,
    RESTORE_OK,
    RESTORE_RECHAZADO,
    destino_es_demo_protegido,
    inspeccionar_backup,
)
from app.core.storage.demo_files import DEMO_FILE, get_demo_file
from app.core.storage.json_atomic import atomic_write_json
from app.data.mock_data import crear_datos_mock
from app.data.serializers import appdata_to_dict, dict_to_appdata, load_json

# Reexport estados para callers/UI
OP_OK = RESTORE_OK
OP_CANCELADO = "cancelado"
OP_RECHAZADO = RESTORE_RECHAZADO
OP_FALLIDO_SIN_CAMBIOS = RESTORE_FALLIDO_SIN_CAMBIOS
OP_FALLIDO_RECUPERADO = RESTORE_FALLIDO_RECUPERADO
OP_INCIERTO = RESTORE_INCIERTO

FRASE_RESET_TOTAL = "BORRAR TODOS LOS DATOS"
FRASE_ELIMINAR_USUARIO = "ELIMINAR USUARIO"

# Tokens ya consumidos (anti doble ejecución en el mismo proceso).
_CONSUMED_TOKENS: set[str] = set()


@dataclass
class ResultadoBarrera:
    ok: bool
    mensaje: str
    estado: str = OP_RECHAZADO


@dataclass
class ResultadoDestructivo:
    ok: bool
    estado: str
    mensaje: str
    operacion_id: str
    tipo_operacion: str
    fecha: str
    destino_logico: str
    backup_preventivo: str | None = None
    muto_estado: bool = False
    intento_recuperacion: bool = False
    recuperacion_ok: bool | None = None
    advertencias: list[str] = field(default_factory=list)
    error: str | None = None


def clear_consumed_tokens() -> None:
    """Solo para tests: limpia el conjunto anti-rerun del proceso."""
    _CONSUMED_TOKENS.clear()


def validar_confirmacion(
    frase_esperada: str,
    frase_recibida: str | None,
    checkbox_aceptado: bool,
) -> ResultadoBarrera:
    """Exige checkbox y coincidencia exacta (sin strip ni casefold)."""
    if not checkbox_aceptado:
        return ResultadoBarrera(False, "Debe aceptar la casilla de confirmación.")
    if frase_recibida is None:
        return ResultadoBarrera(False, "Falta la frase de confirmación.")
    if frase_recibida != frase_esperada:
        return ResultadoBarrera(
            False,
            "La frase de confirmación no coincide exactamente.",
        )
    return ResultadoBarrera(True, "Confirmación válida.", OP_OK)


def boton_destructivo_habilitado(
    frase_esperada: str,
    frase_recibida: str | None,
    checkbox_aceptado: bool,
) -> bool:
    """True solo si la barrera está completa (UI: disabled=not …)."""
    return validar_confirmacion(
        frase_esperada, frase_recibida, checkbox_aceptado
    ).ok


def _sanitizar_error(exc: BaseException) -> str:
    text = str(exc)
    if len(text) > 240:
        text = text[:240] + "…"
    return text.replace(str(DEMO_FILE), "[demo]")


def _dir_pre_reset(destino_json: Path) -> Path:
    return destino_json.parent / "backups" / "pre_reset"


def _destino_label(dest: Path) -> str:
    if destino_es_demo_protegido(dest):
        return "demo_protegido"
    if dest.resolve() == DEMO_FILE.resolve():
        return "demo_canonico"
    return "almacen_activo"


def crear_backup_preventivo_pre_reset(
    data,
    *,
    destino_json: Path,
    operacion_id: str,
) -> tuple[Path | None, str | None]:
    """Crea y valida ZIP pre_reset. Devuelve (path, error)."""
    try:
        pre = generar_backup_zip(data, kind="pre_reset", include_disk_snapshot=True)
        insp = inspeccionar_backup(pre.contenido, nombre=pre.nombre_archivo)
        if not insp.ok:
            return None, insp.mensaje
        folder = _dir_pre_reset(destino_json)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{operacion_id}_{pre.nombre_archivo}"
        path.write_bytes(pre.contenido)
        reinsp = inspeccionar_backup(path.read_bytes(), nombre=path.name)
        if not reinsp.ok:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None, reinsp.mensaje
        return path, None
    except Exception as exc:  # noqa: BLE001
        return None, _sanitizar_error(exc)


def _escribir_payload_mock(dest: Path, payload: dict) -> None:
    """Punto único de escritura (parcheable en tests de fallo/recuperación)."""
    atomic_write_json(dest, payload)


def _recuperar_desde_pre_reset(pre_path: Path, dest: Path) -> bool:
    try:
        with zipfile.ZipFile(pre_path) as zf:
            pre_payload = json.loads(zf.read(APPDATA_ARCNAME).decode("utf-8"))
        atomic_write_json(dest, pre_payload)
        return True
    except Exception:  # noqa: BLE001
        return False


def _resultado_base(
    *,
    ok: bool,
    estado: str,
    mensaje: str,
    op_id: str,
    ahora: str,
    dest_label: str,
    **kwargs,
) -> ResultadoDestructivo:
    return ResultadoDestructivo(
        ok,
        estado,
        mensaje,
        op_id,
        "restablecer_mock",
        ahora,
        dest_label,
        **kwargs,
    )


def restablecer_a_datos_mock(
    *,
    confirmacion_escrita: str,
    checkbox_aceptado: bool,
    destino_json: Path | str | None = None,
    operation_token: str | None = None,
    recargar_sesion: bool = False,
) -> ResultadoDestructivo:
    """Sustituye AppData por mock tras backup preventivo C2 validado."""
    op_id = str(uuid.uuid4())
    ahora = datetime.now().isoformat(timespec="seconds")
    dest = Path(destino_json).resolve() if destino_json else get_demo_file().resolve()
    dest_label = _destino_label(dest)

    try:
        from app.core.auth.permissions import Permiso
        from app.core.auth.session import require_permiso

        require_permiso(Permiso.EJECUTAR_OPERACION_DESTRUCTIVA)
    except Exception as exc:  # noqa: BLE001
        msg = getattr(exc, "mensaje", None) or str(exc) or "No autorizado."
        return _resultado_base(
            ok=False,
            estado=OP_RECHAZADO,
            mensaje=msg,
            op_id=op_id,
            ahora=ahora,
            dest_label=dest_label,
            error="no_autorizado",
        )

    if operation_token:
        if operation_token in _CONSUMED_TOKENS:
            return _resultado_base(
                ok=True,
                estado=OP_OK,
                mensaje="Operación ya aplicada (idempotente; no se repite).",
                op_id=op_id,
                ahora=ahora,
                dest_label=dest_label,
                advertencias=["token_ya_consumido"],
            )
    else:
        operation_token = op_id

    barrera = validar_confirmacion(
        FRASE_RESET_TOTAL, confirmacion_escrita, checkbox_aceptado
    )
    if not barrera.ok:
        return _resultado_base(
            ok=False,
            estado=OP_RECHAZADO,
            mensaje=barrera.mensaje,
            op_id=op_id,
            ahora=ahora,
            dest_label=dest_label,
            error=barrera.mensaje,
        )

    if destino_es_demo_protegido(dest):
        return _resultado_base(
            ok=False,
            estado=OP_RECHAZADO,
            mensaje="Destino demo protegido: operación abortada.",
            op_id=op_id,
            ahora=ahora,
            dest_label="demo_protegido",
            error="demo_protegido",
        )

    try:
        if dest.is_file():
            current = dict_to_appdata(load_json(dest))
        else:
            from app.core.storage.demo_files import load_demo_files

            current = load_demo_files()
    except Exception as exc:  # noqa: BLE001
        return _resultado_base(
            ok=False,
            estado=OP_FALLIDO_SIN_CAMBIOS,
            mensaje=f"No se pudo leer el estado actual: {_sanitizar_error(exc)}",
            op_id=op_id,
            ahora=ahora,
            dest_label=dest_label,
            error=_sanitizar_error(exc),
        )

    pre_path, pre_err = crear_backup_preventivo_pre_reset(
        current, destino_json=dest, operacion_id=op_id
    )
    if pre_path is None:
        return _resultado_base(
            ok=False,
            estado=OP_FALLIDO_SIN_CAMBIOS,
            mensaje=f"Backup preventivo inválido o no creado: {pre_err}",
            op_id=op_id,
            ahora=ahora,
            dest_label=dest_label,
            error=pre_err,
        )

    nuevo = crear_datos_mock()
    payload = appdata_to_dict(nuevo)
    muto = False
    try:
        _escribir_payload_mock(dest, payload)
        muto = True
    except Exception as exc:  # noqa: BLE001
        # Tras cualquier fallo en la fase de escritura: intentar recuperar.
        # No afirmamos si el destino quedó a medias (JSON atómico vs hook de test).
        recuperado = _recuperar_desde_pre_reset(pre_path, dest)
        return _resultado_base(
            ok=False,
            estado=OP_FALLIDO_RECUPERADO if recuperado else OP_INCIERTO,
            mensaje=f"Fallo al escribir datos: {_sanitizar_error(exc)}",
            op_id=op_id,
            ahora=ahora,
            dest_label=dest_label,
            backup_preventivo=pre_path.name,
            muto_estado=True,
            intento_recuperacion=True,
            recuperacion_ok=recuperado,
            error=_sanitizar_error(exc),
            advertencias=["Se intentó recuperar desde el backup preventivo pre_reset."],
        )

    _CONSUMED_TOKENS.add(operation_token)

    if recargar_sesion:
        try:
            from app.core.storage.session_store import reload_from_disk

            reload_from_disk()
        except Exception:  # noqa: BLE001
            pass

    return _resultado_base(
        ok=True,
        estado=OP_OK,
        mensaje="Datos restablecidos al conjunto mock. Backup preventivo conservado.",
        op_id=op_id,
        ahora=ahora,
        dest_label=dest_label,
        backup_preventivo=pre_path.name,
        muto_estado=muto,
        advertencias=[
            "Sustituye productos, lotes, documentos, movimientos, consumos y demás AppData.",
            "JSON y adjuntos previos en disco bajo data/documentos/ no se borran "
            "(pueden quedar huérfanos respecto al nuevo JSON).",
            "Sin roles F16: la UI no simula autorización por rol.",
        ],
    )


def inventario_acciones_destructivas_visibles() -> list[dict]:
    """Catálogo estático para tests/UI de lo expuesto en Configuración tras C3."""
    return [
        {
            "id": "restablecer_mock",
            "clasificacion": "B",
            "expuesta_en": "Zona de peligro",
            "frase": FRASE_RESET_TOTAL,
            "backup_preventivo": True,
        },
        {
            "id": "restaurar_backup",
            "clasificacion": "B",
            "expuesta_en": "Restauración de datos",
            "frase": "RESTAURAR",
            "backup_preventivo": True,
            "nota": "Protegida en C2",
        },
        {
            "id": "eliminar_usuario",
            "clasificacion": "B",
            "expuesta_en": "Usuarios",
            "frase": FRASE_ELIMINAR_USUARIO,
            "backup_preventivo": False,
            "nota": "Borrado puntual de un usuario; no wipe de AppData",
        },
        {
            "id": "recargar_desde_disco",
            "clasificacion": "A",
            "expuesta_en": "Datos demo",
            "frase": None,
            "backup_preventivo": False,
            "nota": "Solo reemplaza sesión desde JSON; no borra disco",
        },
        {
            "id": "reset_data_legacy_un_clic",
            "clasificacion": "C",
            "expuesta_en": "oculto",
            "frase": None,
            "backup_preventivo": False,
            "nota": "Botón legacy oculto; servicio session_store.reset_data conservado",
        },
    ]
