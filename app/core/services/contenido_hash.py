"""Hash de intención de confirmación (A7 / addendum D87–D88)."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any


def _norm_decimal(value: Any) -> str | None:
    if value is None or value == "":
        return None
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _canon(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, Decimal):
        return _norm_decimal(obj)
    if isinstance(obj, (int, float)):
        # float no debe entrar en hash monetario; normalizar vía str
        return _norm_decimal(obj)
    if isinstance(obj, dict):
        return {k: _canon(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, (list, tuple)):
        return [_canon(x) for x in obj]
    return obj


def contenido_hash_intencion(payload: dict) -> str:
    """SHA-256 hex de JSON canónico UTF-8 (claves ordenadas, Decimal normalizado).

    El caller debe construir ``payload`` solo con campos de intención
    (sin ids/timestamps/totales derivados del servidor).
    """
    canon = _canon(payload)
    raw = json.dumps(canon, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def payload_intencion_documento(
    *,
    tipo: str,
    proveedor_id: str | None,
    referencia_externa: str | None,
    fecha_documento: str | None,
    fecha_recepcion: str | None,
    ubicacion_entrada_id: str | None,
    moneda: str | None,
    descuento_cabecera_importe: Any,
    lineas: list[dict],
    conciliaciones_propuestas: list[dict] | None = None,
) -> dict:
    """Estructura de intención alineada al addendum A5."""
    lineas_ord = sorted(lineas, key=lambda ln: str(ln.get("client_line_key") or ""))
    conc = sorted(
        conciliaciones_propuestas or [],
        key=lambda c: (
            str(c.get("linea_factura_client_key") or c.get("linea_factura_id") or ""),
            str(c.get("linea_albaran_id") or c.get("linea_albaran_client_key") or ""),
        ),
    )
    return {
        "tipo": tipo,
        "proveedor_id": proveedor_id,
        "referencia_externa": referencia_externa,
        "fecha_documento": fecha_documento,
        "fecha_recepcion": fecha_recepcion,
        "ubicacion_entrada_id": ubicacion_entrada_id,
        "moneda": moneda,
        "descuento_cabecera_importe": descuento_cabecera_importe,
        "lineas": lineas_ord,
        "conciliaciones_propuestas": conc,
    }
