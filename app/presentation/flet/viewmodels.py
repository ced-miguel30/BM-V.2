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


@dataclass(frozen=True)
class BasketLineVM:
    kind: str  # "receta" | "producto"
    line_id: str
    nombre: str
    cantidad: float
    unidad: str = ""


@dataclass(frozen=True)
class BasketVM:
    lineas: tuple[BasketLineVM, ...]
    vacia: bool
    servicio_id: str
    servicio_etiqueta: str


@dataclass(frozen=True)
class FeedbackVM:
    ok: bool
    mensaje: str
    codigo: str | None = None


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


def assert_sin_campos_economicos(obj: object) -> None:
    """Falla si un dataclass de viewmodel declara campos económicos."""
    if not hasattr(obj, "__dataclass_fields__"):
        return
    names = {f.name.lower() for f in fields(obj)}
    for bad in CAMPOS_ECONOMICOS_PROHIBIDOS:
        if bad.lower() in names:
            raise AssertionError(f"Viewmodel contiene campo económico: {bad}")
