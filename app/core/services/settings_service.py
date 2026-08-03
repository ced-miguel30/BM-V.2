"""Servicio de settings — usuarios y configuración."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

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


@dataclass
class ResultadoOperacion:
    ok: bool
    mensaje: str


def _next_id(prefix: str, ids: list[str]) -> str:
    numeros = []
    for item_id in ids:
        sufijo = item_id[len(prefix):]
        if item_id.startswith(prefix) and sufijo.isdigit():
            numeros.append(int(sufijo))
    return f"{prefix}{(max(numeros, default=0) + 1):02d}"


def _registrar_actividad(data, accion: str, detalle: str) -> None:
    usuario = "Sistema"
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


def crear_usuario(nombre: str, rol: str) -> ResultadoOperacion:
    nombre = nombre.strip()
    if not nombre or len(nombre) < 2:
        return ResultadoOperacion(False, "El nombre debe tener al menos 2 caracteres.")
    if rol not in ("Owner", "Admin"):
        return ResultadoOperacion(False, "Rol no válido.")

    data = get_data()
    if any(u.nombre.lower() == nombre.lower() for u in data.usuarios):
        return ResultadoOperacion(False, f"Ya existe un usuario llamado «{nombre}».")

    usuario = Usuario(
        _next_id("u", [u.id for u in data.usuarios]),
        nombre,
        RolUsuario(rol),
        True,
    )
    data.usuarios.append(usuario)
    _registrar_actividad(data, "Crear usuario", f"Usuario «{nombre}» ({rol}) creado")
    persist_data(data)
    return ResultadoOperacion(True, f"Usuario «{nombre}» creado.")


def editar_usuario(usuario_id: str, nuevo_nombre: str) -> ResultadoOperacion:
    nuevo_nombre = nuevo_nombre.strip()
    if not nuevo_nombre or len(nuevo_nombre) < 2:
        return ResultadoOperacion(False, "El nombre debe tener al menos 2 caracteres.")

    data = get_data()
    usuario = next((u for u in data.usuarios if u.id == usuario_id), None)
    if not usuario:
        return ResultadoOperacion(False, "Usuario no encontrado.")
    if any(u.id != usuario_id and u.nombre.lower() == nuevo_nombre.lower() for u in data.usuarios):
        return ResultadoOperacion(False, "Ya existe otro usuario con ese nombre.")

    anterior = usuario.nombre
    usuario.nombre = nuevo_nombre
    _registrar_actividad(data, "Editar usuario", f"«{anterior}» renombrado a «{nuevo_nombre}»")
    persist_data(data)
    return ResultadoOperacion(True, "Usuario actualizado.")


def eliminar_usuario(usuario_id: str) -> ResultadoOperacion:
    data = get_data()
    if len(data.usuarios) <= 1:
        return ResultadoOperacion(False, "Debe quedar al menos un usuario.")
    if usuario_id == data.usuario_actual_id:
        return ResultadoOperacion(False, "No puede eliminar el usuario activo de la sesión.")

    usuario = next((u for u in data.usuarios if u.id == usuario_id), None)
    if not usuario:
        return ResultadoOperacion(False, "Usuario no encontrado.")

    data.usuarios = [u for u in data.usuarios if u.id != usuario_id]
    _registrar_actividad(data, "Eliminar usuario", f"Usuario «{usuario.nombre}» eliminado")
    persist_data(data)
    return ResultadoOperacion(True, f"Usuario «{usuario.nombre}» eliminado.")


def guardar_configuracion(nombre: str, moneda_key: str) -> ResultadoOperacion:
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
    _registrar_actividad(data, "Guardar configuración", f"Establecimiento: «{nombre}», moneda {moneda_key}")
    persist_data(data)
    return ResultadoOperacion(True, "Configuración guardada correctamente.")


def guardar_logo(archivo_bytes: bytes, extension: str = "png") -> ResultadoOperacion:
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
