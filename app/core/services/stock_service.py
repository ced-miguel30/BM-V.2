"""Servicio de gestión de stock — productos y lotes."""

from dataclasses import dataclass
from datetime import date, datetime

from app.core.models import Actividad, AppData, LoteStock, Producto, UnidadProducto
from app.core.repositories.data_repository import DataRepository
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
