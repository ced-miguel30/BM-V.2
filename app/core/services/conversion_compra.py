"""Resolución de factor de conversión compra → inventario (B1 / D67)."""

from __future__ import annotations

from decimal import Decimal


class ConversionDesconocidaError(ValueError):
    """Unidades distintas sin factor conocido: bloquea confirmación."""


def normalizar_unidad(valor: str | None) -> str:
    return (valor or "").strip().lower()


def resolver_factor_conversion(
    *,
    unidad_compra: str | None,
    unidad_inventario: str | None,
    factor_explicito: Decimal | float | str | None,
    factor_catalogo: Decimal | float | str | None = None,
) -> Decimal:
    """Devuelve factor > 0.

    - Misma unidad (normalizada) → 1
    - Factor explícito o de catálogo si > 0
    - Unidades distintas sin factor → ConversionDesconocidaError
    - Nunca 1.0 silencioso si unidades distintas
    """
    uc = normalizar_unidad(unidad_compra)
    ui = normalizar_unidad(unidad_inventario)
    if uc and ui and uc == ui:
        if factor_explicito is not None and Decimal(str(factor_explicito)) > 0:
            return Decimal(str(factor_explicito))
        return Decimal("1")

    for cand in (factor_explicito, factor_catalogo):
        if cand is None or cand == "":
            continue
        f = Decimal(str(cand))
        if f <= 0:
            raise ValueError("factor_conversion debe ser mayor que cero.")
        return f

    if uc and ui and uc != ui:
        raise ConversionDesconocidaError(
            f"Conversión desconocida entre «{unidad_compra}» y «{unidad_inventario}»."
        )
    # Sin unidades claras: exigir factor explícito
    if factor_explicito is None or factor_explicito == "":
        raise ConversionDesconocidaError(
            "Falta factor_conversion y no hay unidades comparables."
        )
    f = Decimal(str(factor_explicito))
    if f <= 0:
        raise ValueError("factor_conversion debe ser mayor que cero.")
    return f
