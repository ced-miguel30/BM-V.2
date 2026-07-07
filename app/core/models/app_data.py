"""Contenedor de datos de la aplicación."""

from dataclasses import dataclass, field

from app.core.models.actividad import Actividad
from app.core.models.alerta import AlertaOperativa
from app.core.models.configuracion import ConfiguracionHotel
from app.core.models.desayuno import RegistroDesayuno
from app.core.models.lote import LoteStock
from app.core.models.merma import RegistroMerma
from app.core.models.producto import Producto
from app.core.models.usuario import Usuario


@dataclass
class AppData:
    productos: list[Producto] = field(default_factory=list)
    lotes: list[LoteStock] = field(default_factory=list)
    desayunos: list[RegistroDesayuno] = field(default_factory=list)
    mermas: list[RegistroMerma] = field(default_factory=list)
    alertas: list[AlertaOperativa] = field(default_factory=list)
    actividades: list[Actividad] = field(default_factory=list)
    usuarios: list[Usuario] = field(default_factory=list)
    configuracion: ConfiguracionHotel | None = None
    usuario_actual_id: str = ""
