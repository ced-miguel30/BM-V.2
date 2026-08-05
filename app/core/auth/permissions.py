"""Política central de permisos (F16)."""

from __future__ import annotations

from enum import Enum

from app.core.auth.roles import (
    ROL_ADMINISTRACION,
    ROL_DIRECCION,
    ROL_RECEPCION,
    ROL_RESTAURANTE,
    rol_canonico,
)


class Permiso(str, Enum):
    ACCEDER_REGISTRO = "acceder_registro"
    ACCEDER_GESTOR = "acceder_gestor"
    ACCEDER_INVENTARIO = "acceder_inventario"
    ACCEDER_COMPRAS_DOCUMENTOS = "acceder_compras_documentos"
    ACCEDER_CONFIGURACION = "acceder_configuracion"
    GESTIONAR_USUARIOS = "gestionar_usuarios"
    CREAR_USUARIO_DIRECCION = "crear_usuario_direccion"
    MODIFICAR_USUARIO_DIRECCION = "modificar_usuario_direccion"
    ELIMINAR_USUARIO = "eliminar_usuario"
    EXPORTAR_BACKUP = "exportar_backup"
    RESTAURAR_BACKUP = "restaurar_backup"
    EJECUTAR_OPERACION_DESTRUCTIVA = "ejecutar_operacion_destructiva"
    CONSULTAR_COSTES = "consultar_costes"
    REGISTRAR_CONSUMO_TERMINAL = "registrar_consumo_terminal"
    ACCEDER_TERMINAL_RESTAURANTE = "acceder_terminal_restaurante"
    # Subsecciones peligrosas de Configuración
    VER_RESTAURACION = "ver_restauracion"
    VER_ZONA_PELIGRO = "ver_zona_peligro"


_TODOS = frozenset(Permiso)

_MATRIZ: dict[str, frozenset[Permiso]] = {
    ROL_DIRECCION: _TODOS,
    ROL_ADMINISTRACION: frozenset(
        {
            Permiso.ACCEDER_REGISTRO,
            Permiso.ACCEDER_GESTOR,
            Permiso.ACCEDER_INVENTARIO,
            Permiso.ACCEDER_COMPRAS_DOCUMENTOS,
            Permiso.ACCEDER_CONFIGURACION,
            Permiso.GESTIONAR_USUARIOS,
            Permiso.ELIMINAR_USUARIO,
            Permiso.EXPORTAR_BACKUP,
            Permiso.CONSULTAR_COSTES,
        }
    ),
    ROL_RECEPCION: frozenset(),  # módulo pendiente — todos los Permiso = False (explícito)
    ROL_RESTAURANTE: frozenset(
        {
            Permiso.ACCEDER_REGISTRO,
            Permiso.ACCEDER_TERMINAL_RESTAURANTE,
            Permiso.REGISTRAR_CONSUMO_TERMINAL,
        }
    ),
}


class AuthorizationError(PermissionError):
    """Operación denegada por política F16."""

    def __init__(self, mensaje: str = "No autorizado.") -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje


def permisos_de_rol(rol: str | None) -> frozenset[Permiso]:
    return _MATRIZ.get(rol_canonico(rol), frozenset())


def tiene_permiso(rol: str | None, permiso: Permiso | str) -> bool:
    p = Permiso(permiso) if not isinstance(permiso, Permiso) else permiso
    return p in permisos_de_rol(rol)


def matriz_permisos() -> dict[str, frozenset[Permiso]]:
    """Copia de la matriz para tests."""
    return {k: frozenset(v) for k, v in _MATRIZ.items()}


# Mapeo sección de menú (etiqueta) → permiso requerido
_SECCION_PERMISO: dict[str, Permiso] = {
    "Dashboard": Permiso.ACCEDER_GESTOR,
    "Análisis": Permiso.ACCEDER_GESTOR,
    "Registros": Permiso.ACCEDER_REGISTRO,
    "Stock": Permiso.ACCEDER_INVENTARIO,
    "Recetas": Permiso.ACCEDER_INVENTARIO,
    "Configuración": Permiso.ACCEDER_CONFIGURACION,
}


def puede_ver_seccion(rol: str | None, seccion_label: str) -> bool:
    perm = _SECCION_PERMISO.get(seccion_label)
    if perm is None:
        return False
    return tiene_permiso(rol, perm)
