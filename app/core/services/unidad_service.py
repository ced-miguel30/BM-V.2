"""Conversión de unidades para ingredientes de receta."""

from app.core.models import UnidadProducto


def unidades_seleccionables(unidad_producto: UnidadProducto) -> list[str]:
    """Unidades que el usuario puede elegir según la unidad del producto."""
    if unidad_producto in {UnidadProducto.KG, UnidadProducto.GR}:
        return [UnidadProducto.KG.value, UnidadProducto.GR.value]
    return [unidad_producto.value]


def convertir_a_unidad_producto(
    cantidad: float,
    unidad_seleccionada: str,
    unidad_producto: UnidadProducto,
) -> float:
    """Convierte la cantidad introducida a la unidad nativa del producto."""
    if unidad_seleccionada == unidad_producto.value:
        return round(cantidad, 6)

    if unidad_producto == UnidadProducto.KG and unidad_seleccionada == UnidadProducto.GR.value:
        return round(cantidad / 1000, 6)
    if unidad_producto == UnidadProducto.GR and unidad_seleccionada == UnidadProducto.KG.value:
        return round(cantidad * 1000, 6)

    return round(cantidad, 6)


def cantidad_para_mostrar(
    cantidad_producto: float,
    unidad_producto: UnidadProducto,
    unidad_ui: str,
) -> float:
    """Convierte cantidad almacenada (unidad producto) a la unidad mostrada en UI."""
    if unidad_ui == unidad_producto.value:
        return cantidad_producto

    if unidad_producto == UnidadProducto.KG and unidad_ui == UnidadProducto.GR.value:
        return round(cantidad_producto * 1000, 4)
    if unidad_producto == UnidadProducto.GR and unidad_ui == UnidadProducto.KG.value:
        return round(cantidad_producto / 1000, 4)

    return cantidad_producto
