"""Modelos de registro de servicio (comida, cena, bebidas) y detalle de origen."""

from dataclasses import dataclass, field
from datetime import date, time


@dataclass
class ConsumoLoteDetalle:
    """Fragmento de descuento FIFO atribuido a una línea de detalle (Fase 10.5)."""

    lote_id: str
    producto_id: str
    cantidad: float
    coste: float


@dataclass
class LineaDetalleOrigen:
    """Consumo individual con origen explícito para análisis futuros.

    No fusiona irreversible directo + receta: si el mismo producto aparece
    como producto suelto y como ingrediente, hay dos líneas de detalle.
    """

    origen: str  # OrigenConsumo.value
    producto_id: str
    cantidad: float
    coste: float = 0.0
    receta_origen_id: str | None = None
    registro_origen_id: str | None = None
    tipo_servicio: str = ""
    # Legacy / espejo; preferir categoria_receta_snapshot en análisis.
    categoria_receta: str | None = None
    # Snapshots al registrar (aditivos; antiguos → None → fallback catálogo).
    es_bebida_snapshot: bool | None = None
    categoria_receta_snapshot: str | None = None
    # Desglose FIFO por lote (aditivo; históricos → []).
    consumos_lote: list[ConsumoLoteDetalle] = field(default_factory=list)


@dataclass
class LineaServicio:
    producto_id: str
    cantidad: float
    coste: float
    es_extra: bool = False


@dataclass
class ExtraRecetaServicio:
    producto_id: str
    cantidad: float


@dataclass
class OmisionRecetaServicio:
    producto_id: str


@dataclass
class RegistroRecetaServicio:
    receta_id: str
    nombre_receta: str
    porciones: float
    extras: list[ExtraRecetaServicio] = field(default_factory=list)
    omisiones: list[OmisionRecetaServicio] = field(default_factory=list)
    categoria_receta: str | None = None
    categoria_receta_snapshot: str | None = None
    # Snapshots Fase 8 (aditivos; históricos → None).
    porciones_estandar_snapshot: float | None = None
    factor_aplicado: float | None = None


@dataclass
class RegistroServicio:
    id: str
    tipo_servicio: str
    fecha: date
    lineas: list[LineaServicio] = field(default_factory=list)
    coste_total: float = 0.0
    registrado_por: str = ""
    num_huespedes: int = 0
    registros_recetas: list[RegistroRecetaServicio] = field(default_factory=list)
    hora: time | None = None
    lineas_detalle: list[LineaDetalleOrigen] = field(default_factory=list)
    # Fase 11A — soft-delete (aditivo; históricos → False / vacíos).
    anulado: bool = False
    fecha_anulacion: date | None = None
    hora_anulacion: time | None = None
    motivo_anulacion: str = ""
    referencia_anulacion: str = ""
    anulado_por: str = ""
    # Token de confirmación UI (aditivo; históricos → None). Evita doble registro.
    clave_idempotencia: str | None = None
    # Observaciones operativas del registro (aditivo; históricos → "").
    observaciones: str = ""
    # Confirmación manual de revisión operativa (aditivo; históricos → False).
    revision_confirmada: bool = False
    fecha_revision_confirmacion: date | None = None
    hora_revision_confirmacion: time | None = None
    revision_confirmada_por: str = ""
