"""Servicio de gestión de stock — productos y lotes."""

from dataclasses import dataclass
from datetime import date, datetime

from app.core.models import Actividad, AppData, LoteStock, Producto, UnidadProducto
from app.core.repositories.data_repository import DataRepository
from app.core.services.excel_bloques import RegistroExportable
from app.core.services.exportacion_semanal_service import ConfiguracionExportacionModulo
from app.core.services.formatting import formato_fecha, formato_moneda
from app.core.storage.session_store import get_data, persist_data

UNIDADES = [u.value for u in UnidadProducto]


@dataclass
class ResultadoOperacion:
    ok: bool
    mensaje: str


def _next_id(prefix: str, ids: list[str]) -> str:
    numeros = []
    for item_id in ids:
        sufijo = item_id[len(prefix):]
        if item_id.startswith(prefix) and sufijo.isdigit():
            numeros.append(int(sufijo))
    return f"{prefix}{(max(numeros, default=0) + 1):02d}"


def _nombre_usuario(data: AppData) -> str:
    for u in data.usuarios:
        if u.id == data.usuario_actual_id:
            return u.nombre
    return data.usuarios[0].nombre if data.usuarios else "Usuario"


def _registrar_actividad(data: AppData, accion: str, detalle: str) -> None:
    actividad = Actividad(
        _next_id("act", [a.id for a in data.actividades]),
        datetime.now(),
        _nombre_usuario(data),
        accion,
        detalle,
    )
    data.actividades.insert(0, actividad)


def _nombre_duplicado(data: AppData, nombre: str) -> bool:
    nombre_norm = nombre.strip().lower()
    return any(p.nombre.strip().lower() == nombre_norm for p in data.productos)


def crear_producto(
    nombre: str,
    unidad: str,
    stock_minimo: float | None,
    *,
    es_bebida: bool = False,
) -> ResultadoOperacion:
    nombre = nombre.strip()
    if not nombre:
        return ResultadoOperacion(
            False,
            "El nombre es obligatorio.",
        )
    if len(nombre) < 2:
        return ResultadoOperacion(False, "El nombre debe tener al menos 2 caracteres.")
    if unidad not in UNIDADES:
        return ResultadoOperacion(False, "Seleccione una unidad válida.")

    data = get_data()
    if _nombre_duplicado(data, nombre):
        tipo = "bebida" if es_bebida else "producto"
        return ResultadoOperacion(False, f"Ya existe un {tipo} llamado «{nombre}».")

    stock_min = stock_minimo if stock_minimo and stock_minimo > 0 else None
    prefix = "b" if es_bebida else "p"
    ids_mismo_tipo = [p.id for p in data.productos if p.id.startswith(prefix)]

    producto = Producto(
        _next_id(prefix, ids_mismo_tipo),
        nombre,
        UnidadProducto(unidad),
        stock_min,
        es_bebida=es_bebida,
    )
    data.productos.append(producto)
    accion = "Crear bebida" if es_bebida else "Crear producto"
    _registrar_actividad(data, accion, f"«{nombre}» ({unidad}) creado")
    persist_data(data)
    tipo_ok = "Bebida" if es_bebida else "Producto"
    return ResultadoOperacion(True, f"{tipo_ok} «{nombre}» creado correctamente.")


def crear_bebida(
    nombre: str,
    unidad: str,
    stock_minimo: float | None,
) -> ResultadoOperacion:
    """Alias para crear un producto marcado como bebida."""
    return crear_producto(nombre, unidad, stock_minimo, es_bebida=True)


def registrar_lote(
    producto_id: str,
    precio_total: float,
    cantidad: float,
    fecha_compra: date | None = None,
    fecha_expiracion: date | None = None,
    marca_proveedor: str | None = None,
    alerta_expiracion_dias: int | None = None,
) -> ResultadoOperacion:
    if not producto_id:
        return ResultadoOperacion(False, "Seleccione un producto.")
    if precio_total <= 0:
        return ResultadoOperacion(False, "El precio total debe ser mayor que 0.")
    if cantidad <= 0:
        return ResultadoOperacion(False, "La cantidad debe ser mayor que 0.")
    if fecha_compra and fecha_expiracion and fecha_expiracion < fecha_compra:
        return ResultadoOperacion(False, "La fecha de expiración no puede ser anterior a la compra.")
    if alerta_expiracion_dias is not None and alerta_expiracion_dias < 0:
        return ResultadoOperacion(False, "Los días de alerta no pueden ser negativos.")

    data = get_data()
    repo = DataRepository(data)
    producto = repo.get_producto(producto_id)
    if not producto:
        return ResultadoOperacion(False, "El producto seleccionado no existe.")

    proveedor = marca_proveedor.strip() if marca_proveedor else None
    alerta_dias = alerta_expiracion_dias if alerta_expiracion_dias and alerta_expiracion_dias > 0 else None

    lote = LoteStock(
        _next_id("l", [l.id for l in data.lotes]),
        producto_id,
        round(precio_total, 2),
        cantidad,
        cantidad,
        fecha_compra,
        fecha_expiracion,
        proveedor,
        alerta_dias,
    )
    data.lotes.append(lote)
    _registrar_actividad(
        data,
        "Registrar lote",
        f"Lote de «{producto.nombre}» — {cantidad} {producto.unidad.value} — {precio_total:.2f} €",
    )
    persist_data(data)
    return ResultadoOperacion(True, f"Lote registrado para «{producto.nombre}».")


