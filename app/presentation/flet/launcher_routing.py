"""Routing del launcher Flet — sin reglas de negocio ni autorización.

Seleccionar un destino NO concede permisos; cada vertical autentica por su cuenta.
"""

from __future__ import annotations

from dataclasses import dataclass


DESTINO_RESTAURANTE = "restaurante"
DESTINO_INVENTARIO = "inventario"
DESTINO_ADMINISTRACION = "administracion"
DESTINO_LAUNCHER = "launcher"

DESTINOS_OPERATIVOS = (
    DESTINO_RESTAURANTE,
    DESTINO_INVENTARIO,
    DESTINO_ADMINISTRACION,
)


@dataclass(frozen=True)
class DestinoLauncher:
    id: str
    etiqueta: str
    descripcion: str


DESTINOS: tuple[DestinoLauncher, ...] = (
    DestinoLauncher(
        DESTINO_RESTAURANTE,
        "Restaurante",
        "Registro operativo de Desayuno, Comida, Cena y Bebidas. "
        "Tras abrir, pulse «Entrar al terminal».",
    ),
    DestinoLauncher(
        DESTINO_INVENTARIO,
        "Inventario",
        "Alertas, caducidad, merma y ajustes operativos.",
    ),
    DestinoLauncher(
        DESTINO_ADMINISTRACION,
        "Administración operativa",
        "Maestros, compras, documentos y backup. "
        "Primera vez: cree el acceso Dirección.",
    ),
)

STREAMLIT_ADMIN_HINT = (
    "Administración operativa en Flet (maestros, compras albarán/factura, "
    "documentos, adjuntos, rectificativas, backup). Streamlit queda como legado."
)


class DestinoDesconocidoError(ValueError):
    """Destino de launcher no reconocido."""


def normalizar_destino(valor: str | None) -> str:
    raw = (valor or "").strip().lower()
    aliases = {
        "": DESTINO_LAUNCHER,
        "launcher": DESTINO_LAUNCHER,
        "menu": DESTINO_LAUNCHER,
        "inicio": DESTINO_LAUNCHER,
        "restaurante": DESTINO_RESTAURANTE,
        "restaurant": DESTINO_RESTAURANTE,
        "inventario": DESTINO_INVENTARIO,
        "inventory": DESTINO_INVENTARIO,
        "administracion": DESTINO_ADMINISTRACION,
        "administración": DESTINO_ADMINISTRACION,
        "admin": DESTINO_ADMINISTRACION,
    }
    if raw not in aliases:
        raise DestinoDesconocidoError(f"Destino desconocido: {valor!r}")
    return aliases[raw]


def listar_destinos() -> tuple[DestinoLauncher, ...]:
    return DESTINOS


def resolver_destino(valor: str | None) -> str:
    """Devuelve id canónico de destino o lanza DestinoDesconocidoError."""
    return normalizar_destino(valor)
