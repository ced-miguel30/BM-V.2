"""Configuración y frontera de activación del ledger (Fase 7B).

La frontera se persiste en ``ConfiguracionHotel.ledger_activation_iso``.
No se re-calcula desde «ahora» en cada ejecución.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.models import AppData, ConfiguracionHotel
from app.core.models.configuracion import (
    LEDGER_BALANCE_MODES,
    LEDGER_QTY_TOLERANCE_DEFAULT,
    LEDGER_SCHEMA_VERSION_DEFAULT,
)

LEDGER_ACTIVATION_SOURCE_MOVEMENTS = "derived_once_from_first_movement"
LEDGER_ACTIVATION_SOURCE_EXPLICIT = "explicit"
LEDGER_ACTIVATION_SOURCE_UNSET = "unset"


def tolerancia_cantidad(data: AppData) -> float:
    cfg = data.configuracion
    if cfg is None:
        return LEDGER_QTY_TOLERANCE_DEFAULT
    try:
        return float(getattr(cfg, "ledger_qty_tolerance", LEDGER_QTY_TOLERANCE_DEFAULT))
    except (TypeError, ValueError):
        return LEDGER_QTY_TOLERANCE_DEFAULT


def ledger_balance_mode(data: AppData) -> str:
    cfg = data.configuracion
    if cfg is None:
        return "shadow"
    mode = str(getattr(cfg, "ledger_balance_mode", "shadow") or "shadow").strip().lower()
    if mode not in LEDGER_BALANCE_MODES:
        return "shadow"
    return mode


def ledger_schema_version(data: AppData) -> int:
    cfg = data.configuracion
    if cfg is None:
        return LEDGER_SCHEMA_VERSION_DEFAULT
    try:
        return int(getattr(cfg, "ledger_schema_version", LEDGER_SCHEMA_VERSION_DEFAULT))
    except (TypeError, ValueError):
        return LEDGER_SCHEMA_VERSION_DEFAULT


def parse_activation_datetime(iso: str | None) -> datetime | None:
    if not iso:
        return None
    text = str(iso).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def frontera_activacion(data: AppData) -> datetime | None:
    """Frontera persistida (o None si aún no se ha fijado)."""
    cfg = data.configuracion
    if cfg is None:
        return None
    return parse_activation_datetime(getattr(cfg, "ledger_activation_iso", None))


def _ensure_config(data: AppData) -> ConfiguracionHotel:
    if data.configuracion is None:
        data.configuracion = ConfiguracionHotel(
            nombre_establecimiento="Hotel Boutique",
            moneda="EUR",
            simbolo_moneda="€",
        )
    return data.configuracion


def _earliest_movement_creado(data: AppData) -> datetime | None:
    tiempos: list[datetime] = []
    for m in getattr(data, "movimientos", None) or []:
        creado = getattr(m, "creado_en", None)
        if isinstance(creado, datetime):
            tiempos.append(creado)
        elif creado is not None:
            parsed = parse_activation_datetime(str(creado))
            if parsed is not None:
                tiempos.append(parsed)
    if not tiempos:
        return None
    return min(tiempos)


def asegurar_frontera_activacion(
    data: AppData,
    *,
    explicit_iso: str | None = None,
    persist_mutate: bool = True,
) -> tuple[datetime | None, str]:
    """Garantiza frontera persistida sin re-inferir en cada uso.

    - Si ya hay ``ledger_activation_iso`` → se respeta.
    - Si ``explicit_iso`` se pasa → se persiste una vez.
    - Si hay movimientos y no hay frontera → se deriva **una vez** del
      ``creado_en`` más antiguo y se persiste (no usa datetime.now()).
    - Si no hay movimientos → permanece unset.

    Returns:
        (frontera, fuente)
    """
    cfg = _ensure_config(data) if persist_mutate else data.configuracion
    existing = frontera_activacion(data)
    if existing is not None:
        return existing, LEDGER_ACTIVATION_SOURCE_EXPLICIT

    if explicit_iso:
        parsed = parse_activation_datetime(explicit_iso)
        if parsed is not None and persist_mutate and cfg is not None:
            cfg.ledger_activation_iso = parsed.replace(microsecond=0).isoformat()
            return parsed, LEDGER_ACTIVATION_SOURCE_EXPLICIT
        return parsed, LEDGER_ACTIVATION_SOURCE_EXPLICIT

    earliest = _earliest_movement_creado(data)
    if earliest is not None and persist_mutate:
        cfg = _ensure_config(data)
        cfg.ledger_activation_iso = earliest.replace(microsecond=0).isoformat()
        return earliest, LEDGER_ACTIVATION_SOURCE_MOVEMENTS

    return earliest, (
        LEDGER_ACTIVATION_SOURCE_MOVEMENTS
        if earliest is not None
        else LEDGER_ACTIVATION_SOURCE_UNSET
    )


def fijar_modo_saldo(data: AppData, mode: str) -> None:
    mode_n = str(mode or "").strip().lower()
    if mode_n not in LEDGER_BALANCE_MODES:
        raise ValueError(f"modo de saldo no válido: {mode!r}")
    cfg = _ensure_config(data)
    cfg.ledger_balance_mode = mode_n


def preservable_ledger_fields(cfg: ConfiguracionHotel | None) -> dict[str, Any]:
    """Campos 7B a conservar al guardar nombre/moneda."""
    if cfg is None:
        return {
            "ledger_schema_version": LEDGER_SCHEMA_VERSION_DEFAULT,
            "ledger_activation_iso": None,
            "ledger_balance_mode": "shadow",
            "ledger_qty_tolerance": LEDGER_QTY_TOLERANCE_DEFAULT,
        }
    return {
        "ledger_schema_version": int(
            getattr(cfg, "ledger_schema_version", LEDGER_SCHEMA_VERSION_DEFAULT)
        ),
        "ledger_activation_iso": getattr(cfg, "ledger_activation_iso", None),
        "ledger_balance_mode": str(
            getattr(cfg, "ledger_balance_mode", "shadow") or "shadow"
        ),
        "ledger_qty_tolerance": float(
            getattr(cfg, "ledger_qty_tolerance", LEDGER_QTY_TOLERANCE_DEFAULT)
        ),
    }


def movimiento_es_posterior_activacion(
    data: AppData,
    creado_en: datetime | None,
    *,
    fecha_fallback=None,
) -> bool | None:
    """True si el movimiento es ≥ frontera; None si no hay frontera."""
    frontera = frontera_activacion(data)
    if frontera is None:
        return None
    ref = creado_en
    if ref is None and fecha_fallback is not None:
        # Solo fecha → inicio del día local (conservador: no marcar como post).
        try:
            ref = datetime.combine(fecha_fallback, datetime.min.time())
        except Exception:  # noqa: BLE001
            return None
    if ref is None:
        return None
    # Comparar naive vs aware: normalizar a naive.
    f = frontera.replace(tzinfo=None) if frontera.tzinfo else frontera
    r = ref.replace(tzinfo=None) if getattr(ref, "tzinfo", None) else ref
    return r >= f
