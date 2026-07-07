"""Utilidades de búsqueda insensible a tildes y mayúsculas."""

from __future__ import annotations

import unicodedata
from typing import Any


def normalizar_texto(texto: str) -> str:
    texto = texto.strip().lower()
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def empieza_por(nombre: str, termino: str) -> bool:
    if not termino.strip():
        return True
    return normalizar_texto(nombre).startswith(normalizar_texto(termino))


def contiene_texto(nombre: str, termino: str) -> bool:
    if not termino.strip():
        return True
    return normalizar_texto(termino) in normalizar_texto(nombre)


def coincide_busqueda(nombre: str, termino: str) -> bool:
    termino = termino.strip()
    if not termino:
        return True
    if len(normalizar_texto(termino)) >= 3:
        return contiene_texto(nombre, termino)
    return empieza_por(nombre, termino)


def filtrar_por_prefijo(
    items: list[dict[str, Any]],
    termino: str,
    campo: str = "nombre",
) -> list[dict[str, Any]]:
    termino = termino.strip()
    if not termino:
        return []
    return [item for item in items if empieza_por(item[campo], termino)]
