"""Modelo de recetas con ingredientes de producto."""

from dataclasses import dataclass, field

from app.core.models.enums import CategoriaReceta


@dataclass
class IngredienteReceta:
    # `cantidad` es siempre la cantidad normalizada en la unidad nativa del
    # producto en inventario (kg, L, Ud...): es la que usan el descuento
    # FIFO, el coste y las validaciones de stock, y nunca cambia por elegir
    # otra presentación.
    producto_id: str
    cantidad: float
    # Cantidad y unidad tal como las introdujo el usuario (p. ej. 10 / "gr"),
    # solo para mostrar. Si son `None` (recetas anteriores a esta función) se
    # usa la unidad nativa del producto.
    cantidad_presentacion: float | None = None
    unidad_presentacion: str | None = None


@dataclass
class ExtraSugeridoReceta:
    """Producto ofrecido como extra al servir esta receta (cantidad por defecto)."""

    producto_id: str
    cantidad: float = 1.0


@dataclass
class Receta:
    id: str
    nombre: str
    ingredientes: list[IngredienteReceta] = field(default_factory=list)
    # Categoría obligatoria en la UI; default Desayuno para recetas antiguas
    # y para llamadas internas que aún no pasan el argumento.
    # Distinta de servicios_disponibles (lista de registros donde aparece).
    categoria: CategoriaReceta = CategoriaReceta.DESAYUNO
    # Lista vacía = «No configurado» (no significa «todos»).
    servicios_disponibles: list[str] = field(default_factory=list)
    # Rendimiento base de la receta (Fase 7). None = no configurado (sin backfill).
    porciones_estandar: float | None = None
    # Soft-disable: inactiva no entra en registros nuevos; históricos intactos.
    activo: bool = True
    # Extras configurables (p. ej. huevo extra, cherry tomatoes) con cantidad.
    extras_sugeridos: list[ExtraSugeridoReceta] = field(default_factory=list)
