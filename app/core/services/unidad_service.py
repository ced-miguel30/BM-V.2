"""Conversión de unidades para ingredientes de receta.

Centraliza toda la conversión entre la "unidad de presentación" que el
usuario elige al definir un ingrediente de receta (p. ej. gramos) y la
unidad nativa en la que el producto se almacena en inventario (p. ej.
kilogramos). El inventario, el coste y el descuento FIFO/lote siempre operan
sobre la unidad nativa; la unidad de presentación es solo para lectura.
"""

from __future__ import annotations

from app.core.models import UnidadProducto

UNIDAD_MG = "mg"
UNIDAD_GR = UnidadProducto.GR.value
UNIDAD_KG = UnidadProducto.KG.value
UNIDAD_ML = "ml"
UNIDAD_CL = "cl"
UNIDAD_L = UnidadProducto.L.value

# Factor de cada unidad respecto a su unidad base (kg para masa, L para volumen).
_MASA_A_KG: dict[str, float] = {UNIDAD_MG: 1e-6, UNIDAD_GR: 1e-3, UNIDAD_KG: 1.0}
_VOLUMEN_A_L: dict[str, float] = {UNIDAD_ML: 1e-3, UNIDAD_CL: 1e-2, UNIDAD_L: 1.0}

# Decimales razonables para mostrar cada unidad sin ruido de coma flotante
# ni ceros innecesarios (combinar con formato `:g` en el punto de uso).
_DECIMALES_VISUALES: dict[str, int] = {
    UNIDAD_MG: 1,
    UNIDAD_GR: 2,
    UNIDAD_KG: 4,
    UNIDAD_ML: 1,
    UNIDAD_CL: 2,
    UNIDAD_L: 4,
}


def _grupo_de(unidad: str) -> dict[str, float] | None:
    if unidad in _MASA_A_KG:
        return _MASA_A_KG
    if unidad in _VOLUMEN_A_L:
        return _VOLUMEN_A_L
    return None


def unidades_seleccionables(unidad_producto: UnidadProducto) -> list[str]:
    """Unidades compatibles que el usuario puede elegir según la unidad nativa
    del producto en inventario. Las unidades discretas (Ud) y "Otro" no
    admiten conversión: solo se pueden expresar en su propia unidad."""
    if unidad_producto in (UnidadProducto.KG, UnidadProducto.GR):
        return [UNIDAD_MG, UNIDAD_GR, UNIDAD_KG]
    if unidad_producto == UnidadProducto.L:
        return [UNIDAD_ML, UNIDAD_CL, UNIDAD_L]
    return [unidad_producto.value]


def unidades_compatibles(unidad: str) -> bool:
    """True si `unidad` es una unidad de masa o volumen reconocida por el
    conversor (independientemente del producto). Útil para validar entradas
    arbitrarias antes de convertir."""
    return unidad in _MASA_A_KG or unidad in _VOLUMEN_A_L


def convertir_a_unidad_producto(
    cantidad: float,
    unidad_seleccionada: str,
    unidad_producto: UnidadProducto,
) -> float:
    """Convierte una cantidad introducida en `unidad_seleccionada` a la
    unidad nativa del producto (`unidad_producto`). Si las unidades no son
    compatibles (p. ej. kg → L, o unidad discreta con otra unidad), no se
    realiza ninguna conversión y se devuelve la cantidad tal cual, ya que esa
    combinación nunca debería ofrecerse en la interfaz."""
    if unidad_seleccionada == unidad_producto.value:
        return round(cantidad, 6)

    grupo = _grupo_de(unidad_seleccionada)
    if grupo and unidad_producto.value in grupo:
        factor = grupo[unidad_seleccionada] / grupo[unidad_producto.value]
        return round(cantidad * factor, 6)

    return round(cantidad, 6)


def cantidad_para_mostrar(
    cantidad_producto: float,
    unidad_producto: UnidadProducto,
    unidad_ui: str,
) -> float:
    """Convierte una cantidad almacenada en la unidad nativa del producto a
    la unidad de presentación `unidad_ui`, redondeando a una precisión visual
    razonable (evita valores como 0,000499999)."""
    if unidad_ui == unidad_producto.value:
        return round(cantidad_producto, _DECIMALES_VISUALES.get(unidad_ui, 4))

    grupo = _grupo_de(unidad_ui)
    if grupo and unidad_producto.value in grupo:
        factor = grupo[unidad_producto.value] / grupo[unidad_ui]
        return round(cantidad_producto * factor, _DECIMALES_VISUALES.get(unidad_ui, 4))

    return round(cantidad_producto, 4)


def presentacion_legible(cantidad_nativa: float, unidad_producto: UnidadProducto) -> tuple[float, str]:
    """Elige una unidad legible para mostrar cuando no hay presentación guardada.

    Si la cantidad en kg o L es pequeña (< 1), se muestra en gr o ml para evitar
    valores como «0,001 Kg» en pantallas orientadas al usuario."""
    cantidad = abs(cantidad_nativa)
    if unidad_producto in (UnidadProducto.KG, UnidadProducto.GR) and cantidad < 1:
        return cantidad_para_mostrar(cantidad_nativa, unidad_producto, UNIDAD_GR), UNIDAD_GR
    if unidad_producto == UnidadProducto.L and cantidad < 1:
        return cantidad_para_mostrar(cantidad_nativa, unidad_producto, UNIDAD_ML), UNIDAD_ML
    return round(cantidad_nativa, _DECIMALES_VISUALES.get(unidad_producto.value, 4)), unidad_producto.value


def resolver_presentacion(
    cantidad_nativa: float,
    unidad_producto: UnidadProducto,
    *,
    cantidad_presentacion: float | None = None,
    unidad_presentacion: str | None = None,
    factor: float = 1.0,
) -> tuple[float, str]:
    """Cantidad y unidad para mostrar al usuario (receta, cesta, exportación).

    Usa la presentación guardada si existe; si no, infiere una unidad legible
    a partir de la cantidad nativa (p. ej. 0,001 kg → 1 gr)."""
    if unidad_presentacion and cantidad_presentacion is not None:
        if factor != 1.0:
            return escalar_presentacion(cantidad_presentacion, factor, unidad_presentacion), unidad_presentacion
        return cantidad_presentacion, unidad_presentacion
    cant = round(cantidad_nativa * factor, 4) if factor != 1.0 else cantidad_nativa
    return presentacion_legible(cant, unidad_producto)


def cantidad_y_unidad_mostrar(
    cantidad_nativa: float,
    unidad_producto: UnidadProducto,
    cantidad_presentacion: float | None,
    unidad_presentacion: str | None,
) -> tuple[float, str]:
    """Cantidad y unidad a mostrar al usuario para un ingrediente de receta.

    Si el ingrediente tiene una unidad de presentación guardada, se usa
    directamente (evita reconvertir y perder precisión). Si no la tiene —p. ej.
    una receta creada antes de esta función— se infiere una unidad legible
    (p. ej. 0,001 kg se muestra como 1 gr)."""
    return resolver_presentacion(
        cantidad_nativa,
        unidad_producto,
        cantidad_presentacion=cantidad_presentacion,
        unidad_presentacion=unidad_presentacion,
    )


def escalar_presentacion(cantidad_presentacion: float, factor: float, unidad_presentacion: str) -> float:
    """Escala una cantidad de presentación (p. ej. al cambiar las porciones
    de una receta) conservando la unidad elegida por el usuario."""
    return round(cantidad_presentacion * factor, _DECIMALES_VISUALES.get(unidad_presentacion, 4))
