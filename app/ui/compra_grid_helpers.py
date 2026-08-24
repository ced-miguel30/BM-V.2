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


def parsear_numero_es(valor: Any, default: float = 0.0) -> float:
    """Parsea número en formato contable ES (1.234,56) o float/inglés.

    - ``10,00`` → 10.0
    - ``10.000`` → 10000.0
    - ``10.000,50`` → 10000.5
    - También acepta ``10.5`` / ``10000.5`` (punto decimal anglosajón).
    """
    if valor is None:
        return default
    if isinstance(valor, bool):
        return default
    if isinstance(valor, (int, float)):
        if isinstance(valor, float) and math.isnan(valor):
            return default
        return float(valor)
    if isinstance(valor, Decimal):
        return float(valor)

    texto = celda_texto(valor)
    if not texto:
        return default
    texto = (
        texto.replace("€", "")
        .replace("\u00a0", "")
        .replace(" ", "")
        .replace("%", "")
    )
    if not texto or texto in {".", ",", "-", "-.", "-,"}:
        return default

    try:
        if "," in texto and "." in texto:
            if texto.rfind(",") > texto.rfind("."):
                # ES: 1.234,56
                texto = texto.replace(".", "").replace(",", ".")
            else:
                # EN: 1,234.56
                texto = texto.replace(",", "")
        elif "," in texto:
            # ES: coma decimal (10,00)
            texto = texto.replace(",", ".")
        elif "." in texto:
            partes = texto.split(".")
            # Solo miles ES: 10.000 / 1.234.567 (grupos de 3)
            if len(partes) > 1 and all(p.lstrip("-").isdigit() for p in partes):
                if all(len(p) == 3 for p in partes[1:]):
                    texto = texto.replace(".", "")
        return float(as_decimal(texto))
    except Exception:  # noqa: BLE001
        return default


def formatear_numero_es(valor: Any, *, decimales: int = 2) -> str:
    """Formato contable español: ``10,00`` / ``10.000,50``."""
    n = parsear_numero_es(valor, 0.0)
    if decimales < 0:
        decimales = 0
    q = Decimal(str(n)).quantize(Decimal(10) ** -decimales)
    sign = "-" if q < 0 else ""
    q = abs(q)
    raw = f"{q:.{decimales}f}"
    if decimales > 0:
        entero, frac = raw.split(".")
    else:
        entero, frac = raw, ""
    # Miles con punto
    neg = entero.startswith("-")
    digitos = entero[1:] if neg else entero
    grupos: list[str] = []
    while digitos:
        grupos.insert(0, digitos[-3:])
        digitos = digitos[:-3]
    entero_fmt = ".".join(grupos) if grupos else "0"
    if frac:
        return f"{sign}{entero_fmt},{frac}"
    return f"{sign}{entero_fmt}"


def celda_numero(valor: Any, default: float = 0.0) -> float:
    """Número seguro; acepta NaN / None / texto ES o EN → float."""
    return parsear_numero_es(valor, default)


# Columnas numéricas mostradas como texto ES en el editor
GRID_NUM_FMT: dict[str, int] = {
    "cantidad": 2,
    "precio_unitario": 2,
    "precio_total": 2,
    "dto_pct": 2,
    "dto_eur": 2,
    "igic_pct": 2,
}


def fila_numeros_a_texto_es(row: dict[str, Any]) -> dict[str, Any]:
    """Copia de fila con importes/cantidades en texto contable ES (para data_editor)."""
    out = dict(row)
    for col, dec in GRID_NUM_FMT.items():
        if col in out:
            out[col] = formatear_numero_es(out.get(col), decimales=dec)
    return out


