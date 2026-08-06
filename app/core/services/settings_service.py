"""Servicio de settings — usuarios y configuración (F16 + CRUD)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.auth.passwords import hash_password, password_usable
from app.core.auth.permissions import AuthorizationError, Permiso
from app.core.auth.roles import (
    ROL_DIRECCION,
    es_direccion,
    parse_rol_persistido,
    rol_canonico,
    roles_asignables,
)
from app.core.auth.session import get_auth_session
from app.core.auth.usecase_guard import require_usecase
from app.core.models import Actividad, ConfiguracionHotel, RolUsuario, Usuario
from app.core.storage.session_store import get_data, persist_data

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ASSETS_DIR = PROJECT_ROOT / "data" / "assets"
LOGO_FILE = ASSETS_DIR / "logo_hotel.png"

MONEDAS = {
    "EUR": ("EUR (€)", "€"),
    "USD": ("USD ($)", "$"),
    "GBP": ("GBP (£)", "£"),
}

MIN_PASSWORD_LEN = 8


@dataclass
class ResultadoOperacion:
    ok: bool
    mensaje: str


def _next_id(prefix: str, ids: list[str]) -> str:
    numeros = []
    for item_id in ids:
        sufijo = item_id[len(prefix) :]
        if item_id.startswith(prefix) and sufijo.isdigit():
            numeros.append(int(sufijo))
    return f"{prefix}{(max(numeros, default=0) + 1):02d}"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _registrar_actividad(data, accion: str, detalle: str) -> None:
    usuario = "Sistema"
    sess = get_auth_session()
    if sess and sess.authenticated:
        usuario = sess.actor_label
    else:
        for u in data.usuarios:
            if u.id == data.usuario_actual_id:
                usuario = u.nombre
                break
    actividad = Actividad(
        _next_id("act", [a.id for a in data.actividades]),
        datetime.now(),
        usuario,
        accion,
        detalle,
    )
    data.actividades.insert(0, actividad)


def _contar_direccion_activos(usuarios: list[Usuario], *, exclude_id: str | None = None) -> int:
    n = 0
    for u in usuarios:
        if exclude_id and u.id == exclude_id:
            continue
        if u.activo and es_direccion(u.rol):
            n += 1
    return n


def _actor_sesion_id() -> str | None:
    s = get_auth_session()
    if s and s.authenticated and s.actor_type == "usuario":
        return s.actor_id
    return None


def crear_usuario(
    nombre: str,
    rol: str,
    *,
    login: str = "",
    password: str = "",
    skip_auth: bool = False,
) -> ResultadoOperacion:
    """Crea usuario. ``skip_auth`` solo para bootstrap / tests controlados."""
    nombre = nombre.strip()
    login_n = (login or "").strip().lower()
    if not nombre or len(nombre) < 2:
        return ResultadoOperacion(False, "El nombre debe tener al menos 2 caracteres.")
    if not login_n or len(login_n) < 2:
        return ResultadoOperacion(False, "El identificador de acceso es obligatorio.")
    if len(password) < MIN_PASSWORD_LEN:
        return ResultadoOperacion(
            False, f"La contraseña debe tener al menos {MIN_PASSWORD_LEN} caracteres."
        )

    rol_c = rol_canonico(rol)
    if rol_c not in roles_asignables(incluye_direccion=True):
        return ResultadoOperacion(False, "Rol no válido.")

    if not skip_auth:
        try:
            require_usecase(Permiso.GESTIONAR_USUARIOS)
        except AuthorizationError as exc:
            return ResultadoOperacion(False, exc.mensaje)
        if rol_c == ROL_DIRECCION:
            try:
                require_usecase(Permiso.CREAR_USUARIO_DIRECCION)
            except AuthorizationError as exc:
                return ResultadoOperacion(False, exc.mensaje)

    data = get_data()
    if any((getattr(u, "login", "") or "").lower() == login_n for u in data.usuarios):
        return ResultadoOperacion(False, "Ya existe un usuario con ese identificador de acceso.")
    if any(u.nombre.lower() == nombre.lower() for u in data.usuarios):
        return ResultadoOperacion(False, f"Ya existe un usuario llamado «{nombre}».")

    ahora = _now()
    usuario = Usuario(
        _next_id("u", [u.id for u in data.usuarios]),
        nombre,
        parse_rol_persistido(rol_c),
        True,
        login=login_n,
        password_hash=hash_password(password),
        creado_en=ahora,
        modificado_en=ahora,
    )
    data.usuarios.append(usuario)
    _registrar_actividad(data, "Crear usuario", f"Usuario «{nombre}» ({rol_c}) creado")
    persist_data(data)
    return ResultadoOperacion(True, f"Usuario «{nombre}» creado.")


def editar_usuario(usuario_id: str, nuevo_nombre: str) -> ResultadoOperacion:
    nuevo_nombre = nuevo_nombre.strip()
    if not nuevo_nombre or len(nuevo_nombre) < 2:
        return ResultadoOperacion(False, "El nombre debe tener al menos 2 caracteres.")

    try:
        require_usecase(Permiso.GESTIONAR_USUARIOS)
    except AuthorizationError as exc:
        return ResultadoOperacion(False, exc.mensaje)

    data = get_data()
    usuario = next((u for u in data.usuarios if u.id == usuario_id), None)
    if not usuario:
        return ResultadoOperacion(False, "Usuario no encontrado.")
    if es_direccion(usuario.rol):
        try:
            require_usecase(Permiso.MODIFICAR_USUARIO_DIRECCION)
        except AuthorizationError as exc:
            return ResultadoOperacion(False, exc.mensaje)
    if any(u.id != usuario_id and u.nombre.lower() == nuevo_nombre.lower() for u in data.usuarios):
        return ResultadoOperacion(False, "Ya existe otro usuario con ese nombre.")

    anterior = usuario.nombre
    usuario.nombre = nuevo_nombre
    usuario.modificado_en = _now()
    _registrar_actividad(data, "Editar usuario", f"«{anterior}» renombrado a «{nuevo_nombre}»")
    persist_data(data)
    return ResultadoOperacion(True, "Usuario actualizado.")


def cambiar_rol_usuario(usuario_id: str, nuevo_rol: str) -> ResultadoOperacion:
    try:
        require_usecase(Permiso.GESTIONAR_USUARIOS)
    except AuthorizationError as exc:
        return ResultadoOperacion(False, exc.mensaje)

    rol_c = rol_canonico(nuevo_rol)
    if rol_c not in roles_asignables(incluye_direccion=True):
        return ResultadoOperacion(False, "Rol no válido.")

    data = get_data()
    usuario = next((u for u in data.usuarios if u.id == usuario_id), None)
    if not usuario:
        return ResultadoOperacion(False, "Usuario no encontrado.")

    era_dir = es_direccion(usuario.rol)
    sera_dir = rol_c == ROL_DIRECCION
    if era_dir or sera_dir:
        try:
            require_usecase(Permiso.MODIFICAR_USUARIO_DIRECCION)
        except AuthorizationError as exc:
            return ResultadoOperacion(False, exc.mensaje)

    if era_dir and not sera_dir:
        if _contar_direccion_activos(data.usuarios) <= 1 and usuario.activo:
            return ResultadoOperacion(False, "No se puede degradar al último Dirección activo.")

    usuario.rol = parse_rol_persistido(rol_c)
    usuario.modificado_en = _now()
    _registrar_actividad(data, "Cambiar rol", f"«{usuario.nombre}» → {rol_c}")
    persist_data(data)
    return ResultadoOperacion(True, "Rol actualizado.")


def set_usuario_activo(usuario_id: str, activo: bool) -> ResultadoOperacion:
    try:
        require_usecase(Permiso.GESTIONAR_USUARIOS)
    except AuthorizationError as exc:
        return ResultadoOperacion(False, exc.mensaje)

    data = get_data()
    usuario = next((u for u in data.usuarios if u.id == usuario_id), None)
    if not usuario:
        return ResultadoOperacion(False, "Usuario no encontrado.")
    if es_direccion(usuario.rol):
        try:
            require_usecase(Permiso.MODIFICAR_USUARIO_DIRECCION)
        except AuthorizationError as exc:
            return ResultadoOperacion(False, exc.mensaje)
    if not activo and es_direccion(usuario.rol):
        if _contar_direccion_activos(data.usuarios) <= 1:
            return ResultadoOperacion(False, "No se puede desactivar al último Dirección activo.")

    usuario.activo = activo
    usuario.modificado_en = _now()
    estado = "activado" if activo else "desactivado"
    _registrar_actividad(data, "Estado usuario", f"Usuario «{usuario.nombre}» {estado}")
    persist_data(data)
    return ResultadoOperacion(True, f"Usuario {estado}.")


def restablecer_password(usuario_id: str, nueva_password: str) -> ResultadoOperacion:
    try:
        require_usecase(Permiso.GESTIONAR_USUARIOS)
    except AuthorizationError as exc:
        return ResultadoOperacion(False, exc.mensaje)
    if len(nueva_password) < MIN_PASSWORD_LEN:
        return ResultadoOperacion(
            False, f"La contraseña debe tener al menos {MIN_PASSWORD_LEN} caracteres."
        )

    data = get_data()
    usuario = next((u for u in data.usuarios if u.id == usuario_id), None)
    if not usuario:
        return ResultadoOperacion(False, "Usuario no encontrado.")
    if es_direccion(usuario.rol):
        try:
            require_usecase(Permiso.MODIFICAR_USUARIO_DIRECCION)
        except AuthorizationError as exc:
            return ResultadoOperacion(False, exc.mensaje)

    usuario.password_hash = hash_password(nueva_password)
    usuario.modificado_en = _now()
    _registrar_actividad(data, "Restablecer contraseña", f"Usuario «{usuario.nombre}»")
    persist_data(data)
    return ResultadoOperacion(True, "Contraseña actualizada.")


def eliminar_usuario(usuario_id: str, *, skip_auth: bool = False) -> ResultadoOperacion:
    if not skip_auth:
        try:
            require_usecase(Permiso.ELIMINAR_USUARIO)
        except AuthorizationError as exc:
            return ResultadoOperacion(False, exc.mensaje)

    data = get_data()
    if usuario_id == _actor_sesion_id() or usuario_id == data.usuario_actual_id:
        # Sesión activa: no auto-eliminarse
        sess = get_auth_session()
        if sess and sess.actor_id == usuario_id:
            return ResultadoOperacion(False, "No puede eliminarse a sí mismo en la sesión activa.")
        if usuario_id == data.usuario_actual_id and sess is None:
            return ResultadoOperacion(False, "No puede eliminar el usuario activo de la sesión.")

    usuario = next((u for u in data.usuarios if u.id == usuario_id), None)
    if not usuario:
        return ResultadoOperacion(False, "Usuario no encontrado.")

    if es_direccion(usuario.rol) and not skip_auth:
        try:
            require_usecase(Permiso.MODIFICAR_USUARIO_DIRECCION)
        except AuthorizationError as exc:
            return ResultadoOperacion(False, exc.mensaje)
        if usuario.activo and _contar_direccion_activos(data.usuarios) <= 1:
            return ResultadoOperacion(False, "No se puede eliminar al último Dirección activo.")

    if len(data.usuarios) <= 1:
        return ResultadoOperacion(False, "Debe quedar al menos un usuario.")

    nombre = usuario.nombre
    data.usuarios = [u for u in data.usuarios if u.id != usuario_id]
    _registrar_actividad(data, "Eliminar usuario", f"Usuario «{nombre}» eliminado")
    persist_data(data)
    return ResultadoOperacion(True, f"Usuario «{nombre}» eliminado.")


def bootstrap_direccion(
    *,
    nombre: str,
    login: str,
    password: str,
) -> ResultadoOperacion:
    """Crea o completa el primer Dirección cuando no hay credenciales."""
    data = get_data()
    from app.core.auth.session import necesita_bootstrap

    if not necesita_bootstrap(data.usuarios):
        return ResultadoOperacion(False, "El bootstrap no está disponible.")

    nombre = nombre.strip()
    login_n = login.strip().lower()
    if not nombre or len(nombre) < 2:
        return ResultadoOperacion(False, "El nombre debe tener al menos 2 caracteres.")
    if not login_n or len(login_n) < 2:
        return ResultadoOperacion(False, "El identificador de acceso es obligatorio.")
    if len(password) < MIN_PASSWORD_LEN:
        return ResultadoOperacion(
            False, f"La contraseña debe tener al menos {MIN_PASSWORD_LEN} caracteres."
        )

    # Preferir completar un Dirección existente sin password
    candidato = next(
        (
            u
            for u in data.usuarios
            if u.activo and es_direccion(u.rol) and not password_usable(u.password_hash)
        ),
        None,
    )
    ahora = _now()
    if candidato is not None:
        if any(
            (getattr(u, "login", "") or "").lower() == login_n and u.id != candidato.id
            for u in data.usuarios
        ):
            return ResultadoOperacion(False, "Ya existe un usuario con ese identificador de acceso.")
        candidato.nombre = nombre
        candidato.login = login_n
        candidato.password_hash = hash_password(password)
        candidato.rol = RolUsuario.DIRECCION
        candidato.modificado_en = ahora
        if not candidato.creado_en:
            candidato.creado_en = ahora
        data.usuario_actual_id = candidato.id
        _registrar_actividad(data, "Bootstrap", "Credenciales iniciales de Dirección definidas")
        persist_data(data)
        return ResultadoOperacion(True, "Credenciales de Dirección configuradas.")

    return crear_usuario(
        nombre,
        ROL_DIRECCION,
        login=login_n,
        password=password,
        skip_auth=True,
    )


def guardar_configuracion(nombre: str, moneda_key: str) -> ResultadoOperacion:
    try:
        require_usecase(Permiso.ACCEDER_CONFIGURACION)
    except AuthorizationError as exc:
        return ResultadoOperacion(False, exc.mensaje)

    nombre = nombre.strip()
    if not nombre:
        return ResultadoOperacion(False, "El nombre del establecimiento es obligatorio.")
    if moneda_key not in MONEDAS:
        return ResultadoOperacion(False, "Moneda no válida.")

    _, simbolo = MONEDAS[moneda_key]
    data = get_data()
    logo = data.configuracion.logo_path if data.configuracion else None
    from app.core.services.ledger_config import preservable_ledger_fields

    ledger_fields = preservable_ledger_fields(data.configuracion)
    data.configuracion = ConfiguracionHotel(
        nombre,
        moneda_key,
        simbolo,
        logo,
        **ledger_fields,
    )
    _registrar_actividad(
        data, "Guardar configuración", f"Establecimiento: «{nombre}», moneda {moneda_key}"
    )
    persist_data(data)
    return ResultadoOperacion(True, "Configuración guardada correctamente.")


def guardar_logo(archivo_bytes: bytes, extension: str = "png") -> ResultadoOperacion:
    try:
        require_usecase(Permiso.ACCEDER_CONFIGURACION)
    except AuthorizationError as exc:
        return ResultadoOperacion(False, exc.mensaje)

    if not archivo_bytes:
        return ResultadoOperacion(False, "No se recibió ningún archivo.")

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    ruta = ASSETS_DIR / f"logo_hotel.{extension}"
    ruta.write_bytes(archivo_bytes)

    data = get_data()
    if not data.configuracion:
        data.configuracion = ConfiguracionHotel("Hotel Boutique", "EUR", "€", str(ruta))
    else:
        data.configuracion.logo_path = str(ruta)

    _registrar_actividad(data, "Subir logo", "Logo del establecimiento actualizado")
    persist_data(data)
    return ResultadoOperacion(True, "Logo guardado correctamente.")


def nombre_hotel_sidebar() -> str:
    data = get_data()
    if data.configuracion:
        return data.configuracion.nombre_establecimiento
    return "Hotel Boutique"
