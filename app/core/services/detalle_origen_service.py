"""Construcción de líneas de detalle con origen explícito."""

from __future__ import annotations

from app.core.models import LineaDetalleOrigen, OrigenConsumo
from app.core.repositories.data_repository import DataRepository
from app.core.services.cesta_service import GrupoRecetaCesta, LineaCesta


def construir_lineas_detalle(
    cesta: list[LineaCesta],
    grupos: list[GrupoRecetaCesta],
    *,
    tipo_servicio: str,
    registro_id: str,
    data,
) -> list[LineaDetalleOrigen]:
    """Genera una línea de detalle por cada consumo con origen, sin fusionar."""
    repo = DataRepository(data)
    detalle: list[LineaDetalleOrigen] = []

    for linea in cesta:
        if linea.cantidad <= 0:
            continue
        producto = repo.get_producto(linea.producto_id)
        es_bebida = bool(producto.es_bebida) if producto else False
        detalle.append(LineaDetalleOrigen(
            origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
            producto_id=linea.producto_id,
            cantidad=linea.cantidad,
            registro_origen_id=registro_id,
            tipo_servicio=tipo_servicio,
            categoria_receta=None,
            es_bebida_snapshot=es_bebida,
            categoria_receta_snapshot=None,
        ))

    for grupo in grupos:
        receta = repo.get_receta(grupo.receta_id)
        categoria = receta.categoria.value if receta else None
        for ing in grupo.ingredientes:
            if ing.cantidad <= 0:
                continue
            if ing.es_base_receta and not ing.es_extra:
                origen = OrigenConsumo.INGREDIENTE_RECETA.value
            else:
                origen = OrigenConsumo.EXTRA_RECETA.value
            producto = repo.get_producto(ing.producto_id)
            es_bebida = bool(producto.es_bebida) if producto else False
            detalle.append(LineaDetalleOrigen(
                origen=origen,
                producto_id=ing.producto_id,
                cantidad=ing.cantidad,
                receta_origen_id=grupo.receta_id,
                registro_origen_id=registro_id,
                tipo_servicio=tipo_servicio,
                categoria_receta=categoria,
                es_bebida_snapshot=es_bebida,
                categoria_receta_snapshot=categoria,
            ))

    return detalle


def asignar_costes_proporcionales(
    lineas_detalle: list[LineaDetalleOrigen],
    costes_agregados: dict[str, float],
    cantidades_agregadas: dict[str, float],
) -> None:
    """Reparte el coste FIFO agregado entre las líneas de detalle del mismo producto."""
    restantes = dict(costes_agregados)
    vistos: dict[str, int] = {}
    for det in lineas_detalle:
        vistos[det.producto_id] = vistos.get(det.producto_id, 0) + 1

    contador: dict[str, int] = {}
    for det in lineas_detalle:
        pid = det.producto_id
        contador[pid] = contador.get(pid, 0) + 1
        total_cant = cantidades_agregadas.get(pid, 0.0)
        total_coste = costes_agregados.get(pid, 0.0)
        if total_cant <= 0:
            det.coste = 0.0
            continue
        if contador[pid] == vistos[pid]:
            # Última línea del producto: absorbe el resto de redondeo.
            det.coste = round(restantes.get(pid, 0.0), 2)
        else:
            parte = round(total_coste * (det.cantidad / total_cant), 2)
            det.coste = parte
            restantes[pid] = round(restantes.get(pid, 0.0) - parte, 2)
