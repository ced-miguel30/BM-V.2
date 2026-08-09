"""Resolución de factor de conversión compra → inventario (B1 / D67)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


class ConversionDesconocidaError(ValueError):
    """Unidades distintas sin factor conocido: bloquea confirmación."""


def normalizar_unidad(valor: str | None) -> str:
    return (valor or "").strip().lower()


def parse_factor_conversion(raw: Decimal | float | int | str | None) -> Decimal | None:
    """Parsea factor (admite coma decimal). Vacío → None. Inválido → lanza ValueError."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, Decimal):
        d = raw
    else:
        texto = str(raw).strip().replace(" ", "").replace(",", ".")
        if not texto:
            return None
        try:
            d = Decimal(texto)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("El factor de conversión no es un número válido.") from exc
    if d.is_nan() or d.is_infinite():
        raise ValueError("El factor de conversión no es un número válido.")
    return d


def resolver_factor_conversion(
    *,
    unidad_compra: str | None,
    unidad_inventario: str | None,
    factor_explicito: Decimal | float | str | None,
    factor_catalogo: Decimal | float | str | None = None,
) -> Decimal:
    """Devuelve factor > 0.

    Prioridad:
    1. Factor explícito válido de la línea
    2. factor_compra del vínculo producto–proveedor
    3. Factor 1 solo si unidad de compra y unidad base son equivalentes
    4. Error bloqueante si las unidades difieren y no hay factor

    Nunca aplica 1.0 en silencio entre unidades distintas.
    """
    uc = normalizar_unidad(unidad_compra)
    ui = normalizar_unidad(unidad_inventario)

    explicito = parse_factor_conversion(
        factor_explicito if factor_explicito != "" else None
    )
    catalogo = parse_factor_conversion(
        factor_catalogo if factor_catalogo != "" else None
    )

    if uc and ui and uc == ui:
        if explicito is not None:
            if explicito <= 0:
                raise ValueError("factor_conversion debe ser mayor que cero.")
            return explicito
        return Decimal("1")

    for cand in (explicito, catalogo):
        if cand is None:
            continue
        if cand <= 0:
            raise ValueError("factor_conversion debe ser mayor que cero.")
        return cand

    if uc and ui and uc != ui:
        raise ConversionDesconocidaError(
            f"Conversión desconocida entre «{unidad_compra}» y «{unidad_inventario}»."
        )
    # Sin unidades claras: exigir factor explícito
    if explicito is None:
        raise ConversionDesconocidaError(
            "Falta factor_conversion y no hay unidades comparables."
        )
    if explicito <= 0:
        raise ValueError("factor_conversion debe ser mayor que cero.")
    return explicito


def relacion_activa(
    data: Any,
    *,
    producto_id: str | None,
    proveedor_id: str | None,
) -> Any | None:
    """Primer vínculo activo producto–proveedor, o None."""
    if not producto_id or not proveedor_id or data is None:
        return None
    for r in getattr(data, "relaciones_producto_proveedor", []) or []:
        if (
            r.producto_id == producto_id
            and r.proveedor_id == proveedor_id
            and getattr(r, "activo", True)
        ):
            return r
    return None


def obtener_factor_catalogo(
    data: Any,
    *,
    producto_id: str | None,
    proveedor_id: str | None,
) -> Decimal | None:
    rel = relacion_activa(data, producto_id=producto_id, proveedor_id=proveedor_id)
    if rel is None:
        return None
    return getattr(rel, "factor_compra", None)


def obtener_unidad_compra_catalogo(
    data: Any,
    *,
    producto_id: str | None,
    proveedor_id: str | None,
) -> str | None:
    rel = relacion_activa(data, producto_id=producto_id, proveedor_id=proveedor_id)
    if rel is None:
        return None
    u = getattr(rel, "unidad_compra", None)
    return (u or "").strip() or None


def texto_equivalencia(
    unidad_compra: str | None,
    factor: Decimal | float | str | None,
    unidad_base: str | None,
) -> str:
    """«1 Caja = 6 L» (vacío si no hay datos suficientes)."""
    uc = (unidad_compra or "").strip()
    ub = (unidad_base or "").strip()
    if not uc or not ub:
        return ""
    try:
        f = parse_factor_conversion(factor)
    except ValueError:
        return ""
    if f is None:
        if normalizar_unidad(uc) == normalizar_unidad(ub):
            f = Decimal("1")
        else:
            return ""
    # Formato legible sin ruido de ceros
    f_txt = format(f.normalize(), "f").rstrip("0").rstrip(".")
    if not f_txt:
        f_txt = "0"
    return f"1 {uc} = {f_txt} {ub}"
