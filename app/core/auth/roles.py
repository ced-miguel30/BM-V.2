"""Autenticación F16 — roles canónicos y etiquetas."""

from __future__ import annotations

from app.core.models.enums import RolUsuario

# Claves canónicas (no usar literales sueltos en páginas)
ROL_DIRECCION = "direccion"
ROL_ADMINISTRACION = "administracion"
ROL_RECEPCION = "recepcion"
ROL_RESTAURANTE = "restaurante"

ROLES_CANONICOS: tuple[str, ...] = (
    ROL_DIRECCION,
    ROL_ADMINISTRACION,
    ROL_RECEPCION,
    ROL_RESTAURANTE,
)

ETIQUETAS_ROL: dict[str, str] = {
    ROL_DIRECCION: "Dirección",
    ROL_ADMINISTRACION: "Administración",
    ROL_RECEPCION: "Recepción",
    ROL_RESTAURANTE: "Restaurante",
}

# Valores legacy persistidos → canónico
_LEGACY_A_CANONICO: dict[str, str] = {
    "Owner": ROL_DIRECCION,
    "Admin": ROL_ADMINISTRACION,
    "owner": ROL_DIRECCION,
    "admin": ROL_ADMINISTRACION,
    "Dirección": ROL_DIRECCION,
    "Administración": ROL_ADMINISTRACION,
    "Recepción": ROL_RECEPCION,
    "Restaurante": ROL_RESTAURANTE,
}


def rol_canonico(rol: RolUsuario | str | None) -> str:
    """Normaliza cualquier rol persistido/legacy a clave canónica."""
    if rol is None:
        return ""
    raw = rol.value if isinstance(rol, RolUsuario) else str(rol)
    if raw in ROLES_CANONICOS:
        return raw
    if raw in _LEGACY_A_CANONICO:
        return _LEGACY_A_CANONICO[raw]
    # Enum members nuevos
    try:
        enum_rol = RolUsuario(raw)
        return rol_canonico(enum_rol.value)
    except ValueError:
        return raw.lower().strip()


def es_direccion(rol: RolUsuario | str | None) -> bool:
    return rol_canonico(rol) == ROL_DIRECCION


def es_administracion(rol: RolUsuario | str | None) -> bool:
    return rol_canonico(rol) == ROL_ADMINISTRACION


def etiqueta_rol(rol: RolUsuario | str | None) -> str:
    c = rol_canonico(rol)
    return ETIQUETAS_ROL.get(c, c or "—")


def parse_rol_persistido(raw: str | None) -> RolUsuario:
    """Carga rol desde JSON: acepta legacy y canónicos."""
    if not raw:
        return RolUsuario.ADMINISTRACION
    c = rol_canonico(raw)
    mapping = {
        ROL_DIRECCION: RolUsuario.DIRECCION,
        ROL_ADMINISTRACION: RolUsuario.ADMINISTRACION,
        ROL_RECEPCION: RolUsuario.RECEPCION,
        ROL_RESTAURANTE: RolUsuario.RESTAURANTE,
    }
    if c in mapping:
        return mapping[c]
    # Fallback: intentar enum directo (Owner/Admin)
    try:
        return RolUsuario(raw)
    except ValueError:
        return RolUsuario.ADMINISTRACION


def roles_asignables(*, incluye_direccion: bool) -> list[str]:
    roles = [ROL_ADMINISTRACION, ROL_RECEPCION, ROL_RESTAURANTE]
    if incluye_direccion:
        return [ROL_DIRECCION, *roles]
    return roles
