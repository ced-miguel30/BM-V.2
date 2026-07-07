"""Servicio de registro de desayuno — consumo y FIFO."""

from dataclasses import dataclass
from datetime import date, datetime

from app.core.models import AppData, LineaDesayuno, LoteStock, RegistroDesayuno
from app.core.repositories.data_repository import DataRepository
from app.core.storage.session_store import get_data, persist_data

CESTA_SESSION_KEY = "bm_cesta_desayuno"


@dataclass
class ResultadoOperacion:
    ok: bool
    mensaje: str


@dataclass
class LineaCesta:
    producto_id: str
    nombre: str
    unidad: str
    cantidad: float


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
    from app.core.models import Actividad

    actividad = Actividad(
        _next_id("act", [a.id for a in data.actividades]),
        datetime.now(),
        _nombre_usuario(data),
        accion,
        detalle,
    )
    data.actividades.insert(0, actividad)


def _lotes_fifo(data: AppData, producto_id: str) -> list[LoteStock]:
    lotes = [
        l for l in data.lotes
        if l.producto_id == producto_id and l.cantidad_restante > 0
    ]
    return sorted(
        lotes,
        key=lambda l: (l.fecha_compra or date.min, l.id),
    )


def _coste_unidad_lote(lote: LoteStock) -> float:
    if lote.cantidad <= 0:
        return 0.0
    return lote.precio_total / lote.cantidad


def stock_disponible(data: AppData, producto_id: str) -> float:
    return sum(l.cantidad_restante for l in data.lotes if l.producto_id == producto_id)


def calcular_coste_linea(data: AppData, producto_id: str, cantidad: float) -> float:
    """Calcula coste FIFO sin modificar lotes."""
    restante = cantidad
    coste = 0.0
    for lote in _lotes_fifo(data, producto_id):
        if restante <= 0:
            break
        tomar = min(restante, lote.cantidad_restante)
        coste += tomar * _coste_unidad_lote(lote)
        restante -= tomar
    return round(coste, 2)


def _descontar_fifo(data: AppData, producto_id: str, cantidad: float) -> float:
    restante = cantidad
    coste = 0.0
    for lote in _lotes_fifo(data, producto_id):
        if restante <= 0:
            break
        tomar = min(restante, lote.cantidad_restante)
        coste += tomar * _coste_unidad_lote(lote)
        lote.cantidad_restante = round(lote.cantidad_restante - tomar, 4)
        restante -= tomar
    return round(coste, 2)


def _desayuno_existe(data: AppData, fecha: date) -> bool:
    return any(d.fecha == fecha for d in data.desayunos)


def get_cesta() -> list[LineaCesta]:
    import streamlit as st

    if CESTA_SESSION_KEY not in st.session_state:
        st.session_state[CESTA_SESSION_KEY] = []
    return st.session_state[CESTA_SESSION_KEY]


def limpiar_cesta() -> None:
    import streamlit as st

    st.session_state[CESTA_SESSION_KEY] = []


def anadir_a_cesta(producto_id: str, cantidad: float) -> ResultadoOperacion:
    if cantidad <= 0:
        return ResultadoOperacion(False, "La cantidad debe ser mayor que 0.")

    data = get_data()
    repo = DataRepository(data)
    producto = repo.get_producto(producto_id)
    if not producto:
        return ResultadoOperacion(False, "Producto no encontrado.")

    disponible = stock_disponible(data, producto_id)
    cesta = get_cesta()
    ya_en_cesta = sum(l.cantidad for l in cesta if l.producto_id == producto_id)
    if ya_en_cesta + cantidad > disponible:
        return ResultadoOperacion(
            False,
            f"Stock insuficiente de «{producto.nombre}». Disponible: {disponible:g} {producto.unidad.value}.",
        )

    for linea in cesta:
        if linea.producto_id == producto_id:
            linea.cantidad = round(linea.cantidad + cantidad, 4)
            return ResultadoOperacion(True, f"«{producto.nombre}» actualizado en la cesta.")

    cesta.append(LineaCesta(
        producto_id=producto_id,
        nombre=producto.nombre,
        unidad=producto.unidad.value,
        cantidad=cantidad,
    ))
    return ResultadoOperacion(True, f"«{producto.nombre}» añadido a la cesta.")


def quitar_de_cesta(producto_id: str) -> None:
    import streamlit as st

    cesta = get_cesta()
    st.session_state[CESTA_SESSION_KEY] = [l for l in cesta if l.producto_id != producto_id]


def coste_total_cesta() -> float:
    data = get_data()
    cesta = get_cesta()
    return sum(calcular_coste_linea(data, l.producto_id, l.cantidad) for l in cesta)


def registrar_desayuno(fecha: date) -> ResultadoOperacion:
    cesta = get_cesta()
    if not cesta:
        return ResultadoOperacion(False, "La cesta está vacía. Añada productos antes de registrar.")

    if fecha > date.today():
        return ResultadoOperacion(False, "No puede registrar desayunos en fechas futuras.")

    data = get_data()
    if _desayuno_existe(data, fecha):
        return ResultadoOperacion(
            False,
            f"Ya existe un desayuno registrado para el {fecha.strftime('%d/%m/%Y')}.",
        )

    lineas: list[LineaDesayuno] = []

    for item in cesta:
        disponible = stock_disponible(data, item.producto_id)
        if item.cantidad > disponible:
            return ResultadoOperacion(
                False,
                f"Stock insuficiente de «{item.nombre}» al registrar.",
            )

    for item in cesta:
        coste = _descontar_fifo(data, item.producto_id, item.cantidad)
        lineas.append(LineaDesayuno(item.producto_id, item.cantidad, coste))

    coste_total = round(sum(l.coste for l in lineas), 2)
    registro = RegistroDesayuno(
        _next_id("d", [d.id for d in data.desayunos]),
        fecha,
        lineas,
        coste_total,
        _nombre_usuario(data),
    )
    data.desayunos.append(registro)
    _registrar_actividad(
        data,
        "Registro desayuno",
        f"Desayuno del {fecha.strftime('%d/%m/%Y')} — {coste_total:.2f} €",
    )
    persist_data(data)
    limpiar_cesta()

    from app.core.services.alert_service import sincronizar_alertas
    sincronizar_alertas()

    return ResultadoOperacion(
        True,
        f"Desayuno registrado — {coste_total:.2f} € ({len(lineas)} producto(s)).",
    )


def productos_disponibles(buscar: str = "") -> list[dict]:
    """Productos con stock > 0, opcionalmente filtrados por nombre."""
    data = get_data()
    resultado = []
    termino = buscar.strip().lower()

    for producto in sorted(data.productos, key=lambda p: p.nombre):
        stock = stock_disponible(data, producto.id)
        if stock <= 0:
            continue
        if termino and termino not in producto.nombre.lower():
            continue
        resultado.append({
            "id": producto.id,
            "nombre": producto.nombre,
            "unidad": producto.unidad.value,
            "stock": stock,
            "etiqueta": f"{producto.nombre} ({stock:g} {producto.unidad.value})",
        })
    return resultado
