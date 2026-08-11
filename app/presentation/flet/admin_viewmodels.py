"""Viewmodels Administración operativa Flet — maestros + backup.

Sin economía salvo ``LoteAltaVM.precio_total`` (inventario inicial / registrar_lote).
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from app.presentation.flet.viewmodels import (
    CAMPOS_ECONOMICOS_PROHIBIDOS,
    FeedbackVM,
    SessionVM,
)

ADMIN_SECCIONES: tuple[str, ...] = (
    "inicio",
    "productos",
    "recetas",
    "usuarios",
    "responsables",
    "inventario_inicial",
    "backup",
    "configuracion",
)

ADMIN_SECCION_LABEL: dict[str, str] = {
    "inicio": "Inicio",
    "productos": "Productos",
    "recetas": "Recetas",
    "usuarios": "Usuarios",
    "responsables": "Responsables merma",
    "inventario_inicial": "Inventario inicial",
    "backup": "Backup",
    "configuracion": "Configuración",
}


@dataclass(frozen=True)
class ResponsableMermaVM:
    id: str
    nombre: str
    activo: bool


@dataclass(frozen=True)
class ProductoAdminVM:
    id: str
    nombre: str
    codigo: str
    unidad: str
    stock_minimo: float
    tipo_articulo: str
    es_bebida: bool
    activo: bool
    servicios: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecetaAdminVM:
    id: str
    nombre: str
    categoria: str
    porciones_estandar: float | None
    n_ingredientes: int
    activo: bool
    servicios: tuple[str, ...] = ()


@dataclass(frozen=True)
class UsuarioAdminVM:
    id: str
    nombre: str
    login: str
    rol: str
    activo: bool


@dataclass(frozen=True)
class BackupItemVM:
    nombre: str
    ruta: str
    tamano_bytes: int
    modificado: str


@dataclass(frozen=True)
class LoteAltaVM:
    """Borrador / resumen de alta de lote. Único VM admin con precio_total."""

    producto_id: str
    producto_nombre: str
    cantidad: float
    precio_total: float
    marca_proveedor: str = ""
    ubicacion_destino_id: str = ""


@dataclass(frozen=True)
class PendingChangeVM:
    """Resumen previo a confirmar una mutación (destructiva o responsables)."""

    kind: str
    resumen: str
    responsable_id: str = ""
    nombre: str = ""
    producto_id: str = ""
    receta_id: str = ""
    usuario_id: str = ""
    backup_nombre: str = ""
    backup_ruta: str = ""
    rol: str = ""
    password: str = ""
    login: str = ""
    confirmacion: str = ""


@dataclass(frozen=True)
class AdminScreenVM:
    session: SessionVM
    responsables: tuple[ResponsableMermaVM, ...]
    seccion: str = "inicio"
    productos: tuple[ProductoAdminVM, ...] = ()
    recetas: tuple[RecetaAdminVM, ...] = ()
    usuarios: tuple[UsuarioAdminVM, ...] = ()
    backups: tuple[BackupItemVM, ...] = ()
    unidades: tuple[str, ...] = ()
    categorias_receta: tuple[str, ...] = ()
    servicios_disponibles: tuple[str, ...] = ()
    tipos_articulo: tuple[str, ...] = ()
    roles_asignables: tuple[str, ...] = ()
    hotel_nombre: str = ""
    hotel_moneda: str = "EUR"
    lote_alta: LoteAltaVM | None = None
    filtro: str = ""
    feedback: FeedbackVM | None = None
    pending: PendingChangeVM | None = None
    mutando: bool = False
    motivos_fijos: tuple[str, ...] = ()
    puede_gestionar_usuarios: bool = False
    puede_exportar_backup: bool = False
    puede_restaurar_backup: bool = False
    inspeccion_backup: str = ""


def assert_admin_sin_economia(*tipos: type) -> None:
    """Falla si un VM declara campos económicos prohibidos (no usar con LoteAltaVM)."""
    for cls in tipos:
        nombres = {f.name.lower() for f in fields(cls)}
        for prohibido in CAMPOS_ECONOMICOS_PROHIBIDOS:
            assert prohibido not in nombres, f"{cls.__name__} campo económico {prohibido}"
            assert not any(
                prohibido in n for n in nombres if len(prohibido) > 2
            ), f"{cls.__name__} substring económico {prohibido} en {nombres}"


def assert_lote_alta_permite_solo_precio_total() -> None:
    """LoteAltaVM puede tener precio_total; ningún otro campo económico."""
    nombres = {f.name.lower() for f in fields(LoteAltaVM)}
    assert "precio_total" in nombres
    for prohibido in CAMPOS_ECONOMICOS_PROHIBIDOS:
        if prohibido == "precio_total":
            continue
        assert prohibido not in nombres, f"LoteAltaVM campo económico {prohibido}"
        matches = [
            n
            for n in nombres
            if len(prohibido) > 2 and prohibido in n and n != "precio_total"
        ]
        assert not matches, f"LoteAltaVM substring económico {prohibido} en {matches}"
