"""Enumeraciones del dominio."""

from enum import Enum


class UnidadProducto(str, Enum):
    UD = "Ud"
    L = "L"
    GR = "gr"
    KG = "Kg"
    OTRO = "Otro"


class RolUsuario(str, Enum):
    OWNER = "Owner"
    ADMIN = "Admin"


class MotivoMerma(str, Enum):
    MERMA = "Merma"
    EXPIRACION = "Expiración"
    PRODUCTO_MALO = "Producto malo"
    PRODUCTO_ABIERTO = "Producto abierto"
    ROTURA = "Rotura"
    SOBRAS = "Sobras"
    ERROR_PREPARACION = "Error de preparación"
    OTRO = "Otro"


class MotivoAjuste(str, Enum):
    """Motivos de ajuste de inventario (Fase 10)."""

    RECONTEO_FISICO = "Reconteo físico"
    ERROR_REGISTRO = "Error de registro"
    OTRO = "Otro"


class TurnoMerma(str, Enum):
    """Turno operativo de la línea de merma (snapshot histórico)."""

    MANANA = "manana"
    TARDE = "tarde"
    NOCHE = "noche"


TURNO_MERMA_LABEL: dict[TurnoMerma, str] = {
    TurnoMerma.MANANA: "Mañana",
    TurnoMerma.TARDE: "Tarde",
    TurnoMerma.NOCHE: "Noche",
}

TURNO_MERMA_VALORES: frozenset[str] = frozenset(t.value for t in TurnoMerma)


class OrigenServicioMerma(str, Enum):
    """Servicio/área donde se produjo la merma (snapshot histórico por línea)."""

    DESAYUNO = "desayuno"
    COMIDA = "comida"
    CENA = "cena"
    BEBIDAS = "bebidas"
    GENERAL = "general"


ORIGEN_SERVICIO_MERMA_LABEL: dict[OrigenServicioMerma, str] = {
    OrigenServicioMerma.DESAYUNO: "Desayuno",
    OrigenServicioMerma.COMIDA: "Comida",
    OrigenServicioMerma.CENA: "Cena",
    OrigenServicioMerma.BEBIDAS: "Bebidas",
    OrigenServicioMerma.GENERAL: "Almacén / General",
}

ORIGEN_SERVICIO_MERMA_VALORES: frozenset[str] = frozenset(
    m.value for m in OrigenServicioMerma
)


class TipoAlerta(str, Enum):
    STOCK_BAJO = "stock_bajo"
    STOCK_CERO = "stock_cero"
    STOCK_NEGATIVO = "stock_negativo"
    EXPIRACION_PROXIMA = "expiracion_proxima"
    EXPIRADO = "expirado"
    MERMA_ELEVADA = "merma_elevada"
    DESAYUNO_NO_REGISTRADO = "desayuno_no_registrado"
    MANUAL = "manual"


class EstadoAlerta(str, Enum):
    PENDIENTE = "pendiente"
    REVISADA = "revisada"
    RESUELTA = "resuelta"
    IGNORADA = "ignorada"


ESTADO_ALERTA_LABEL: dict[EstadoAlerta, str] = {
    EstadoAlerta.PENDIENTE: "Pendiente",
    EstadoAlerta.REVISADA: "Revisada",
    EstadoAlerta.RESUELTA: "Resuelta",
    EstadoAlerta.IGNORADA: "Ignorada",
}


class CategoriaReceta(str, Enum):
    DESAYUNO = "desayuno"
    COMIDA = "comida"
    CENA = "cena"
    BEBIDAS = "bebidas"


CATEGORIA_RECETA_LABEL: dict[CategoriaReceta, str] = {
    CategoriaReceta.DESAYUNO: "Desayuno",
    CategoriaReceta.COMIDA: "Comida",
    CategoriaReceta.CENA: "Cena",
    CategoriaReceta.BEBIDAS: "Bebidas",
}


class OrigenConsumo(str, Enum):
    """Origen explícito de una línea de consumo (no heurístico)."""

    PRODUCTO_DIRECTO = "producto_directo"
    INGREDIENTE_RECETA = "ingrediente_receta"
    EXTRA_RECETA = "extra_receta"


