"""Viewmodels Terminal Inventario — ops sin economía + slice economato opcional."""

from __future__ import annotations

from dataclasses import dataclass, fields

from app.presentation.flet.inventory_document_viewmodels import EconomatoPanelVM
from app.presentation.flet.viewmodels import (
    CAMPOS_ECONOMICOS_PROHIBIDOS,
    FeedbackVM,
    SessionVM,
    assert_sin_campos_economicos,
)

# Orden NAV: compras Noray primero; ops planta al final.
ESPACIOS = (
    "compras_panel",
    "compras_albaran",
    "compras_factura",
    "compras_documentos",
    "compras_pendientes",
    "compras_conciliacion",
    "compras_proveedores",
    "compras_historial",
    "alertas",
    "caducidad",
    "merma",
    "stock",
    "traslados",
    "recuentos",
    "ajustes",
)

ESPACIOS_OPS = frozenset(
    {
        "alertas",
        "caducidad",
        "merma",
        "stock",
        "traslados",
        "recuentos",
        "ajustes",
    }
)

ESPACIOS_ECONOMATO = frozenset(
    {
        "compras_panel",
        "compras_albaran",
        "compras_factura",
        "compras_documentos",
        "compras_pendientes",
        "compras_conciliacion",
        "compras_proveedores",
        "compras_historial",
    }
)

ETIQUETA_SIN_UBICACION_HISTORICA = "Sin ubicación histórica"


@dataclass(frozen=True)
class EspacioVM:
    id: str
    etiqueta: str
    activo: bool = False


@dataclass(frozen=True)
class AlertaVM:
    id: str
    tipo: str
    titulo: str
    mensaje: str
    estado: str
    producto_id: str = ""
    severidad: str = ""  # operativa: stock_bajo / cero / vencido / …


@dataclass(frozen=True)
class LoteCaducidadVM:
    lote_id: str
    producto_id: str
    nombre_producto: str
    unidad: str
    cantidad_restante: float
    fecha_expiracion: str
    dias_restantes: int
    estado: str  # vencido | proximo


@dataclass(frozen=True)
class MermaLineaVM:
    lote_id: str
    producto_id: str
    nombre: str
    unidad: str
    cantidad: float
    motivo: str
    servicio: str
    turno: str
    responsable: str


@dataclass(frozen=True)
class MermaOpcionVM:
    id: str
    etiqueta: str


@dataclass(frozen=True)
class LoteAjusteVM:
    lote_id: str
    producto_id: str
    nombre: str
    unidad: str
    restante: float
    etiqueta: str


@dataclass(frozen=True)
class AjustePreviewVM:
    lote_id: str
    nombre: str
    unidad: str
    cantidad_antes: float
    cantidad_despues: float
    delta: float
    motivo: str
    comentario: str = ""


@dataclass(frozen=True)
class StockSaldoVM:
    producto_id: str
    producto_nombre: str
    lote_id: str
    ubicacion_id: str
    ubicacion_etiqueta: str
    saldo: float
    unidad: str
    cobertura: str
    es_historico_sin_ubicacion: bool = False


@dataclass(frozen=True)
class TrasladoOpcionVM:
    id: str
    etiqueta: str


@dataclass(frozen=True)
class TrasladoPreviewVM:
    producto_id: str
    producto_nombre: str
    lote_id: str
    ubicacion_origen_id: str
    ubicacion_origen_etiqueta: str
    ubicacion_destino_id: str
    ubicacion_destino_etiqueta: str
    cantidad: float
    disponible_origen: float
    unidad: str
    mensaje: str
    advertencia: str = ""


@dataclass(frozen=True)
class TrasladoRecienteVM:
    traslado_id: str
    producto_nombre: str
    lote_id: str
    origen_etiqueta: str
    destino_etiqueta: str
    cantidad: float
    unidad: str
    fecha: str


@dataclass(frozen=True)
class RecuentoLineaVM:
    producto_id: str
    producto_nombre: str
    lote_id: str
    unidad: str
    cantidad_esperada: float
    cantidad_contada: float
    diferencia: float
    efecto: str  # sin_cambio | entrada | salida


