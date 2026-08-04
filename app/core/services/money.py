"""Cálculo monetario documental (Plan v3 + addendum).

Reglas:
- Base documental = cantidad_compra × precio_unitario_compra_neto
  (nunca cantidad_inventario).
- Precio unitario neto sin redondear a 2 dp antes de multiplicar.
- ROUND_HALF_UP a 2 dp en bases, descuentos, cuotas y totales.
- Descuento línea: primero %, luego importe.
- Descuento cabecera: solo importe; último céntimo en
  descuento_cabecera_asignado de la última línea (orden por id).
- Coste inventariable = base_imponible_final (+ no deducibles; 0 por defecto).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

TWOPLACES = Decimal("0.01")
ZERO = Decimal("0")


def as_decimal(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money_round(value: Decimal) -> Decimal:
    return as_decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def precio_unitario_neto(
    precio_introducido: Decimal | str | float,
    *,
    precio_incluye_igic: bool,
    impuesto_porcentaje: Decimal | str | float | None,
) -> Decimal:
    """Neto de compra. Sin forzar 2 dp (alta precisión interna)."""
    bruto = as_decimal(precio_introducido)
    if not precio_incluye_igic:
        return bruto
    pct = as_decimal(impuesto_porcentaje)
    if pct <= 0:
        return bruto
    return bruto / (1 + pct / Decimal("100"))


@dataclass(frozen=True)
class ResultadoLinea:
    cantidad_compra: Decimal
    precio_unitario_compra_neto: Decimal
    descuento_linea_porcentaje: Decimal
    descuento_linea_importe: Decimal
    base_antes_descuentos: Decimal
    base_tras_descuento_linea: Decimal
    descuento_cabecera_asignado: Decimal
    base_imponible_final: Decimal
    cuota_impuesto: Decimal
    total_linea: Decimal
    impuesto_porcentaje: Decimal
    cantidad_inventario: Decimal
    coste_inventariable_linea: Decimal
    coste_unitario_inventario: Decimal | None


@dataclass(frozen=True)
class DesgloseImpuestoCalc:
    impuesto_id: str | None
    porcentaje: Decimal
    base: Decimal
    cuota: Decimal


@dataclass(frozen=True)
class ResultadoDocumento:
    lineas: tuple[ResultadoLinea, ...]
    descuento_cabecera_importe: Decimal
    base_imponible: Decimal
    descuento_total: Decimal
    impuesto_total: Decimal
    total_documento: Decimal
    desglose_impuestos: tuple[DesgloseImpuestoCalc, ...] = field(default_factory=tuple)


def calcular_linea(
    *,
    cantidad_compra: float | Decimal | str,
    precio_unitario_compra: float | Decimal | str,
    factor_conversion: float | Decimal | str = 1,
    precio_incluye_igic: bool = False,
    impuesto_porcentaje: float | Decimal | str | None = 0,
    descuento_linea_porcentaje: float | Decimal | str = 0,
    descuento_linea_importe: float | Decimal | str = 0,
    descuento_cabecera_asignado: float | Decimal | str = 0,
    impuestos_no_deducibles: float | Decimal | str = 0,
) -> ResultadoLinea:
    qty = as_decimal(cantidad_compra)
    if qty < 0:
        raise ValueError("cantidad_compra no puede ser negativa.")
    factor = as_decimal(factor_conversion)
    if factor <= 0:
        raise ValueError("factor_conversion debe ser mayor que cero.")

    neto = precio_unitario_neto(
        precio_unitario_compra,
        precio_incluye_igic=precio_incluye_igic,
        impuesto_porcentaje=impuesto_porcentaje,
    )
    base_antes = money_round(qty * neto)

    dto_pct = as_decimal(descuento_linea_porcentaje)
    if dto_pct < 0 or dto_pct > 100:
        raise ValueError("descuento_linea_porcentaje debe estar entre 0 y 100.")
    dto_pct_imp = money_round(base_antes * dto_pct / Decimal("100"))
    base_tras_pct = base_antes - dto_pct_imp

    dto_imp = money_round(as_decimal(descuento_linea_importe))
    if dto_imp < 0:
        raise ValueError("descuento_linea_importe no puede ser negativo.")
    if dto_imp > base_tras_pct:
        raise ValueError("descuento_linea_importe excede la base tras el %.")
    base_tras_linea = base_tras_pct - dto_imp

    dto_cab = money_round(as_decimal(descuento_cabecera_asignado))
    if dto_cab < 0:
        raise ValueError("descuento_cabecera_asignado no puede ser negativo.")
    if dto_cab > base_tras_linea:
        raise ValueError("descuento_cabecera_asignado excede la base de línea.")
    base_final = base_tras_linea - dto_cab

    pct = as_decimal(impuesto_porcentaje)
    if pct < 0:
        raise ValueError("impuesto_porcentaje no puede ser negativo.")
    cuota = money_round(base_final * pct / Decimal("100"))
    total = base_final + cuota

    qty_inv = qty * factor
    no_ded = money_round(as_decimal(impuestos_no_deducibles))
    coste = base_final + no_ded
    coste_unit: Decimal | None
    if qty_inv == 0:
        coste_unit = None
    else:
        # Alta precisión: no forzar 2 dp
        coste_unit = coste / qty_inv

    return ResultadoLinea(
        cantidad_compra=qty,
        precio_unitario_compra_neto=neto,
        descuento_linea_porcentaje=dto_pct,
        descuento_linea_importe=dto_imp,
        base_antes_descuentos=base_antes,
        base_tras_descuento_linea=base_tras_linea,
        descuento_cabecera_asignado=dto_cab,
        base_imponible_final=base_final,
        cuota_impuesto=cuota,
        total_linea=total,
        impuesto_porcentaje=pct,
        cantidad_inventario=qty_inv,
        coste_inventariable_linea=coste,
        coste_unitario_inventario=coste_unit,
    )


def _repartir_descuento_cabecera(
    bases_linea: Sequence[Decimal],
    descuento_cabecera: Decimal,
) -> list[Decimal]:
    """Proporcional a bases; último céntimo en la última línea con base > 0."""
    dto = money_round(as_decimal(descuento_cabecera))
    if dto < 0:
        raise ValueError("descuento_cabecera_importe no puede ser negativo.")
    n = len(bases_linea)
    if n == 0:
        if dto > 0:
            raise ValueError("No hay líneas para repartir el descuento de cabecera.")
        return []
    total_bases = sum(bases_linea, ZERO)
    if dto == 0:
        return [ZERO] * n
    if total_bases <= 0:
        raise ValueError(
            "No se puede aplicar descuento de cabecera con bases imponibles nulas."
        )
    if dto > money_round(total_bases):
        raise ValueError("descuento_cabecera_importe excede la suma de bases de línea.")

    asignados = [ZERO] * n
    acumulado = ZERO
    indices_positivos = [i for i, b in enumerate(bases_linea) if b > 0]
    for i in indices_positivos[:-1]:
        parte = money_round(dto * bases_linea[i] / total_bases)
        asignados[i] = parte
        acumulado += parte
    ultimo = indices_positivos[-1]
    asignados[ultimo] = money_round(dto - acumulado)
    return asignados


@dataclass(frozen=True)
class EntradaLineaCalculo:
    cantidad_compra: float | Decimal | str
    precio_unitario_compra: float | Decimal | str
    factor_conversion: float | Decimal | str = 1
    precio_incluye_igic: bool = False
    impuesto_porcentaje: float | Decimal | str | None = 0
    impuesto_id: str | None = None
    descuento_linea_porcentaje: float | Decimal | str = 0
    descuento_linea_importe: float | Decimal | str = 0
    impuestos_no_deducibles: float | Decimal | str = 0
    linea_id: str = ""


def calcular_documento(
    entradas: Sequence[EntradaLineaCalculo],
    *,
    descuento_cabecera_importe: float | Decimal | str = 0,
) -> ResultadoDocumento:
    """Calcula líneas (con reparto de cabecera) y totales de documento."""
    # 1) Bases tras descuento de línea (sin cabecera)
    preliminares: list[ResultadoLinea] = []
    for e in entradas:
        preliminares.append(
            calcular_linea(
                cantidad_compra=e.cantidad_compra,
                precio_unitario_compra=e.precio_unitario_compra,
                factor_conversion=e.factor_conversion,
                precio_incluye_igic=e.precio_incluye_igic,
                impuesto_porcentaje=e.impuesto_porcentaje,
                descuento_linea_porcentaje=e.descuento_linea_porcentaje,
                descuento_linea_importe=e.descuento_linea_importe,
                descuento_cabecera_asignado=0,
                impuestos_no_deducibles=e.impuestos_no_deducibles,
            )
        )

    # Orden estable por linea_id para el último céntimo
    orden = sorted(range(len(entradas)), key=lambda i: entradas[i].linea_id or f"_{i}")
    bases_ordenadas = [preliminares[i].base_tras_descuento_linea for i in orden]
    dto_cab = as_decimal(descuento_cabecera_importe)
    partes = _repartir_descuento_cabecera(bases_ordenadas, dto_cab)
    mapa_dto = {orden[j]: partes[j] for j in range(len(orden))}

    finales: list[ResultadoLinea] = []
    for i, e in enumerate(entradas):
        finales.append(
            calcular_linea(
                cantidad_compra=e.cantidad_compra,
                precio_unitario_compra=e.precio_unitario_compra,
                factor_conversion=e.factor_conversion,
                precio_incluye_igic=e.precio_incluye_igic,
                impuesto_porcentaje=e.impuesto_porcentaje,
                descuento_linea_porcentaje=e.descuento_linea_porcentaje,
                descuento_linea_importe=e.descuento_linea_importe,
                descuento_cabecera_asignado=mapa_dto.get(i, ZERO),
                impuestos_no_deducibles=e.impuestos_no_deducibles,
            )
        )

    base_doc = money_round(sum((r.base_imponible_final for r in finales), ZERO))
    dto_lineas = money_round(
        sum(
            (
                (r.base_antes_descuentos - r.base_tras_descuento_linea)
                for r in finales
            ),
            ZERO,
        )
    )
    dto_cab_sum = money_round(sum((r.descuento_cabecera_asignado for r in finales), ZERO))
    descuento_total = money_round(dto_lineas + dto_cab_sum)
    impuesto_total = money_round(sum((r.cuota_impuesto for r in finales), ZERO))
    total_doc = money_round(base_doc + impuesto_total)

    # Desglose por % (e impuesto_id si existe)
    buckets: dict[tuple[str | None, str], DesgloseImpuestoCalc] = {}
    for i, r in enumerate(finales):
        key = (entradas[i].impuesto_id, format(r.impuesto_porcentaje, "f"))
        prev = buckets.get(key)
        if prev is None:
            buckets[key] = DesgloseImpuestoCalc(
                impuesto_id=entradas[i].impuesto_id,
                porcentaje=r.impuesto_porcentaje,
                base=r.base_imponible_final,
                cuota=r.cuota_impuesto,
            )
        else:
            buckets[key] = DesgloseImpuestoCalc(
                impuesto_id=prev.impuesto_id,
                porcentaje=prev.porcentaje,
                base=money_round(prev.base + r.base_imponible_final),
                cuota=money_round(prev.cuota + r.cuota_impuesto),
            )

    return ResultadoDocumento(
        lineas=tuple(finales),
        descuento_cabecera_importe=money_round(dto_cab),
        base_imponible=base_doc,
        descuento_total=descuento_total,
        impuesto_total=impuesto_total,
        total_documento=total_doc,
        desglose_impuestos=tuple(buckets.values()),
    )


def normalizar_codigo_funcional(codigo: str | None) -> str | None:
    """Normaliza código estable: strip, colapsa espacios, mayúsculas.

    Vacío → None (no válido para altas nuevas).
    """
    if codigo is None:
        return None
    texto = " ".join(str(codigo).strip().split())
    if not texto:
        return None
    return texto.upper()
