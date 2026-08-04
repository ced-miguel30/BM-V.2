"""Aplicación de totales documentales (A4) sobre modelos Documento/Línea.

Usa ``money.calcular_documento``; no confirma ni muta stock.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.models.documento import DesgloseImpuesto, Documento, LineaDocumento
from app.core.services.money import (
    EntradaLineaCalculo,
    ResultadoDocumento,
    as_decimal,
    calcular_documento,
)


def _entrada_desde_linea(ln: LineaDocumento) -> EntradaLineaCalculo | None:
    """Construye entrada de cálculo si la línea tiene datos de compra A4.

    Legacy (solo ``cantidad``/``precio_total``) → None (no recalcular).
    """
    if ln.cantidad_compra is None or ln.precio_unitario_compra is None:
        return None
    factor = ln.factor_conversion if ln.factor_conversion is not None else Decimal("1")
    pct = ln.impuesto_porcentaje_snapshot
    return EntradaLineaCalculo(
        cantidad_compra=ln.cantidad_compra,
        precio_unitario_compra=ln.precio_unitario_compra,
        factor_conversion=factor,
        precio_incluye_igic=bool(ln.precio_incluye_igic),
        impuesto_porcentaje=pct if pct is not None else 0,
        impuesto_id=ln.impuesto_id,
        descuento_linea_porcentaje=ln.descuento_porcentaje or 0,
        descuento_linea_importe=ln.descuento_importe or 0,
        linea_id=ln.id or ln.client_line_key or "",
    )


def aplicar_resultado_a_linea(ln: LineaDocumento, resultado) -> None:
    """Escribe importes calculados en la línea (mutación in-place)."""
    ln.base_antes_descuento = resultado.base_antes_descuentos
    ln.base_imponible = resultado.base_imponible_final
    ln.descuento_cabecera_asignado = resultado.descuento_cabecera_asignado
    ln.cuota_impuesto = resultado.cuota_impuesto
    ln.total_linea = resultado.total_linea
    ln.cantidad_inventario = resultado.cantidad_inventario
    ln.coste_inventariable_linea = resultado.coste_inventariable_linea
    ln.coste_unitario_inventario = resultado.coste_unitario_inventario
    # Compatibilidad: cantidad/precio_total reflejan inventario e importe línea
    try:
        ln.cantidad = float(resultado.cantidad_inventario)
    except (TypeError, ValueError):
        pass
    try:
        ln.precio_total = float(resultado.total_linea)
    except (TypeError, ValueError):
        pass


def aplicar_resultado_a_documento(doc: Documento, resultado: ResultadoDocumento) -> None:
    doc.base_imponible = resultado.base_imponible
    doc.descuento_total = resultado.descuento_total
    doc.impuesto_total = resultado.impuesto_total
    doc.total_documento = resultado.total_documento
    doc.descuento_cabecera_importe = resultado.descuento_cabecera_importe
    doc.desglose_impuestos = [
        DesgloseImpuesto(
            impuesto_id=d.impuesto_id,
            porcentaje=d.porcentaje,
            base=d.base,
            cuota=d.cuota,
        )
        for d in resultado.desglose_impuestos
    ]


def recalcular_totales_documento(doc: Documento) -> ResultadoDocumento | None:
    """Recalcula totales si todas las líneas tienen campos de compra.

    Si alguna línea es legacy (sin cantidad_compra/precio), no muta y
    devuelve None. Si no hay líneas, pone ceros.
    """
    if not doc.lineas:
        cero = Decimal("0.00")
        doc.base_imponible = cero
        doc.descuento_total = cero
        doc.impuesto_total = cero
        doc.total_documento = cero
        if doc.descuento_cabecera_importe is None:
            doc.descuento_cabecera_importe = cero
        doc.desglose_impuestos = []
        return calcular_documento(
            [],
            descuento_cabecera_importe=doc.descuento_cabecera_importe or 0,
        )

    entradas: list[EntradaLineaCalculo] = []
    for ln in doc.lineas:
        e = _entrada_desde_linea(ln)
        if e is None:
            return None
        entradas.append(e)

    dto_cab = (
        as_decimal(doc.descuento_cabecera_importe)
        if doc.descuento_cabecera_importe is not None
        else Decimal("0")
    )
    resultado = calcular_documento(entradas, descuento_cabecera_importe=dto_cab)
    for ln, r in zip(doc.lineas, resultado.lineas, strict=True):
        aplicar_resultado_a_linea(ln, r)
    aplicar_resultado_a_documento(doc, resultado)
    return resultado
