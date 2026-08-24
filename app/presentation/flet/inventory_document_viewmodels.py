"""Viewmodels documentales / economato — con economía (precios, impuestos, totales).

Separados de inventory_viewmodels (ops sin €) para no romper
assert_inventario_sin_economia en espacios de planta.
"""

from __future__ import annotations

from dataclasses import dataclass


TIPOS_UBICACION = ("economato", "cocina", "bar", "camara", "otro")

MAESTRO_TABS = (
    "departamentos",
    "ubicaciones",
    "proveedores",
    "impuestos",
    "vinculos",
)


@dataclass(frozen=True)
class OpcionDocVM:
    id: str
    etiqueta: str


@dataclass(frozen=True)
class CompraLineaDocVM:
    """Línea de recepción con paridad Streamlit 13.5."""

    key: str
    producto_id: str
    producto_nombre: str
    cantidad: str
    unidad: str
    precio_unitario: str
    dto_pct: str = "0"
    dto_eur: str = "0"
    igic_pct: str = "7"
    incluye_igic: bool = False
    total_linea: str = "0"
    ubicacion_destino_id: str = ""
    documento_origen_id: str = ""
    linea_origen_id: str = ""


@dataclass(frozen=True)
class TotalesCompraVM:
    base_imponible: str
    impuesto_total: str
    total: str
    descuento_cabecera: str = "0"


@dataclass(frozen=True)
class DocumentoListaVM:
    id: str
    tipo: str
    estado: str
    proveedor: str
    referencia: str
    fecha: str
    total: str
    lineas: int


@dataclass(frozen=True)
class DocumentoDetalleLineaVM:
    producto: str
    cantidad: str
    precio_unitario: str
    igic: str
    total: str
    origen_albaran: str = ""


@dataclass(frozen=True)
class DocumentoDetalleVM:
    id: str
    tipo: str
    estado: str
    proveedor: str
    referencia: str
    fecha: str
    notas: str
    base: str
    impuesto: str
    total: str
    lineas: tuple[DocumentoDetalleLineaVM, ...]


@dataclass(frozen=True)
class AlbaranConciliableVM:
    id: str
    etiqueta: str
    referencia: str
    total: str
    seleccionado: bool = False


@dataclass(frozen=True)
class DepartamentoMaestroVM:
    id: str
    nombre: str
    activo: bool


@dataclass(frozen=True)
class UbicacionMaestroVM:
    id: str
    nombre: str
    codigo: str
    tipo: str
    activo: bool


@dataclass(frozen=True)
class ProveedorMaestroVM:
    id: str
    codigo: str
    nombre_fiscal: str
    nif: str
    activo: bool


@dataclass(frozen=True)
class ImpuestoMaestroVM:
    id: str
    nombre: str
    porcentaje: str
    activo: bool


@dataclass(frozen=True)
class VinculoMaestroVM:
    id: str
    producto: str
    proveedor: str
    unidad_compra: str
    factor: str
    ultimo_precio: str
    activo: bool


@dataclass(frozen=True)
class HistorialEventoVM:
    fecha: str
    tipo: str
    producto: str
    ubicacion: str
    cantidad: str
    documento: str
    detalle: str


@dataclass(frozen=True)
class EconomatoPanelVM:
    """Slice documental del screen (solo espacios maestros/recepcion/documentos/historial)."""

    maestro_tab: str = "departamentos"
    # Recepción
    compra_tipo: str = "albaran"
    compra_proveedor_id: str = ""
    compra_referencia: str = ""
    compra_notas: str = ""
    compra_descuento_cabecera: str = "0"
    compra_ubicacion_entrada_id: str = ""
    compra_documento_id: str = ""
    compra_lineas: tuple[CompraLineaDocVM, ...] = ()
    compra_totales: TotalesCompraVM | None = None
    compra_prod_busqueda: str = ""
    compra_prod_sugerencias: tuple[OpcionDocVM, ...] = ()
    compra_proveedores: tuple[OpcionDocVM, ...] = ()
    compra_ubicaciones: tuple[OpcionDocVM, ...] = ()
    compra_impuestos_default: str = "7"
    compra_borradores: tuple[DocumentoListaVM, ...] = ()
    albaranes_conciliables: tuple[AlbaranConciliableVM, ...] = ()
    albaranes_seleccionados: tuple[str, ...] = ()
    # Documentos
    doc_filtro_texto: str = ""
    doc_filtro_tipo: str = ""
    doc_filtro_estado: str = ""
    documentos: tuple[DocumentoListaVM, ...] = ()
    documento_detalle: DocumentoDetalleVM | None = None
    # Maestros
    departamentos: tuple[DepartamentoMaestroVM, ...] = ()
    ubicaciones_maestro: tuple[UbicacionMaestroVM, ...] = ()
    proveedores_maestro: tuple[ProveedorMaestroVM, ...] = ()
    impuestos_maestro: tuple[ImpuestoMaestroVM, ...] = ()
    vinculos_maestro: tuple[VinculoMaestroVM, ...] = ()
    productos_opciones: tuple[OpcionDocVM, ...] = ()
    # Historial
    hist_texto: str = ""
    hist_ubicacion_id: str = ""
    hist_proveedor_id: str = ""
    historial: tuple[HistorialEventoVM, ...] = ()