def filas_precios_distintas(
    a: list[dict[str, Any]],
    b: list[dict[str, Any]],
    *,
    eps: float = 1e-9,
) -> bool:
    """True si unitario/total/cantidad difieren (hace falta refrescar celdas)."""
    if len(a) != len(b):
        return True
    for ra, rb in zip(a, b):
        for col in ("cantidad", "precio_unitario", "precio_total"):
            if abs(celda_numero(ra.get(col)) - celda_numero(rb.get(col))) > eps:
                return True
    return False


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
            if abs(celda_numero(prev.get("precio_total")) - total) > 1e-9:
                edited = "precio_total"
            elif abs(celda_numero(prev.get("precio_unitario")) - unit) > 1e-9:
                edited = "precio_unitario"
            elif abs(celda_numero(prev.get("cantidad")) - qty) > 1e-9:
                edited = "cantidad"
        except Exception:  # noqa: BLE001
            edited = None

    if qty <= 0:
        # No dividir (evita NaN/Infinity) y no pisar unitario/total al vaciar cantidad.
        return out

    if edited == "precio_total":
        # Vaciar/cero el total no debe destruir el unitario (edición a medias).
        if total <= 0:
            return out
        out["precio_unitario"] = float(
            money_round(as_decimal(total) / as_decimal(qty))
        )
        out["precio_total"] = float(money_round(as_decimal(total)))
    elif edited == "precio_unitario":
        if unit <= 0:
            return out
        out["precio_total"] = float(
            money_round(as_decimal(unit) * as_decimal(qty))
        )
    elif edited == "cantidad":
        # Al cambiar cantidad se conserva el unitario y se recalcula el total.
        out["precio_total"] = float(
            money_round(as_decimal(unit) * as_decimal(qty))
        )
    elif edited is None:
        # Sin campo editado: solo corregir inconsistencias (no reescribir siempre)
        if total > 0 and unit == 0:
            out["precio_unitario"] = float(
                money_round(as_decimal(total) / as_decimal(qty))
            )
        elif unit > 0:
            esperado = float(money_round(as_decimal(unit) * as_decimal(qty)))
            if abs(esperado - total) > 1e-9:
                out["precio_total"] = esperado

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
    *,
    mapa_prod_por_label: dict[str, Any] | None = None,
    mapa_prod_por_id: dict[str, Any] | None = None,
    data: Any | None = None,
    proveedor_id: str | None = None,
) -> list[EntradaLineaCalculo]:
    """Construye entradas monetarias resolviendo el factor con la misma regla
    productiva que borrador/confirmación (``resolver_factor_conversion``).

    Sin ``data``/mapa (llamadas legacy de test con unidades iguales) se usa
    factor 1 solo cuando no hay contexto de catálogo; nunca se fuerza 1 si
    el contexto indica unidades distintas sin factor.
    """
    from app.core.services.conversion_compra import (
        ConversionDesconocidaError,
        obtener_factor_catalogo,
        resolver_factor_conversion,
    )

    entradas: list[EntradaLineaCalculo] = []
    for row in rows:
        if not fila_tiene_producto(row):
            continue
        qty = as_decimal(celda_numero(row.get("cantidad")))
        if qty <= 0:
            continue
        prod = _producto_de_fila(
            row,
            mapa_prod_por_label=mapa_prod_por_label,
            mapa_prod_por_id=mapa_prod_por_id,
        )
        unidad_inv = _unidad_producto(prod) if prod else (
            celda_texto(row.get("unidad")) or "Ud"
        )
        unidad_compra = celda_texto(row.get("unidad")) or unidad_inv
        factor_explicito = row.get("_factor_conversion")
        factor_cat = None
        if data is not None and prod is not None:
            factor_cat = obtener_factor_catalogo(
                data,
                producto_id=prod.id,
                proveedor_id=proveedor_id,
            )
        try:
            if data is None and prod is None and factor_explicito is None:
                factor: Decimal | float | str = 1
            else:
                factor = resolver_factor_conversion(
                    unidad_compra=unidad_compra,
                    unidad_inventario=unidad_inv,
                    factor_explicito=factor_explicito,
                    factor_catalogo=factor_cat,
                )
        except (ConversionDesconocidaError, ValueError):
            raise
        entradas.append(
            EntradaLineaCalculo(
                cantidad_compra=qty,
                precio_unitario_compra=celda_numero(row.get("precio_unitario")),
                factor_conversion=factor,
                precio_incluye_igic=bool(row.get("incluye_igic")),
                impuesto_porcentaje=celda_numero(row.get("igic_pct")),
                descuento_linea_porcentaje=celda_numero(row.get("dto_pct")),
                descuento_linea_importe=celda_numero(row.get("dto_eur")),
                linea_id=celda_texto(row.get(META_KEY)),
            )
        )
    return entradas


