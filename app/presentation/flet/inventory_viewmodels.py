"""Viewmodels Terminal Inventario — sin información económica."""

from __future__ import annotations

from dataclasses import dataclass, fields

from app.presentation.flet.viewmodels import (
    CAMPOS_ECONOMICOS_PROHIBIDOS,
    FeedbackVM,
    SessionVM,
    assert_sin_campos_economicos,
)

ESPACIOS = ("alertas", "caducidad", "merma", "stock", "traslados", "ajustes")

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
    feedback: FeedbackVM | None
    confirmando: bool


def assert_inventario_sin_economia(*objs: object) -> None:
    for obj in objs:
        if obj is None:
            continue
        if hasattr(obj, "__dataclass_fields__"):
            assert_sin_campos_economicos(obj)
            names = {f.name.lower() for f in fields(obj)}
            for bad in CAMPOS_ECONOMICOS_PROHIBIDOS:
                if bad.lower() in names:
                    raise AssertionError(f"Campo económico en inventario: {bad}")
