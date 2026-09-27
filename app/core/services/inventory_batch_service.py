"""Descuento de inventario por lotes.

Valoración de coste (norma general):
1. Con stock restante: FIFO por lote — cada trozo al precio de ese lote
   hasta agotarlo, luego el siguiente.
2. Sin stock (o sobreconsumo): se valora al **último coste unitario con
   precio** del producto (último lote no anulado con cantidad>0 y
   precio_total>0) hasta que entre un lote nuevo con precio nuevo.

Orden físico de consumo: `(fecha_compra, id)` ascendente (más antiguo primero).

Fase 9: planificación sin mutar + aplicación atómica (todo o nada).
Fase 4F: API pura sobre `AppData`; acceso vía AppContext en
`app.core.application.inventory_ops`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.core.models import AppData, LoteStock


def lotes_ordenados_consumo(data: AppData, producto_id: str) -> list[LoteStock]:
    """Lotes con stock > 0, del más antiguo al más reciente (FIFO)."""
    from app.core.services.inventory_balance import cantidad_disponible_lote

    lotes = [
        l for l in data.lotes
        if l.producto_id == producto_id
        and cantidad_disponible_lote(data, l) > 0
        and not getattr(l, "anulado", False)
    ]
    return sorted(
        lotes,
        key=lambda l: (l.fecha_compra or date.min, l.id),
    )


def _ultimo_lote_producto(data: AppData, producto_id: str) -> LoteStock | None:
    """Último lote del producto (cualquier estado); destino físico de overdraw."""
    lotes = [
        l for l in data.lotes
        if l.producto_id == producto_id and not getattr(l, "anulado", False)
    ]
    if not lotes:
        return None
    return sorted(lotes, key=lambda l: (l.fecha_compra or date.min, l.id))[-1]


def _ultimo_lote_con_precio(data: AppData, producto_id: str) -> LoteStock | None:
    """Último lote con precio unitario usable (registro de precio vigente)."""
    lotes = [
        l for l in data.lotes
        if l.producto_id == producto_id
        and not getattr(l, "anulado", False)
        and float(getattr(l, "cantidad", 0) or 0) > 0
        and float(getattr(l, "precio_total", 0) or 0) > 0
    ]
    if not lotes:
        return None
    return sorted(lotes, key=lambda l: (l.fecha_compra or date.min, l.id))[-1]


def coste_unidad_lote(lote: LoteStock) -> float:
    if lote.cantidad <= 0:
        return 0.0
    return lote.precio_total / lote.cantidad


def coste_unitario_vigente(
    data: AppData,
    producto_id: str,
    *,
    preferido: LoteStock | None = None,
) -> float:
    """Precio unitario para valorar consumo sin stock restante.

    Prefiere ``preferido`` si tiene precio > 0; si no, el último lote con precio.
    """
    if preferido is not None:
        u = coste_unidad_lote(preferido)
        if u > 0:
            return float(u)
    lote = _ultimo_lote_con_precio(data, producto_id)
    if lote is None:
        return 0.0
    return float(coste_unidad_lote(lote))


def stock_disponible(data: AppData, producto_id: str) -> float:
    from app.core.services.inventory_balance import stock_disponible_producto

    return stock_disponible_producto(data, producto_id)


def calcular_coste_linea(data: AppData, producto_id: str, cantidad: float) -> float:
    """Coste FIFO + precio vigente en faltante (compat)."""
    return valorizar_cantidad_fifo(data, producto_id, cantidad).coste


@dataclass
class ResultadoValoracionFifo:
    coste: float
    cantidad_solicitada: float
    cantidad_valorada: float
    incompleto: bool
    coste_unitario_aplicable: float | None

    @property
    def faltante(self) -> float:
        return max(0.0, round(self.cantidad_solicitada - self.cantidad_valorada, 6))


def valorizar_cantidad_fifo(
    data: AppData, producto_id: str, cantidad: float
) -> ResultadoValoracionFifo:
    """Valora consumo: FIFO mientras haya stock; faltante al último precio.

    ``incompleto=True`` solo si queda cantidad sin precio vigente (ningún lote
    con precio_total>0). El stock físico agotado ya no deja el coste a 0 €.
    """
    solicitada = float(cantidad) if cantidad else 0.0
    if solicitada <= 0:
        return ResultadoValoracionFifo(0.0, 0.0, 0.0, False, None)
    from app.core.services.inventory_balance import cantidad_disponible_lote

    restante = solicitada
    coste = 0.0
    valorada = 0.0
    ultimo_tocado: LoteStock | None = None
    for lote in lotes_ordenados_consumo(data, producto_id):
        if restante <= 0:
            break
        disponible = cantidad_disponible_lote(data, lote)
        tomar = min(restante, disponible)
        if tomar <= 0:
            continue
        coste += tomar * coste_unidad_lote(lote)
        valorada += tomar
        restante -= tomar
        ultimo_tocado = lote
    if restante > 1e-9:
        unit_vig = coste_unitario_vigente(
            data, producto_id, preferido=ultimo_tocado,
        )
        if unit_vig > 0:
            coste += restante * unit_vig
            valorada += restante
            restante = 0.0
    valorada = round(valorada, 6)
    coste_r = round(coste, 2)
    # Incompleto: quedó cantidad sin valorizar, o solo había lotes a 0 €.
    sin_precio = _ultimo_lote_con_precio(data, producto_id) is None
    incompleto = restante > 1e-9 or (solicitada > 0 and coste_r <= 0 and sin_precio)
    unit = None
    if valorada > 0 and coste_r > 0:
        unit = coste / valorada
    return ResultadoValoracionFifo(
        coste=coste_r,
        cantidad_solicitada=solicitada,
        cantidad_valorada=valorada,
        incompleto=incompleto,
        coste_unitario_aplicable=unit,
    )


def snapshot_cantidades_restantes(data: AppData) -> dict[str, float]:
    return {lote.id: lote.cantidad_restante for lote in data.lotes}


def restaurar_cantidades_restantes(data: AppData, snapshot: dict[str, float]) -> None:
    for lote in data.lotes:
        if lote.id in snapshot:
            lote.cantidad_restante = snapshot[lote.id]


@dataclass
class LineaPreviewStock:
    producto_id: str
    nombre: str
    unidad: str
    actual: float
    salida: float
    resultante: float
    coste_estimado: float
    ok: bool


@dataclass
class PlanDescuentoStock:
    lineas: list[LineaPreviewStock] = field(default_factory=list)
    ok: bool = True
    deficits: list[str] = field(default_factory=list)


def planificar_descuento(
    data: AppData,
    demandas: dict[str, float],
    *,
    nombres: dict[str, str] | None = None,
    unidades: dict[str, str] | None = None,
) -> PlanDescuentoStock:
    """Vista previa no mutante: actual / salida / resultante por producto."""
    nombres = nombres or {}
    unidades = unidades or {}
    lineas: list[LineaPreviewStock] = []
    deficits: list[str] = []

    for producto_id, cantidad in demandas.items():
        if cantidad <= 0:
            continue
        actual = round(stock_disponible(data, producto_id), 4)
        salida = round(float(cantidad), 4)
        resultante = round(actual - salida, 4)
        ok = resultante >= -1e-9
        if ok and resultante < 0:
            resultante = 0.0
        nombre = nombres.get(producto_id, producto_id)
        unidad = unidades.get(producto_id, "")
        coste = calcular_coste_linea(data, producto_id, salida) if ok else 0.0
        lineas.append(LineaPreviewStock(
            producto_id=producto_id,
            nombre=nombre,
            unidad=unidad,
            actual=actual,
            salida=salida,
            resultante=max(resultante, 0.0) if ok else resultante,
            coste_estimado=coste,
            ok=ok,
        ))
        if not ok:
            ud = f" {unidad}" if unidad else ""
            deficits.append(
                f"No hay suficiente {nombre}. "
                f"Necesario: {salida:g}{ud}. Disponible: {actual:g}{ud}.".strip()
            )

    return PlanDescuentoStock(lineas=lineas, ok=not deficits, deficits=deficits)


@dataclass
class MovimientoDescuentoLote:
    """Trozo real descontado de un lote en el bucle FIFO (Fase 10.5)."""

    lote_id: str
    producto_id: str
    cantidad: float
    coste: float


@dataclass
class ResultadoDescuentoLotes:
    coste: float
    movimientos: list[MovimientoDescuentoLote] = field(default_factory=list)


@dataclass
class ResultadoDescuentoAtomico:
    costes: dict[str, float] = field(default_factory=dict)
    movimientos: list[MovimientoDescuentoLote] = field(default_factory=list)


def descontar_lotes(
    data: AppData,
    producto_id: str,
    cantidad: float,
    *,
    permitir_negativo: bool = False,
) -> ResultadoDescuentoLotes:
    """Descuenta `cantidad` de los lotes FIFO; devuelve coste y movimientos reales.

    Coste: precio de cada lote mientras haya stock; el sobreconsumo (si
    ``permitir_negativo``) se valora al último coste unitario con precio.

    Si no hay stock suficiente y `permitir_negativo` es False, no muta nada
    de este producto y lanza ValueError (Fase 9).
    """
    if cantidad <= 0:
        return ResultadoDescuentoLotes(coste=0.0, movimientos=[])

    if not permitir_negativo:
        disponible = stock_disponible(data, producto_id)
        if cantidad > disponible + 1e-9:
            raise ValueError(
                f"Stock insuficiente para descontar {cantidad:g} "
                f"(disponible {disponible:g}) del producto {producto_id}."
            )

    restante = cantidad
    coste = 0.0
    movimientos: list[MovimientoDescuentoLote] = []
    ultimo_lote_tocado: LoteStock | None = None
    from app.core.services.inventory_balance import cantidad_disponible_lote

    for lote in lotes_ordenados_consumo(data, producto_id):
        if restante <= 0:
            break
        disponible = cantidad_disponible_lote(data, lote)
        if disponible <= 0:
            continue
        tomar = min(restante, disponible)
        coste_trozo = tomar * coste_unidad_lote(lote)
        coste += coste_trozo
        # Espejo de compatibilidad: cantidad_restante sigue actualizándose.
        # En modo ledger la autoridad es el movimiento; el restante es derivado.
        lote.cantidad_restante = round(float(lote.cantidad_restante) - tomar, 4)
        restante -= tomar
        ultimo_lote_tocado = lote
        movimientos.append(MovimientoDescuentoLote(
            lote_id=lote.id,
            producto_id=producto_id,
            cantidad=round(tomar, 4),
            coste=round(coste_trozo, 2),
        ))

    if restante > 0 and permitir_negativo:
        lote_destino = ultimo_lote_tocado or _ultimo_lote_producto(data, producto_id)
        if lote_destino is None:
            # Sin lote previo: crear lote sintético a 0 para poder dejar stock negativo.
            from app.core.application.id_generator import next_id

            lote_destino = LoteStock(
                next_id("l", [l.id for l in data.lotes]),
                producto_id,
                0.0,
                0.0,
                0.0,
                fecha_compra=date.today(),
                marca_proveedor="AJUSTE-NEGATIVO",
            )
            data.lotes.append(lote_destino)
        unit_vig = coste_unitario_vigente(
            data, producto_id, preferido=ultimo_lote_tocado or lote_destino,
        )
        coste_trozo = round(restante * unit_vig, 2)
        coste += coste_trozo
        lote_destino.cantidad_restante = round(
            lote_destino.cantidad_restante - restante, 4,
        )
        movimientos.append(MovimientoDescuentoLote(
            lote_id=lote_destino.id,
            producto_id=producto_id,
            cantidad=round(restante, 4),
            coste=coste_trozo,
        ))

    # Reconciliar coste agregado vs suma de trozos (residuo en el último).
    coste_total = round(coste, 2)
    if movimientos:
        suma_trozos = round(sum(m.coste for m in movimientos), 2)
        if suma_trozos != coste_total:
            movimientos[-1].coste = round(
                movimientos[-1].coste + (coste_total - suma_trozos), 2,
            )

    return ResultadoDescuentoLotes(coste=coste_total, movimientos=movimientos)


def aplicar_descuento_atomico(
    data: AppData,
    demandas: dict[str, float],
    *,
    permitir_negativo: bool = False,
) -> ResultadoDescuentoAtomico:
    """Descuenta todos los productos o ninguno. Devuelve costes y movimientos.

    Por defecto requiere stock suficiente. Con ``permitir_negativo=True``
    deja registrar aunque el stock quede negativo (reconteo físico).
    Si falla a mitad, restaura lotes.
    """
    if not permitir_negativo:
        plan = planificar_descuento(data, demandas)
        if not plan.ok:
            raise ValueError("Stock insuficiente; no se aplica ningún descuento.")

    snap = snapshot_cantidades_restantes(data)
    costes: dict[str, float] = {}
    movimientos: list[MovimientoDescuentoLote] = []
    try:
        for producto_id, cantidad in demandas.items():
            if cantidad <= 0:
                continue
            resultado = descontar_lotes(
                data,
                producto_id,
                cantidad,
                permitir_negativo=permitir_negativo,
            )
            costes[producto_id] = resultado.coste
            movimientos.extend(resultado.movimientos)
    except Exception:
        restaurar_cantidades_restantes(data, snap)
        raise
    return ResultadoDescuentoAtomico(costes=costes, movimientos=movimientos)
