"""Modelo de configuración del hotel."""

from dataclasses import dataclass

# Modos de saldo (Fase 7B). Valores persistidos en JSON.
LEDGER_BALANCE_MODES = frozenset({"legacy", "shadow", "ledger"})
LEDGER_SCHEMA_VERSION_DEFAULT = 7
LEDGER_QTY_TOLERANCE_DEFAULT = 1e-4


@dataclass
class ConfiguracionHotel:
    nombre_establecimiento: str
    moneda: str
    simbolo_moneda: str = "€"
    logo_path: str | None = None
    # --- Fase 7B: frontera de activación y modo de saldo (aditivos) ---
    ledger_schema_version: int = LEDGER_SCHEMA_VERSION_DEFAULT
    # ISO-8601 datetime persistido; no se re-infiere en cada ejecución.
    ledger_activation_iso: str | None = None
    # legacy | shadow | ledger
    ledger_balance_mode: str = "shadow"
    ledger_qty_tolerance: float = LEDGER_QTY_TOLERANCE_DEFAULT
    # Cóctel del día por weekday Python (lunes=0 … domingo=6). Nombres de receta.
    # Vacío / incompleto → sin cóctel del día configurado.
    cocteles_del_dia: tuple[str, ...] = ()