def diagnostico_conversion_filas(
    rows: list[dict[str, Any]],
    *,
    mapa_prod_por_label: dict[str, Any] | None = None,
    mapa_prod_por_id: dict[str, Any] | None = None,
    data: Any | None = None,
    proveedor_id: str | None = None,
) -> list[dict[str, Any]]:
    """Resumen por línea: equivalencia, qty inventariable, coste/ud base o error."""
    from app.core.services.conversion_compra import (
        ConversionDesconocidaError,
        obtener_factor_catalogo,
        resolver_factor_conversion,
        texto_equivalencia,
    )
    from app.core.services.money import calcular_linea

    out: list[dict[str, Any]] = []
    for row in rows:
        if not fila_tiene_producto(row):
            continue
        qty = as_decimal(celda_numero(row.get("cantidad")))
        if qty <= 0:
            continue
        prod = _producto_de_fila(
            row,
            mapa_prod_por_label=mapa_prod_por_label,
            mapa_prod_por_id=mapa_prod_por_id,
        )
        nombre = celda_texto(row.get("producto")) or (
            getattr(prod, "nombre", None) if prod else "?"
        )
        unidad_inv = _unidad_producto(prod) if prod else (
            celda_texto(row.get("unidad")) or "Ud"
        )
        unidad_compra = celda_texto(row.get("unidad")) or unidad_inv
        factor_cat = None
        if data is not None and prod is not None:
            factor_cat = obtener_factor_catalogo(
                data,
                producto_id=prod.id,
                proveedor_id=proveedor_id,
            )
        try:
            factor = resolver_factor_conversion(
                unidad_compra=unidad_compra,
                unidad_inventario=unidad_inv,
                factor_explicito=row.get("_factor_conversion"),
                factor_catalogo=factor_cat,
            )
            calc = calcular_linea(
                cantidad_compra=qty,
                precio_unitario_compra=celda_numero(row.get("precio_unitario")),
                factor_conversion=factor,
                precio_incluye_igic=bool(row.get("incluye_igic")),
                impuesto_porcentaje=celda_numero(row.get("igic_pct")),
                descuento_linea_porcentaje=celda_numero(row.get("dto_pct")),
                descuento_linea_importe=celda_numero(row.get("dto_eur")),
            )
            out.append(
                {
                    "producto": nombre,
                    "cantidad_compra": qty,
                    "unidad_compra": unidad_compra,
                    "unidad_base": unidad_inv,
                    "factor": factor,
                    "equivalencia": texto_equivalencia(
                        unidad_compra, factor, unidad_inv
                    ),
                    "cantidad_inventario": calc.cantidad_inventario,
                    "coste_linea": calc.coste_inventariable_linea,
                    "coste_unitario_base": calc.coste_unitario_inventario,
                    "error": None,
                }
            )
        except (ConversionDesconocidaError, ValueError) as exc:
            out.append(
                {
                    "producto": nombre,
                    "cantidad_compra": qty,
                    "unidad_compra": unidad_compra,
                    "unidad_base": unidad_inv,
                    "factor": None,
                    "equivalencia": "",
                    "cantidad_inventario": None,
                    "coste_linea": None,
                    "coste_unitario_base": None,
                    "error": str(exc),
                }
            )
    return out


def _producto_de_fila(
    row: dict[str, Any],
    *,
    mapa_prod_por_label: dict[str, Any] | None = None,
    mapa_prod_por_id: dict[str, Any] | None = None,
) -> Any | None:
    label = celda_texto(row.get("producto"))
    if mapa_prod_por_label and label and label in mapa_prod_por_label:
        return mapa_prod_por_label[label]
    pid = celda_texto(row.get(META_PROD_ID))
    if mapa_prod_por_id and pid and pid in mapa_prod_por_id:
        return mapa_prod_por_id[pid]
    if mapa_prod_por_label and pid:
        for p in mapa_prod_por_label.values():
            if getattr(p, "id", None) == pid:
                return p
    return None


def aplicar_defaults_vinculo_fila(
    row: dict[str, Any],
    prod: Any,
    *,
    data: Any | None = None,
    proveedor_id: str | None = None,
    forzar_unidad: bool = False,
) -> dict[str, Any]:
    """Rellena unidad (y precio ref.) desde el vínculo activo si aplica."""
    from app.core.services.conversion_compra import (
        obtener_unidad_compra_catalogo,
        relacion_activa,
    )

    out = dict(row)
    out[META_PROD_ID] = prod.id
    ub = _unidad_producto(prod)
    uc_cat = obtener_unidad_compra_catalogo(
        data, producto_id=prod.id, proveedor_id=proveedor_id
    )
    if forzar_unidad:
        out["unidad"] = uc_cat or ub
    elif not celda_texto(out.get("unidad")):
        out["unidad"] = uc_cat or ub
    rel = relacion_activa(data, producto_id=prod.id, proveedor_id=proveedor_id)
    if rel is not None and getattr(rel, "ultimo_precio_unitario_compra", None) is not None:
        if as_decimal(celda_numero(out.get("precio_unitario"))) <= 0:
            out["precio_unitario"] = float(rel.ultimo_precio_unitario_compra)
    return out


