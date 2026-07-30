"""Construcción de líneas de detalle con origen explícito."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.models import AppData, LineaDetalleOrigen, OrigenConsumo
from app.core.models.registro_servicio import ConsumoLoteDetalle
from app.core.repositories.data_repository import DataRepository
from app.core.services.cesta_service import GrupoRecetaCesta, LineaCesta
from app.core.services.inventory_batch_service import MovimientoDescuentoLote


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


@dataclass
class _MovCola:
    """Estado mutable de un movimiento FIFO durante el reparto secuencial."""

    lote_id: str
    producto_id: str
    cantidad_restante: float
    coste_restante: float
    cantidad_original: float
    coste_original: float
    fragmentos: list[ConsumoLoteDetalle] = field(default_factory=list)


def asignar_consumos_lote(
    lineas_detalle: list[LineaDetalleOrigen],
    movimientos: list[MovimientoDescuentoLote],
) -> None:
    """Asigna movimientos FIFO a líneas de detalle de forma secuencial (Fase 10.5).

    - Conserva orden de movimientos y de líneas.
    - Un movimiento puede partirse entre líneas; una línea puede usar varios lotes.
    - Coste: fragmentos proporcionales a cantidad; el último fragmento de cada
      movimiento absorbe el residuo monetario exacto.
    - Tras asignar, `linea.coste` se alinea a la suma de sus fragmentos para
      cuadrar con el desglose por lote (el total por producto sigue siendo el FIFO).
    """
    for det in lineas_detalle:
        det.consumos_lote = []

    colas: dict[str, list[_MovCola]] = {}
    for mov in movimientos:
        if mov.cantidad <= 0:
            continue
        colas.setdefault(mov.producto_id, []).append(_MovCola(
            lote_id=mov.lote_id,
            producto_id=mov.producto_id,
            cantidad_restante=round(float(mov.cantidad), 4),
            coste_restante=round(float(mov.coste), 2),
            cantidad_original=round(float(mov.cantidad), 4),
            coste_original=round(float(mov.coste), 2),
        ))

    for det in lineas_detalle:
        if det.cantidad <= 0:
            continue
        cola = colas.get(det.producto_id, [])
        need = round(float(det.cantidad), 4)
        while need > 1e-9:
            while cola and cola[0].cantidad_restante <= 1e-9:
                cola.pop(0)
            if not cola:
                raise ValueError(
                    f"Sin movimientos FIFO suficientes para cubrir "
                    f"producto {det.producto_id} (faltan {need:g})."
                )
            cabeza = cola[0]
            if cabeza.producto_id != det.producto_id:
                raise ValueError("Movimiento de producto distinto al de la línea.")
            tomar = min(need, cabeza.cantidad_restante)
            tomar = round(tomar, 4)
            agota_mov = abs(cabeza.cantidad_restante - tomar) <= 1e-9
            if agota_mov:
                coste_frag = round(cabeza.coste_restante, 2)
                cabeza.cantidad_restante = 0.0
                cabeza.coste_restante = 0.0
            else:
                if cabeza.cantidad_original <= 0:
                    raise ValueError("Movimiento FIFO con cantidad original inválida.")
                coste_frag = round(
                    cabeza.coste_original * (tomar / cabeza.cantidad_original), 2,
                )
                cabeza.cantidad_restante = round(cabeza.cantidad_restante - tomar, 4)
                cabeza.coste_restante = round(cabeza.coste_restante - coste_frag, 2)
            frag = ConsumoLoteDetalle(
                lote_id=cabeza.lote_id,
                producto_id=cabeza.producto_id,
                cantidad=tomar,
                coste=coste_frag,
            )
            cabeza.fragmentos.append(frag)
            det.consumos_lote.append(frag)
            need = round(need - tomar, 4)
            if agota_mov:
                cola.pop(0)

        det.coste = round(sum(c.coste for c in det.consumos_lote), 2)

    # No deben quedar movimientos con cantidad sin asignar.
    for pid, cola in colas.items():
        resto = sum(m.cantidad_restante for m in cola)
        if resto > 1e-9:
            raise ValueError(
                f"Movimientos FIFO sin asignar para producto {pid}: {resto:g}."
            )


def validar_consumos_lote(
    lineas_detalle: list[LineaDetalleOrigen],
    movimientos: list[MovimientoDescuentoLote],
    costes_agregados: dict[str, float],
    data: AppData | None = None,
) -> None:
    """Valida invariantes de trazabilidad por lote. Lanza ValueError si fallan."""
    lote_por_id = {l.id: l for l in data.lotes} if data is not None else {}

    for det in lineas_detalle:
        if det.cantidad <= 0:
            continue
        if not det.consumos_lote:
            raise ValueError(
                f"Línea {det.producto_id} sin consumos_lote (cantidad {det.cantidad:g})."
            )
        suma_cant = 0.0
        suma_coste = 0.0
        for c in det.consumos_lote:
            if not c.lote_id:
                raise ValueError("consumos_lote con lote_id vacío.")
            if c.cantidad <= 0:
                raise ValueError(
                    f"Fragmento con cantidad no positiva en producto {det.producto_id}."
                )
            if c.producto_id != det.producto_id:
                raise ValueError(
                    f"Fragmento producto {c.producto_id} ≠ línea {det.producto_id}."
                )
            if data is not None:
                lote = lote_por_id.get(c.lote_id)
                if lote is None:
                    raise ValueError(f"Lote inexistente en consumos_lote: {c.lote_id}.")
                if lote.producto_id != c.producto_id:
                    raise ValueError(
                        f"Lote {c.lote_id} es producto {lote.producto_id}, "
                        f"no {c.producto_id}."
                    )
            suma_cant += c.cantidad
            suma_coste += c.coste
        if abs(round(suma_cant, 4) - round(det.cantidad, 4)) > 1e-9:
            raise ValueError(
                f"Suma cantidades consumos ({suma_cant:g}) ≠ "
                f"línea {det.producto_id} ({det.cantidad:g})."
            )
        if round(suma_coste, 2) != round(det.coste, 2):
            raise ValueError(
                f"Suma costes consumos ({suma_coste:.2f}) ≠ "
                f"línea {det.producto_id} ({det.coste:.2f})."
            )

    # Por producto: totales vs FIFO.
    cant_asig: dict[str, float] = {}
    coste_asig: dict[str, float] = {}
    for det in lineas_detalle:
        if det.cantidad <= 0:
            continue
        cant_asig[det.producto_id] = cant_asig.get(det.producto_id, 0.0) + det.cantidad
        coste_asig[det.producto_id] = coste_asig.get(det.producto_id, 0.0) + det.coste

    cant_fifo: dict[str, float] = {}
    coste_fifo: dict[str, float] = {}
    for mov in movimientos:
        if mov.cantidad <= 0:
            continue
        cant_fifo[mov.producto_id] = cant_fifo.get(mov.producto_id, 0.0) + mov.cantidad
        coste_fifo[mov.producto_id] = coste_fifo.get(mov.producto_id, 0.0) + mov.coste

    productos = set(cant_asig) | set(cant_fifo) | set(costes_agregados)
    for pid in productos:
        if abs(round(cant_asig.get(pid, 0.0), 4) - round(cant_fifo.get(pid, 0.0), 4)) > 1e-9:
            raise ValueError(
                f"Cantidad asignada ≠ FIFO para {pid}: "
                f"{cant_asig.get(pid, 0.0):g} vs {cant_fifo.get(pid, 0.0):g}."
            )
        if round(coste_asig.get(pid, 0.0), 2) != round(costes_agregados.get(pid, 0.0), 2):
            raise ValueError(
                f"Coste asignado ≠ agregado para {pid}: "
                f"{coste_asig.get(pid, 0.0):.2f} vs {costes_agregados.get(pid, 0.0):.2f}."
            )
        if round(coste_fifo.get(pid, 0.0), 2) != round(costes_agregados.get(pid, 0.0), 2):
            raise ValueError(
                f"Coste movimientos ≠ agregado para {pid}: "
                f"{coste_fifo.get(pid, 0.0):.2f} vs {costes_agregados.get(pid, 0.0):.2f}."
            )

    # Por movimiento original: suma de fragmentos (detectar por orden/reconstrucción).
    # Agrupar fragmentos asignados en el mismo orden que movimientos con matching secuencial.
    frags_por_producto: dict[str, list[ConsumoLoteDetalle]] = {}
    for det in lineas_detalle:
        for c in det.consumos_lote:
            frags_por_producto.setdefault(c.producto_id, []).append(c)

    for pid, movs in _agrupar_movimientos(movimientos).items():
        frags = list(frags_por_producto.get(pid, []))
        idx = 0
        for mov in movs:
            if mov.cantidad <= 0:
                continue
            acc_cant = 0.0
            acc_coste = 0.0
            while idx < len(frags) and abs(acc_cant - mov.cantidad) > 1e-9:
                f = frags[idx]
                if f.lote_id != mov.lote_id:
                    raise ValueError(
                        f"Fragmento lote {f.lote_id} no coincide con movimiento "
                        f"{mov.lote_id} (producto {pid})."
                    )
                next_cant = round(acc_cant + f.cantidad, 4)
                if next_cant - round(mov.cantidad, 4) > 1e-9:
                    raise ValueError(
                        f"Fragmentos superan cantidad del movimiento {mov.lote_id}."
                    )
                acc_cant = next_cant
                acc_coste = round(acc_coste + f.coste, 2)
                idx += 1
            if abs(round(acc_cant, 4) - round(mov.cantidad, 4)) > 1e-9:
                raise ValueError(
                    f"Fragmentos no cubren movimiento {mov.lote_id}: "
                    f"{acc_cant:g} vs {mov.cantidad:g}."
                )
            if round(acc_coste, 2) != round(mov.coste, 2):
                raise ValueError(
                    f"Coste fragmentos ≠ movimiento {mov.lote_id}: "
                    f"{acc_coste:.2f} vs {mov.coste:.2f}."
                )
        if idx != len(frags):
            raise ValueError(f"Fragmentos sobrantes sin movimiento para producto {pid}.")


def _agrupar_movimientos(
    movimientos: list[MovimientoDescuentoLote],
) -> dict[str, list[MovimientoDescuentoLote]]:
    out: dict[str, list[MovimientoDescuentoLote]] = {}
    for mov in movimientos:
        out.setdefault(mov.producto_id, []).append(mov)
    return out
