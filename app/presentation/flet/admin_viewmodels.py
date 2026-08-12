"""Viewmodels Administración operativa Flet — maestros + backup + compras + cierre.

Sin economía salvo ``LoteAltaVM.precio_total``, ``CompraLineaVM.precio_unitario``
y el panel ``AnalisisPanelVM`` (sección analisis).
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from app.presentation.flet.analisis_viewmodels import AnalisisPanelVM
from app.presentation.flet.viewmodels import (
    CAMPOS_ECONOMICOS_PROHIBIDOS,
    FeedbackVM,
    SessionVM,
)

ADMIN_SECCIONES: tuple[str, ...] = (
    "inicio",
    "analisis",
    "productos",
    "recetas",
    "usuarios",
    "responsables",
    "catalogos",
    "proveedores",
    "compras",
    "documentos",
    "inventario_inicial",
    "actividad",
    "backup",
    "configuracion",
    "servidor",
    "zona_peligro",
)

ADMIN_SECCION_LABEL: dict[str, str] = {
    "inicio": "Dashboard",
    "analisis": "Análisis",
    "productos": "Productos",
    "recetas": "Recetas",
    "usuarios": "Usuarios",
    "responsables": "Responsables merma",
    "catalogos": "Catálogos",
    "proveedores": "Proveedores",
    "compras": "Compras",
    "documentos": "Documentos",
    "inventario_inicial": "Inventario inicial",
    "actividad": "Actividad",
    "backup": "Backup",
    "configuracion": "Configuración",
    "servidor": "Servidor",
    "zona_peligro": "Zona peligro",
}


def secciones_visibles_admin(
    *,
    puede_zona_peligro: bool,
    puede_ver_analisis: bool = False,
) -> tuple[str, ...]:
    """Filtra zona_peligro y analisis según permisos de sesión."""
    out = list(ADMIN_SECCIONES)
    if not puede_ver_analisis:
        out = [s for s in out if s != "analisis"]
    if not puede_zona_peligro:
        out = [s for s in out if s != "zona_peligro"]
    return tuple(out)


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
class ProveedorAdminVM:
    id: str
    nombre_fiscal: str
    nombre_comercial: str
    codigo: str
    nif_cif: str
    activo: bool


@dataclass(frozen=True)
class CompraLineaVM:
    """Línea de borrador de compra. Único VM compra con precio_unitario."""

    producto_id: str
    nombre: str
    cantidad: float
    precio_unitario: float


@dataclass(frozen=True)
class DocumentoAdminVM:
    """Resumen operativo de documento (sin importes en la lista)."""

    id: str
    tipo: str
    estado: str
    fecha: str
    proveedor: str
    referencia: str = ""
    n_lineas: int = 0


@dataclass(frozen=True)
class ArchivoAdminVM:
    id: str
    nombre: str
    documento_id: str = ""
    activo: bool = True
    tamanio: int = 0


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
class CatalogoItemVM:
    id: str
    nombre: str
    activo: bool
    codigo: str = ""


@dataclass(frozen=True)
class ActividadAdminVM:
    fecha: str
    usuario: str
    accion: str
    detalle: str


@dataclass(frozen=True)
class DestructivaOpVM:
    id: str
    etiqueta: str
    frase: str
    nota: str = ""


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
    proveedor_id: str = ""
    backup_nombre: str = ""
    backup_ruta: str = ""
    rol: str = ""
    password: str = ""
    login: str = ""
    confirmacion: str = ""
    documento_id: str = ""


@dataclass(frozen=True)
class AdminScreenVM:
    session: SessionVM
    responsables: tuple[ResponsableMermaVM, ...]
    seccion: str = "inicio"
    productos: tuple[ProductoAdminVM, ...] = ()
    recetas: tuple[RecetaAdminVM, ...] = ()
    usuarios: tuple[UsuarioAdminVM, ...] = ()
    proveedores: tuple[ProveedorAdminVM, ...] = ()
    compra_lineas: tuple[CompraLineaVM, ...] = ()
    compra_proveedor_id: str = ""
    compra_referencia: str = ""
    compra_documento_id: str = ""
    compra_tipo: str = "albaran"
    compra_albaran_id: str = ""
    documentos: tuple[DocumentoAdminVM, ...] = ()
    archivos: tuple[ArchivoAdminVM, ...] = ()
    albaranes_conciliables: tuple[DocumentoAdminVM, ...] = ()
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
    # Dashboard (inicio)
    periodo: str = ""
    consumo_count: int = 0
    merma_count: int = 0
    stock_bajo: int = 0
    caducidades: int = 0
    alerta_registro: str = ""
    revision: int = 0
    data_path_label: str = ""
    # Servidor / shared root
    shared_root_label: str = ""
    # Catálogos
    departamentos: tuple[CatalogoItemVM, ...] = ()
    categorias: tuple[CatalogoItemVM, ...] = ()
    ubicaciones: tuple[CatalogoItemVM, ...] = ()
    # Actividad
    actividades: tuple[ActividadAdminVM, ...] = ()
    # Zona de peligro
    puede_zona_peligro: bool = False
    ops_destructivas: tuple[DestructivaOpVM, ...] = ()
    # Análisis (costes / consumo / merma)
    puede_ver_analisis: bool = False
    analisis: AnalisisPanelVM | None = None


def assert_admin_sin_economia(*tipos: type) -> None:
    """Falla si un VM declara campos económicos prohibidos (no usar con LoteAltaVM/CompraLineaVM)."""
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


def assert_compra_linea_permite_precio_unitario() -> None:
    """CompraLineaVM puede tener precio_unitario; ningún otro campo económico."""
    nombres = {f.name.lower() for f in fields(CompraLineaVM)}
    assert "precio_unitario" in nombres
    for prohibido in CAMPOS_ECONOMICOS_PROHIBIDOS:
        if prohibido == "precio_unitario":
            continue
        assert prohibido not in nombres, f"CompraLineaVM campo económico {prohibido}"
        matches = [
            n
            for n in nombres
            if len(prohibido) > 2 and prohibido in n and n != "precio_unitario"
        ]
        assert not matches, f"CompraLineaVM substring económico {prohibido} en {matches}"