def mapa_productos(data: AppData, *, es_bebida: bool | None = None) -> dict[str, str]:
    items = data.productos
    if es_bebida is not None:
        items = [p for p in items if p.es_bebida == es_bebida]
    return {p.nombre: p.id for p in items}


def mapa_bebidas(data: AppData) -> dict[str, str]:
    return mapa_productos(data, es_bebida=True)


def _ids_catalogo(data: AppData, *, es_bebida: bool) -> set[str]:
    return {p.id for p in data.productos if p.es_bebida == es_bebida}


def _lotes_filtrados(data: AppData, *, es_bebida: bool) -> list[LoteStock]:
    ids = _ids_catalogo(data, es_bebida=es_bebida)
    return [l for l in data.lotes if l.producto_id in ids]


def fecha_mas_antigua(*, es_bebida: bool = False) -> date | None:
    """Fecha de compra del lote más antiguo (para sembrar exportaciones
    semanales pendientes si nunca se ha exportado nada todavía)."""
    fechas = [l.fecha_compra for l in _lotes_filtrados(get_data(), es_bebida=es_bebida) if l.fecha_compra]
    return min(fechas) if fechas else None


def registros_exportables(
    inicio: date,
    hasta: datetime,
    *,
    es_bebida: bool = False,
) -> list[RegistroExportable]:
    """Un registro exportable por cada compra (lote) registrada entre
    `inicio` y `hasta`, filtrado por productos o bebidas."""
    data = get_data()
    repo = DataRepository(data)
    fin = hasta.date()
    col_producto = "Bebida" if es_bebida else "Producto"
    columnas = [
        col_producto, "Proveedor", "Lote", "Cantidad", "Unidad",
        "Precio total", "Coste unitario", "Expiración", "Tipo",
    ]
    simbolo = repo.get_simbolo_moneda()
    tipo_registro = "Bebida" if es_bebida else "Stock"
    tipo_movimiento = "Compra"

    resultado: list[RegistroExportable] = []
    for lote in sorted(
        _lotes_filtrados(data, es_bebida=es_bebida),
        key=lambda l: (l.fecha_compra or date.min, l.id),
    ):
        if not lote.fecha_compra or not (inicio <= lote.fecha_compra <= fin):
            continue
        producto = repo.get_producto(lote.producto_id)
        if not producto:
            continue
        coste_unit = round(lote.precio_total / lote.cantidad, 4) if lote.cantidad > 0 else 0.0
        resultado.append(RegistroExportable(
            fecha=lote.fecha_compra,
            hora=None,
            tipo=tipo_registro,
            identificador=lote.id,
            usuario=None,
            columnas=columnas,
            filas=[[
                repo.get_nombre_producto(lote.producto_id),
                lote.marca_proveedor or "—",
                lote.id,
                lote.cantidad,
                producto.unidad.value,
                formato_moneda(lote.precio_total, simbolo),
                formato_moneda(coste_unit, simbolo),
                formato_fecha(lote.fecha_expiracion),
                tipo_movimiento,
            ]],
            resumen=[("Precio total", formato_moneda(lote.precio_total, simbolo))],
        ))
    return resultado


def _registros_exportables_stock(inicio: date, hasta: datetime) -> list[RegistroExportable]:
    return registros_exportables(inicio, hasta, es_bebida=False)


def _registros_exportables_bebidas(inicio: date, hasta: datetime) -> list[RegistroExportable]:
    return registros_exportables(inicio, hasta, es_bebida=True)


def configuracion_exportacion(*, es_bebida: bool = False) -> ConfiguracionExportacionModulo:
    if es_bebida:
        return ConfiguracionExportacionModulo(
            tipo="bebidas",
            titulo_documento="Registro de Bebidas",
            obtener_registros=_registros_exportables_bebidas,
        )
    return ConfiguracionExportacionModulo(
        tipo="stock",
        titulo_documento="Registro de Stock",
        obtener_registros=_registros_exportables_stock,
    )