def calcular_totales_grid(
    rows: list[dict[str, Any]],
    *,
    descuento_cabecera: float | Decimal | str = 0,
    mapa_prod_por_label: dict[str, Any] | None = None,
    mapa_prod_por_id: dict[str, Any] | None = None,
    data: Any | None = None,
    proveedor_id: str | None = None,
) -> ResultadoDocumento | None:
    from app.core.services.conversion_compra import ConversionDesconocidaError

    try:
        entradas = filas_a_entradas_calculo(
            rows,
            mapa_prod_por_label=mapa_prod_por_label,
            mapa_prod_por_id=mapa_prod_por_id,
            data=data,
            proveedor_id=proveedor_id,
        )
    except (ConversionDesconocidaError, ValueError):
        return None
    if not entradas:
        return None
    return calcular_documento(
        entradas, descuento_cabecera_importe=descuento_cabecera
    )


def totales_a_dict(res: ResultadoDocumento | None) -> dict[str, Any]:
    if res is None:
        return {
            "base_imponible": formatear_numero_es(0),
            "impuesto_total": formatear_numero_es(0),
            "total_documento": formatear_numero_es(0),
            "desglose": [],
        }
    return {
        "base_imponible": formatear_numero_es(res.base_imponible),
        "impuesto_total": formatear_numero_es(res.impuesto_total),
        "total_documento": formatear_numero_es(res.total_documento),
        "desglose": [
            {
                "porcentaje": formatear_numero_es(d.porcentaje, decimales=2),
                "base": formatear_numero_es(d.base),
                "cuota": formatear_numero_es(d.cuota),
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
    """Líneas con cantidad pendiente de facturar > 0 (soporta parcial)."""
    from app.core.services.compra_pendientes_service import cantidad_pendiente_facturar

    libres = []
    for ln in alb.lineas:
        pend = cantidad_pendiente_facturar(
            data, ln.id, excluir_factura_id=excluir_factura_id, linea=ln
        )
        if pend > 0:
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
    """Una fila de factura por cada línea con pendiente (qty = residual)."""
    from app.core.services.compra_pendientes_service import lineas_pendientes_albaran

    rows: list[dict[str, Any]] = []
    for alb in albaranes:
        for ln, pend in lineas_pendientes_albaran(
            data, alb, excluir_factura_id=excluir_factura_id
        ):
            prod = mapa_prod_por_id.get(ln.producto_id)
            label = mapa_label_por_id.get(
                ln.producto_id,
                getattr(ln, "producto_nombre_snapshot", None) or ln.producto_id,
            )
            # Pendiente está en ud inventario; para grid usamos proporción compra
            recibida_inv = as_decimal(
                ln.cantidad_inventario
                if ln.cantidad_inventario is not None
                else (ln.cantidad_compra if ln.cantidad_compra is not None else ln.cantidad)
            )
            qty_compra = as_decimal(
                ln.cantidad_compra
                if ln.cantidad_compra is not None
                else ln.cantidad
            )
            if recibida_inv > 0 and qty_compra > 0:
                qty = float(money_round(qty_compra * (pend / recibida_inv)))
            else:
                qty = float(pend)
            if qty <= 0:
                continue
            unit_p = float(
                as_decimal(
                    ln.precio_unitario_compra
                    if ln.precio_unitario_compra is not None
                    else 0
                )
            )
            if unit_p <= 0 and qty > 0:
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
                    META_KEY: str(uuid.uuid4()),
                    META_ALB_LN: ln.id,
                    META_ALB_DOC: alb.id,
                    META_PROD_ID: ln.producto_id,
                    "producto_id": ln.producto_id,
                    "producto": label,
                    "cantidad": qty,
                    "unidad": unidad,
                    "precio_unitario": unit_p,
                    "precio_total": total,
                    "dto_pct": float(as_decimal(ln.descuento_porcentaje or 0)),
                    "dto_eur": float(as_decimal(ln.descuento_importe or 0)),
                    "igic_pct": igic,
                    "incluye_igic": bool(ln.precio_incluye_igic),
                    "total": total,
                    "pendiente_facturar": float(pend),
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
                "total": formatear_numero_es(money_round(g["total"])),
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
