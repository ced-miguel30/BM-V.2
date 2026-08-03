"""Generador de IDs con el mismo algoritmo que los servicios actuales."""

from __future__ import annotations


def next_id(prefix: str, ids: list[str]) -> str:
    """Prefijo + sufijo numérico zero-padded a 2 dígitos (p01, l02, …)."""
    numeros: list[int] = []
    for item_id in ids:
        sufijo = item_id[len(prefix):]
        if item_id.startswith(prefix) and sufijo.isdigit():
            numeros.append(int(sufijo))
    return f"{prefix}{(max(numeros, default=0) + 1):02d}"
