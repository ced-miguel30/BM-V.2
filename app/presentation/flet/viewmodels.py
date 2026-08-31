"""Viewmodels de Terminal Restaurante — sin información económica."""

from __future__ import annotations

from dataclasses import dataclass, fields


# Campos prohibidos en cualquier viewmodel de esta vertical.
CAMPOS_ECONOMICOS_PROHIBIDOS = frozenset({
    "coste",
    "coste_total",
    "precio",
    "precio_total",
    "margen",
    "valoracion",
    "importe",
    "eur",
    "euro",
    "euros",
    "€",
})


@dataclass(frozen=True)
class SessionVM:
    authenticated: bool
    actor_label: str = ""
    actor_id: str = ""
    role: str = ""
    terminal_id: str | None = None
    mensaje: str = ""


@dataclass(frozen=True)
class ServicioVM:
    id: str
    etiqueta: str
    activo: bool = False


@dataclass(frozen=True)
class CatalogItemVM:
    id: str
    nombre: str
    tipo: str  # "receta" | "producto_directo"
    unidad: str = ""
    stock_disponible: float | None = None
    es_bebida: bool = False
    categoria: str = ""
    # Cantidad al pulsar Añadir (extras rápidos de desayuno).
    cantidad_default: float | None = None
    # Texto de ayuda operativo (p. ej. «porción 20 gr»).
    hint_extra: str = ""


@dataclass(frozen=True)
class BasketLineVM:
    kind: str  # "receta" | "producto"
    line_id: str
    nombre: str
    cantidad: float
    unidad: str = ""


@dataclass(frozen=True)
class BasketExtraVM:
    """Extra sugerido de una receta en cesta (añadir como producto suelto)."""

    producto_id: str
    nombre: str
    cantidad: float
    unidad: str = ""
    receta_nombre: str = ""


@dataclass(frozen=True)
class BasketVM:
    lineas: tuple[BasketLineVM, ...]
    vacia: bool
    servicio_id: str
    servicio_etiqueta: str
    extras_sugeridos: tuple[BasketExtraVM, ...] = ()


@dataclass(frozen=True)
class FeedbackVM:
    ok: bool
    mensaje: str
    codigo: str | None = None


@dataclass(frozen=True)
class EdicionLineaVM:
    producto_id: str
    nombre: str
    cantidad: float
    unidad: str = ""


@dataclass(frozen=True)
class EdicionRegistroVM:
    registro_id: str
    tipo_registro: str
    etiqueta_corta: str
    lineas: tuple[EdicionLineaVM, ...]
    busqueda_producto: str = ""


@dataclass(frozen=True)
class HistorialRegistroVM:
    """Registro operativo sanitizado (sin economía).

    ``registro_id`` y ``tipo_registro`` son internos para anulación; la vista
    no debe mostrar el ID técnico completo.
    """

    registro_id: str
    tipo_registro: str  # "desayuno" | "servicio"
    etiqueta_corta: str
    fecha: str
    hora: str
    resumen: str
    estado: str  # activo | anulado | no_anulable | confirmado
    puede_anular: bool
    motivo_bloqueo: str = ""
    detalle_lineas: tuple[str, ...] = ()
    observaciones: str = ""
    puede_confirmar_revision: bool = False
    revision_confirmada: bool = False
    puede_editar: bool = False


@dataclass(frozen=True)
class AnulacionPendienteVM:
    """Confirmación de anulación en memoria (sin mutar aún)."""

    registro_id: str
    tipo_registro: str
    etiqueta_corta: str
    resumen: str
    motivo: str = ""


@dataclass(frozen=True)
class ImportacionTpvVM:
    """Resumen visible tras subir un documento TPV (sin economía)."""

    ok: bool
    titulo: str
    lineas: tuple[str, ...]
    advertencias: tuple[str, ...]
    historial: tuple[HistorialRegistroVM, ...] = ()


@dataclass(frozen=True)
class TerminalScreenVM:
    session: SessionVM
    servicios: tuple[ServicioVM, ...]
    servicio_activo: str | None
    catalogo: tuple[CatalogItemVM, ...]
    cesta: BasketVM | None
    feedback: FeedbackVM | None
    confirmando: bool
    num_huespedes: int
    requiere_huespedes: bool
    busqueda: str
    catalogo_tipo: str = "recetas"
    fecha_registro: str = ""  # AAAA-MM-DD
    historial: tuple[HistorialRegistroVM, ...] = ()
    historial_expandido: bool = False
    importacion_tpv: ImportacionTpvVM | None = None
    anulacion_pendiente: AnulacionPendienteVM | None = None
    anulando: bool = False
    edicion: EdicionRegistroVM | None = None
    editando: bool = False


def assert_sin_campos_economicos(obj: object) -> None:
    """Falla si un dataclass de viewmodel declara campos económicos."""
    if not hasattr(obj, "__dataclass_fields__"):
        return
    names = {f.name.lower() for f in fields(obj)}
    for bad in CAMPOS_ECONOMICOS_PROHIBIDOS:
        if bad.lower() in names:
            raise AssertionError(f"Viewmodel contiene campo económico: {bad}")
