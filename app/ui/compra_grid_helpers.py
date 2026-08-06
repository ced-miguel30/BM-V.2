"""Helpers puros para la rejilla de compras (UI) — sin Streamlit.

Precio unitario ↔ total, totales documentales y conciliación multi-albarán.
"""

from __future__ import annotations

import math
import uuid
from decimal import Decimal
from typing import Any

from app.core.models import EstadoDocumento, TipoDocumento
from app.core.models.conciliacion import EstadoConciliacion
from app.core.services.factura_service import linea_albaran_ya_conciliada
from app.core.services.money import (
    EntradaLineaCalculo,
    ResultadoDocumento,
    as_decimal,
    calcular_documento,
    money_round,
)

# Columnas visibles en data_editor
GRID_COLS = [
    "producto",
    "cantidad",
    "unidad",
    "precio_unitario",
    "precio_total",
    "dto_pct",
    "dto_eur",
    "igic_pct",
    "incluye_igic",
]

# Metadatos por fila (no editables en rejilla)
META_KEY = "_key"
META_ALB_LN = "_alb_linea_id"
META_ALB_DOC = "_alb_doc_id"
META_PROD_ID = "_producto_id"


def celda_texto(valor: Any) -> str:
    """Texto seguro desde celdas del editor (None / NaN / float → "")."""
    if valor is None:
        return ""
    if isinstance(valor, float) and math.isnan(valor):
        return ""
    if isinstance(valor, str):
        texto = valor.strip()
        return "" if texto.lower() == "nan" else texto
    texto = str(valor).strip()
    if not texto or texto.lower() == "nan":
        return ""
    return texto


def celda_numero(valor: Any, default: float = 0.0) -> float:
    """Número seguro; NaN / None / inválido → default."""
    if valor is None:
        return default
    if isinstance(valor, float) and math.isnan(valor):
        return default
    if isinstance(valor, str) and not valor.strip():
        return default
    try:
        return float(as_decimal(valor))
    except Exception:  # noqa: BLE001
        return default


def empty_row(*, igic_default: float = 7.0) -> dict[str, Any]:
    return {
        "producto": "",
        "cantidad": 0.0,
        "unidad": "Ud",
        "precio_unitario": 0.0,
        "precio_total": 0.0,
        "dto_pct": 0.0,
        "dto_eur": 0.0,
        "igic_pct": float(igic_default),
        "incluye_igic": False,
        META_KEY: str(uuid.uuid4()),
        META_ALB_LN: "",
        META_ALB_DOC: "",
        META_PROD_ID: "",
    }