@dataclass(frozen=True)
class RecuentoPreviewVM:
    ubicacion_id: str
    ubicacion_etiqueta: str
    lineas: tuple[RecuentoLineaVM, ...]
    mensaje: str
    en_memoria: bool = True


@dataclass(frozen=True)
class RecuentoPendienteVM:
    recuento_id: str
    ubicacion_id: str
    ubicacion_etiqueta: str
    resumen: str
    fecha: str


@dataclass(frozen=True)
class RecuentoRecienteVM:
    recuento_id: str
    ubicacion_etiqueta: str
    resumen: str
    fecha: str
    estado: str


@dataclass(frozen=True)
class InventarioScreenVM:
    session: SessionVM
    espacios: tuple[EspacioVM, ...]
    espacio_activo: str
    alertas: tuple[AlertaVM, ...]
    lotes_caducidad: tuple[LoteCaducidadVM, ...]
    cesta_merma: tuple[MermaLineaVM, ...]
    cesta_merma_vacia: bool
    motivos_merma: tuple[str, ...]
    servicios_merma: tuple[MermaOpcionVM, ...]
    turnos_merma: tuple[MermaOpcionVM, ...]
    responsables_merma: tuple[MermaOpcionVM, ...]
    responsable_seleccionado: str | None
    lotes_ajuste: tuple[LoteAjusteVM, ...]
    motivos_ajuste: tuple[str, ...]
    ajuste_preview: AjustePreviewVM | None
    stock_filas: tuple[StockSaldoVM, ...]
    stock_busqueda: str
    stock_filtro_ubicacion: str | None
    stock_ubicaciones: tuple[TrasladoOpcionVM, ...]
    traslado_productos: tuple[TrasladoOpcionVM, ...]
    traslado_lotes: tuple[TrasladoOpcionVM, ...]
    traslado_origenes: tuple[TrasladoOpcionVM, ...]
    traslado_destinos: tuple[TrasladoOpcionVM, ...]
    traslado_producto_id: str | None
    traslado_lote_id: str | None
    traslado_origen_id: str | None
    traslado_destino_id: str | None
    traslado_cantidad: str
    traslado_disponible: float | None
    traslado_preview: TrasladoPreviewVM | None
    traslados_recientes: tuple[TrasladoRecienteVM, ...]
    recuento_ubicaciones: tuple[TrasladoOpcionVM, ...]
    recuento_productos: tuple[TrasladoOpcionVM, ...]
    recuento_lotes: tuple[TrasladoOpcionVM, ...]
    recuento_ubicacion_id: str | None
    recuento_producto_id: str | None
    recuento_lote_id: str | None
    recuento_esperado: float | None
    recuento_cantidad: str
    recuento_unidad: str
    recuento_lineas: tuple[RecuentoLineaVM, ...]
    recuento_preview: RecuentoPreviewVM | None
    recuento_pendiente_id: str | None
    recuento_requiere_confirmacion_borrador: bool
    recuento_aviso_borrador: str
    recuentos_pendientes: tuple[RecuentoPendienteVM, ...]
    recuentos_recientes: tuple[RecuentoRecienteVM, ...]
    feedback: FeedbackVM | None
    confirmando: bool
    economato: EconomatoPanelVM | None = None


def assert_inventario_sin_economia(*objs: object) -> None:
    """Valida VMs de planta. No aplicar a EconomatoPanelVM ni anidados documentales."""
    for obj in objs:
        if obj is None:
            continue
        if isinstance(obj, EconomatoPanelVM):
            continue
        if hasattr(obj, "__dataclass_fields__"):
            assert_sin_campos_economicos(obj)
            names = {f.name.lower() for f in fields(obj)}
            # economato es un contenedor opcional; no es campo económico.
            names.discard("economato")
            for bad in CAMPOS_ECONOMICOS_PROHIBIDOS:
                if bad.lower() in names:
                    raise AssertionError(f"Campo económico en inventario: {bad}")
