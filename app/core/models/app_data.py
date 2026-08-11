"""Contenedor de datos de la aplicación."""

from dataclasses import dataclass, field

from app.core.models.actividad import Actividad
from app.core.models.ajuste import RegistroAjuste
from app.core.models.alerta import AlertaOperativa
from app.core.models.archivo_documental import ArchivoDocumental
from app.core.models.catalogo import Categoria, Departamento, Subcategoria, Ubicacion
from app.core.models.configuracion import ConfiguracionHotel
from app.core.models.desayuno import RegistroDesayuno
from app.core.models.documento import Documento
from app.core.models.conciliacion import ConciliacionLineaDocumento
from app.core.models.lote import LoteStock
from app.core.models.merma import RegistroMerma, ResponsableMerma
from app.core.models.movimiento import MovimientoInventario
from app.core.models.producto import Producto
from app.core.models.proveedor import Impuesto, Proveedor, RelacionProductoProveedor
from app.core.models.receta import Receta
from app.core.models.recuento import SesionRecuento
from app.core.models.registro_servicio import RegistroServicio
from app.core.models.usuario import Usuario


@dataclass
class AppData:
    productos: list[Producto] = field(default_factory=list)
    lotes: list[LoteStock] = field(default_factory=list)
    recetas: list[Receta] = field(default_factory=list)
    desayunos: list[RegistroDesayuno] = field(default_factory=list)
    registros_servicio: list[RegistroServicio] = field(default_factory=list)
    mermas: list[RegistroMerma] = field(default_factory=list)
    ajustes: list[RegistroAjuste] = field(default_factory=list)
    alertas: list[AlertaOperativa] = field(default_factory=list)
    alertas_descartadas: list[str] = field(default_factory=list)
    actividades: list[Actividad] = field(default_factory=list)
    usuarios: list[Usuario] = field(default_factory=list)
    responsables_merma: list[ResponsableMerma] = field(default_factory=list)
    departamentos: list[Departamento] = field(default_factory=list)
    categorias: list[Categoria] = field(default_factory=list)
    subcategorias: list[Subcategoria] = field(default_factory=list)
    ubicaciones: list[Ubicacion] = field(default_factory=list)
    movimientos: list[MovimientoInventario] = field(default_factory=list)
    recuentos: list[SesionRecuento] = field(default_factory=list)
    proveedores: list[Proveedor] = field(default_factory=list)
    impuestos: list[Impuesto] = field(default_factory=list)
    relaciones_producto_proveedor: list[RelacionProductoProveedor] = field(
        default_factory=list
    )
    archivos_documentales: list[ArchivoDocumental] = field(default_factory=list)
    # Fase 10 — albaranes (facturas = F11).
    documentos: list[Documento] = field(default_factory=list)
    # A7 — conciliaciones N:M factura↔albarán
    conciliaciones_documento: list[ConciliacionLineaDocumento] = field(
        default_factory=list
    )
    configuracion: ConfiguracionHotel | None = None
    usuario_actual_id: str = ""
    revision: int = 0