def sincronizar_precios_fila(
    row: dict[str, Any],
    *,
    campo_editado: str | None = None,
    prev: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bidireccional: unitario ↔ total según cantidad y campo editado.

    - Si cambia ``precio_total`` (y qty > 0) → unitario = total / qty.
    - Si cambia ``precio_unitario`` o ``cantidad`` → total = unitario × qty.
    - Si ``campo_editado`` es None, infiere comparando con ``prev``.
    """
    out = dict(row)
    qty = celda_numero(out.get("cantidad"))
    unit = celda_numero(out.get("precio_unitario"))
    total = celda_numero(out.get("precio_total"))

    edited = campo_editado
    if edited is None and prev is not None:
        try:
            if celda_numero(prev.get("precio_total")) != total:
                edited = "precio_total"
            elif celda_numero(prev.get("precio_unitario")) != unit:
                edited = "precio_unitario"
            elif celda_numero(prev.get("cantidad")) != qty:
                edited = "cantidad"
        except Exception:  # noqa: BLE001
            edited = None

    if qty > 0 and edited == "precio_total":
        out["precio_unitario"] = float(money_round(as_decimal(total) / as_decimal(qty)))
        out["precio_total"] = float(money_round(as_decimal(total)))
    elif qty > 0 and edited in ("precio_unitario", "cantidad", None):
        # Default: unitario manda (también al cargar / sin prev)
        if edited is None and total > 0 and unit == 0:
            out["precio_unitario"] = float(
                money_round(as_decimal(total) / as_decimal(qty))
            )
        else:
            out["precio_total"] = float(
                money_round(as_decimal(celda_numero(out.get("precio_unitario"))) * as_decimal(qty))
            )
    elif qty <= 0:
        out["precio_total"] = 0.0

    return out


def sincronizar_precios_filas(
    rows: list[dict[str, Any]],
    prev_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    prev_by_key: dict[str, dict] = {}
    if prev_rows:
        for p in prev_rows:
            k = celda_texto(p.get(META_KEY))
            if k:
                prev_by_key[k] = p
    out: list[dict[str, Any]] = []
    for row in rows:
        k = celda_texto(row.get(META_KEY))
        out.append(sincronizar_precios_fila(row, prev=prev_by_key.get(k)))
    return out


def fila_tiene_producto(row: dict[str, Any]) -> bool:
    prod = celda_texto(row.get("producto"))
    pid = celda_texto(row.get(META_PROD_ID))
    return bool(prod or pid)


def _fila_tenia_producto(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    return fila_tiene_producto(row)


def purgar_filas_sin_producto(
    rows: list[dict[str, Any]],
    prev_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Elimina filas cuyo producto se vació (p. ej. Retroceso en la celda).

    - Si una fila tenía producto/id y ahora está vacía → se elimina.
    - Conserva **todas** las plantillas vacías (add row mientras se rellena).
    - Siempre deja al menos una fila vacía para poder añadir.
    """
    prev_by_key: dict[str, dict[str, Any]] = {}
    if prev_rows:
        for p in prev_rows:
            k = celda_texto(p.get(META_KEY))
            if k:
                prev_by_key[k] = p

    kept: list[dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        label = celda_texto(out.get("producto"))
        out["producto"] = label
        out["unidad"] = celda_texto(out.get("unidad")) or "Ud"
        out["cantidad"] = celda_numero(out.get("cantidad"))
        out["precio_unitario"] = celda_numero(out.get("precio_unitario"))
        out["precio_total"] = celda_numero(out.get("precio_total"))
        out["dto_pct"] = celda_numero(out.get("dto_pct"))
        out["dto_eur"] = celda_numero(out.get("dto_eur"))
        out["igic_pct"] = celda_numero(out.get("igic_pct"), 7.0)
        if not label:
            out[META_PROD_ID] = ""
            k = celda_texto(out.get(META_KEY))
            prev = prev_by_key.get(k)
            if _fila_tenia_producto(prev):
                continue
            kept.append(out)
            continue
        kept.append(out)

    if not any(not fila_tiene_producto(r) for r in kept):
        kept.append(empty_row())
    return kept


def filas_a_entradas_calculo(
    rows: list[dict[str, Any]],
) -> list[EntradaLineaCalculo]:
    entradas: list[EntradaLineaCalculo] = []
    for row in rows:
        if not fila_tiene_producto(row):
            continue
        qty = as_decimal(celda_numero(row.get("cantidad")))
        if qty <= 0:
            continue
        entradas.append(
            EntradaLineaCalculo(
                cantidad_compra=qty,
                precio_unitario_compra=celda_numero(row.get("precio_unitario")),
                factor_conversion=1,
                precio_incluye_igic=bool(row.get("incluye_igic")),
                impuesto_porcentaje=celda_numero(row.get("igic_pct")),
                descuento_linea_porcentaje=celda_numero(row.get("dto_pct")),
                descuento_linea_importe=celda_numero(row.get("dto_eur")),
                linea_id=celda_texto(row.get(META_KEY)),
            )
        )
    return entradas


def calcular_totales_grid(
    rows: list[dict[str, Any]],
    *,
    descuento_cabecera: float | Decimal | str = 0,
) -> ResultadoDocumento | None:
    entradas = filas_a_entradas_calculo(rows)
    if not entradas:
        return None
    return calcular_documento(
        entradas, descuento_cabecera_importe=descuento_cabecera
    )


def totales_a_dict(res: ResultadoDocumento | None) -> dict[str, Any]:
    if res is None:
        return {
            "base_imponible": "0.00",
            "impuesto_total": "0.00",
            "total_documento": "0.00",
            "desglose": [],
        }
    return {
        "base_imponible": f"{res.base_imponible:.2f}",
        "impuesto_total": f"{res.impuesto_total:.2f}",
        "total_documento": f"{res.total_documento:.2f}",
        "desglose": [
            {
                "porcentaje": f"{d.porcentaje:g}",
                "base": f"{d.base:.2f}",
                "cuota": f"{d.cuota:.2f}",
            }
            for d in res.desglose_impuestos
        ],
    }


def _unidad_producto(prod) -> str:
    u = getattr(prod, "unidad", None)
    if u is None:
        return "Ud"
    return u.value if hasattr(u, "value") else str(u)


def lineas_documento_a_filas(
    doc,
    *,
    mapa_prod_por_id: dict[str, Any],
    mapa_label_por_id: dict[str, str],
) -> list[dict[str, Any]]:
    """Precarga rejilla desde líneas persistidas."""
    rows: list[dict[str, Any]] = []
    for ln in getattr(doc, "lineas", []) or []:
        prod = mapa_prod_por_id.get(ln.producto_id)
        label = mapa_label_por_id.get(ln.producto_id, ln.producto_id)
        qty = float(as_decimal(ln.cantidad_compra if ln.cantidad_compra is not None else ln.cantidad))
        unit_p = float(
            as_decimal(ln.precio_unitario_compra if ln.precio_unitario_compra is not None else 0)
        )
        if unit_p <= 0 and qty > 0 and ln.precio_total:
            unit_p = float(money_round(as_decimal(ln.precio_total) / as_decimal(qty)))
        total = float(money_round(as_decimal(unit_p) * as_decimal(qty))) if qty > 0 else 0.0
        unidad = ln.unidad_compra or ( _unidad_producto(prod) if prod else "Ud")
        igic = float(
            as_decimal(
                ln.impuesto_porcentaje_snapshot
                if ln.impuesto_porcentaje_snapshot is not None
                else 7
            )
        )
        rows.append(
            {
                "producto": label,
                "cantidad": qty,
                "unidad": unidad,
                "precio_unitario": unit_p,
                "precio_total": total,
                "dto_pct": float(as_decimal(ln.descuento_porcentaje or 0)),
                "dto_eur": float(as_decimal(ln.descuento_importe or 0)),
                "igic_pct": igic,
                "incluye_igic": bool(getattr(ln, "precio_incluye_igic", False)),
                META_KEY: ln.client_line_key or str(uuid.uuid4()),
                META_ALB_LN: getattr(ln, "linea_origen_id", None) or "",
                META_ALB_DOC: getattr(ln, "documento_origen_id", None) or "",
                META_PROD_ID: ln.producto_id,
            }
        )
    if not rows:
        rows.append(empty_row())
    return rows


def filas_a_payload_lineas(
    rows: list[dict[str, Any]],
    *,
    mapa_prod_por_label: dict[str, Any],
) -> list[dict[str, Any]]:
    """Mapea rejilla → dicts para ``guardar_borrador`` (sin factor explícito)."""
    out: list[dict[str, Any]] = []
    for row in rows:
        label = celda_texto(row.get("producto"))
        prod = mapa_prod_por_label.get(label)
        pid = celda_texto(row.get(META_PROD_ID))
        if prod is None and pid:
            # fallback si label vacío pero hay id
            for p in mapa_prod_por_label.values():
                if p.id == pid:
                    prod = p
                    break
        if prod is None:
            continue
        qty = as_decimal(celda_numero(row.get("cantidad")))
        if qty <= 0:
            continue
        synced = sincronizar_precios_fila(row, campo_editado="precio_unitario")
        unidad_inv = _unidad_producto(prod)
        unidad_compra = celda_texto(row.get("unidad")) or unidad_inv
        clk = celda_texto(row.get(META_KEY)) or str(uuid.uuid4())
        payload: dict[str, Any] = {
            "producto_id": prod.id,
            "client_line_key": clk,
            "cantidad_compra": str(qty),
            "unidad_compra": unidad_compra,
            "unidad_inventario": unidad_inv,
            "factor_conversion": None,
            "precio_unitario_compra": str(celda_numero(synced.get("precio_unitario"))),
            "precio_incluye_igic": bool(row.get("incluye_igic")),
            "descuento_porcentaje": str(celda_numero(row.get("dto_pct"))),
            "descuento_importe": str(celda_numero(row.get("dto_eur"))),
            "impuesto_porcentaje": str(celda_numero(row.get("igic_pct"), 7.0)),
        }
        alb_ln = celda_texto(row.get(META_ALB_LN))
        alb_doc = celda_texto(row.get(META_ALB_DOC))
        if alb_ln:
            payload["linea_origen_id"] = alb_ln
        if alb_doc:
            payload["documento_origen_id"] = alb_doc
        out.append(payload)
    return out


def filas_a_conciliaciones(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conc: list[dict[str, Any]] = []
    for row in rows:
        alb_ln = celda_texto(row.get(META_ALB_LN))
        if not alb_ln:
            continue
        qty = as_decimal(celda_numero(row.get("cantidad")))
        if qty <= 0:
            continue
        clk = celda_texto(row.get(META_KEY))
        if not clk:
            continue
        conc.append(
            {
                "linea_factura_client_key": clk,
                "linea_albaran_id": alb_ln,
                "cantidad_conciliada": str(qty),
            }
        )
    return conc


def _linea_conciliada_activa(data, linea_albaran_id: str) -> bool:
    for c in getattr(data, "conciliaciones_documento", []) or []:
        if c.linea_albaran_id != linea_albaran_id:
            continue
        est = c.estado.value if hasattr(c.estado, "value") else str(c.estado)
        if est == EstadoConciliacion.ACTIVA.value:
            return True
    return False


def _estado_val(doc) -> str:
    e = doc.estado
    return e.value if hasattr(e, "value") else str(e)


def _tipo_val(doc) -> str:
    t = doc.tipo
    return t.value if hasattr(t, "value") else str(t)


def albaranes_conciliables(
    data,
    *,
    proveedor_id: str,
    excluir_factura_id: str | None = None,
) -> list[Any]:
    """Albaranes confirmados del proveedor con al menos una línea libre."""
    out = []
    for d in getattr(data, "documentos", []) or []:
        if _tipo_val(d) != TipoDocumento.ALBARAN.value:
            continue
        if _estado_val(d) != EstadoDocumento.CONFIRMADO.value:
            continue
        if (d.proveedor_id or "") != proveedor_id:
            continue
        libres = lineas_libres_albaran(
            data, d, excluir_factura_id=excluir_factura_id
        )
        if libres:
            out.append(d)
    return sorted(out, key=lambda x: (x.fecha_documento, x.id), reverse=True)


def lineas_libres_albaran(
    data,
    alb,
    *,
    excluir_factura_id: str | None = None,
) -> list[Any]:
    libres = []
    for ln in alb.lineas:
        if linea_albaran_ya_conciliada(
            data, ln.id, excluir_factura_id=excluir_factura_id
        ):
            continue
        if _linea_conciliada_activa(data, ln.id):
            continue
        libres.append(ln)
    return libres


def expandir_albaranes_a_filas(
    data,
    albaranes: list[Any],
    *,
    mapa_label_por_id: dict[str, str],
    mapa_prod_por_id: dict[str, Any],
    excluir_factura_id: str | None = None,
    igic_default: float = 7.0,
) -> list[dict[str, Any]]:
    """Una fila de factura por cada línea libre de los albaranes."""
    rows: list[dict[str, Any]] = []
    for alb in albaranes:
        for ln in lineas_libres_albaran(
            data, alb, excluir_factura_id=excluir_factura_id
        ):
            prod = mapa_prod_por_id.get(ln.producto_id)
            label = mapa_label_por_id.get(
                ln.producto_id,
                getattr(ln, "producto_nombre_snapshot", None) or ln.producto_id,
            )
            qty = float(
                as_decimal(
                    ln.cantidad_compra
                    if ln.cantidad_compra is not None
                    else ln.cantidad
                )
            )
            unit_p = float(
                as_decimal(
                    ln.precio_unitario_compra
                    if ln.precio_unitario_compra is not None
                    else 0
                )
            )
            if unit_p <= 0 and qty > 0:
                # legacy: precio_total es total de línea
                unit_p = float(
                    money_round(as_decimal(ln.precio_total or 0) / as_decimal(qty))
                )
            total = float(money_round(as_decimal(unit_p) * as_decimal(qty)))
            unidad = ln.unidad_compra or (
                _unidad_producto(prod) if prod else "Ud"
            )
            igic = float(
                as_decimal(
                    ln.impuesto_porcentaje_snapshot
                    if ln.impuesto_porcentaje_snapshot is not None
                    else igic_default
                )
            )
            rows.append(
                {
                    "producto": label,
                    "cantidad": qty,
                    "unidad": unidad,
                    "precio_unitario": unit_p,
                    "precio_total": total,
                    "dto_pct": float(as_decimal(ln.descuento_porcentaje or 0)),
                    "dto_eur": float(as_decimal(ln.descuento_importe or 0)),
                    "igic_pct": igic,
                    "incluye_igic": bool(getattr(ln, "precio_incluye_igic", False)),
                    META_KEY: str(uuid.uuid4()),
                    META_ALB_LN: ln.id,
                    META_ALB_DOC: alb.id,
                    META_PROD_ID: ln.producto_id,
                }
            )
    return rows


def agrupar_filas_por_albaran(
    rows: list[dict[str, Any]],
    *,
    mapa_alb: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Agrupa filas con enlace a albarán para vista resumen.

    Cada grupo: ``{alb_id, etiqueta, total, productos: [nombres]}``.
    """
    grupos: dict[str, dict[str, Any]] = {}
    for row in rows:
        alb_id = celda_texto(row.get(META_ALB_DOC))
        if not alb_id:
            continue
        g = grupos.get(alb_id)
        if g is None:
            alb = (mapa_alb or {}).get(alb_id)
            ref = getattr(alb, "referencia_externa", None) if alb else None
            etiqueta = f"Albarán {ref or alb_id}"
            g = {"alb_id": alb_id, "etiqueta": etiqueta, "total": Decimal("0"), "productos": []}
            grupos[alb_id] = g
        g["total"] += as_decimal(celda_numero(row.get("precio_total")))
        nombre = celda_texto(row.get("producto")) or "?"
        # quitar sufijo [código] (id) si es label largo
        if " (" in nombre:
            nombre = nombre.split(" (")[0]
        if " [" in nombre:
            nombre = nombre.split(" [")[0]
        if nombre not in g["productos"]:
            g["productos"].append(nombre)
    out = []
    for g in grupos.values():
        out.append(
            {
                "alb_id": g["alb_id"],
                "etiqueta": g["etiqueta"],
                "total": f"{money_round(g['total']):.2f}",
                "productos": ", ".join(g["productos"]),
            }
        )
    return out


def etiqueta_albaran(alb) -> str:
    ref = alb.referencia_externa or "—"
    total = alb.total_documento
    total_s = f"{total:.2f} €" if total is not None else "—"
    n = len(alb.lineas or [])
    return f"{alb.id} · ref={ref} · {n} líns · total={total_s}"
