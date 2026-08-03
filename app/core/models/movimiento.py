"""Movimiento de inventario — ledger append-only (Fase 7A / 7B).

Complementario a LoteStock.cantidad_restante hasta activación ledger.
Cantidad siempre > 0; el sentido lo da ``direccion`` (salvo traslado neto 0).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from app.core.models.enums import DireccionMovimiento, TipoMovimiento


@dataclass
class MovimientoInventario:
    """Variación trazable de inventario asociada a un lote."""

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
    # Fase 7B.3 — ubicaciones aditivas (None = histórico / sin ubicación).
    ubicacion_origen_id: str | None = None
    ubicacion_destino_id: str | None = None

    @property
    def cantidad_firmada(self) -> float:
        """Derivada: +cantidad si entrada, −cantidad si salida, 0 si traslado."""
        tipo_val = (
            self.tipo.value if hasattr(self.tipo, "value") else str(self.tipo)
        )
        if tipo_val == "traslado":
            return 0.0
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