class TipoServicio(str, Enum):
    DESAYUNO = "desayuno"
    COMIDA = "comida"
    CENA = "cena"
    BEBIDAS = "bebidas"


class TipoArticulo(str, Enum):
    """Clasificación fija de producto (Fase 6C). Sin CRUD; taxonomía cerrada."""

    CONSUMIBLE = "consumible"
    REUTILIZABLE = "reutilizable"


TIPO_ARTICULO_LABEL: dict[TipoArticulo, str] = {
    TipoArticulo.CONSUMIBLE: "Consumible",
    TipoArticulo.REUTILIZABLE: "Reutilizable",
}

TIPO_ARTICULO_AYUDA: dict[TipoArticulo, str] = {
    TipoArticulo.CONSUMIBLE: (
        "Se utiliza o agota durante la operación, como alimentos, bebidas, "
        "productos de limpieza o amenities."
    ),
    TipoArticulo.REUTILIZABLE: (
        "Permanece en el hotel y puede usarse varias veces, como vajilla, "
        "menaje o determinados utensilios."
    ),
}

TIPO_ARTICULO_VALORES: frozenset[str] = frozenset(t.value for t in TipoArticulo)


class DireccionMovimiento(str, Enum):
    """Sentido del movimiento de inventario (Fase 7A). Cantidad siempre > 0."""

    ENTRADA = "entrada"
    SALIDA = "salida"


class TipoMovimiento(str, Enum):
    """Tipos del ledger (7A espejo + 7B traslados + 7/10 documentos)."""

    ENTRADA_COMPRA = "entrada_compra"
    ENTRADA_ALBARAN = "entrada_albaran"
    ENTRADA_FACTURA = "entrada_factura"
    CONSUMO = "consumo"
    MERMA = "merma"
    AJUSTE_ENTRADA = "ajuste_entrada"
    AJUSTE_SALIDA = "ajuste_salida"
    REVERSION_CONSUMO = "reversion_consumo"
    REVERSION_MERMA = "reversion_merma"
    REVERSION_ENTRADA = "reversion_entrada"
    TRASLADO = "traslado"


DIRECCION_POR_TIPO_MOVIMIENTO: dict[TipoMovimiento, DireccionMovimiento] = {
    TipoMovimiento.ENTRADA_COMPRA: DireccionMovimiento.ENTRADA,
    TipoMovimiento.ENTRADA_ALBARAN: DireccionMovimiento.ENTRADA,
    TipoMovimiento.ENTRADA_FACTURA: DireccionMovimiento.ENTRADA,
    TipoMovimiento.CONSUMO: DireccionMovimiento.SALIDA,
    TipoMovimiento.MERMA: DireccionMovimiento.SALIDA,
    TipoMovimiento.AJUSTE_ENTRADA: DireccionMovimiento.ENTRADA,
    TipoMovimiento.AJUSTE_SALIDA: DireccionMovimiento.SALIDA,
    TipoMovimiento.REVERSION_CONSUMO: DireccionMovimiento.ENTRADA,
    TipoMovimiento.REVERSION_MERMA: DireccionMovimiento.ENTRADA,
    TipoMovimiento.REVERSION_ENTRADA: DireccionMovimiento.SALIDA,
    # Traslado: neto 0 en lote; dirección convencional entrada (cantidad_firmada=0).
    TipoMovimiento.TRASLADO: DireccionMovimiento.ENTRADA,
}

TIPO_MOVIMIENTO_VALORES: frozenset[str] = frozenset(t.value for t in TipoMovimiento)
DIRECCION_MOVIMIENTO_VALORES: frozenset[str] = frozenset(d.value for d in DireccionMovimiento)


# Servicios en los que un producto/receta puede aparecer en registros.
# Distinto de categoria_inventario y de CategoriaReceta.
SERVICIO_DISPONIBLE_LABEL: dict[TipoServicio, str] = {
    TipoServicio.DESAYUNO: "Desayuno",
    TipoServicio.COMIDA: "Comida",
    TipoServicio.CENA: "Cena",
    TipoServicio.BEBIDAS: "Bebidas",
}

SERVICIOS_DISPONIBLES_VALORES: frozenset[str] = frozenset(s.value for s in TipoServicio)
