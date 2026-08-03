"""Movimiento de inventario — ledger append-only (Fase 7A).

Complementario a LoteStock.cantidad_restante (fuente de verdad operativa).
Cantidad siempre > 0; el sentido lo da ``direccion``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from app.core.models.enums import DireccionMovimiento, TipoMovimiento


@dataclass
class MovimientoInventario:
    """Variación trazable de inventario asociada a un lote (espejo)."""

    id: str
    producto_id: str
    lote_id: str
    tipo: TipoMovimiento | str
    direccion: DireccionMovimiento | str
    cantidad: float
    fecha: date
    hora: time | None
    origen_tipo: str
    origen_id: str
    origen_linea_id: str | None = None
    movimiento_revertido_id: str | None = None
    usuario_id: str | None = None
    idempotency_key: str | None = None
    coste_unitario_snapshot: float | None = None
    coste_total_snapshot: float | None = None
    creado_en: datetime | None = None

    @property
    def cantidad_firmada(self) -> float:
        """Derivada: +cantidad si entrada, −cantidad si salida."""
        dir_val = (
            self.direccion.value
            if hasattr(self.direccion, "value")
            else str(self.direccion)
        )
        if dir_val == DireccionMovimiento.ENTRADA.value:
            return float(self.cantidad)
        if dir_val == DireccionMovimiento.SALIDA.value:
            return -float(self.cantidad)
        return 0.0
