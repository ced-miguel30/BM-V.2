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
    OTRO = "Otro"


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
