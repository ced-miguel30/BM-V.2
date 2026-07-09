"""Servicio de registro de desayuno — consumo y FIFO."""

from dataclasses import dataclass, field
from datetime import date, datetime

from app.core.models import (
    AppData,
    ExtraRecetaDesayuno,
    LineaDesayuno,
    LoteStock,
    OmisionRecetaDesayuno,
    RegistroDesayuno,
    RegistroRecetaDesayuno,
)
from app.core.repositories.data_repository import DataRepository
from app.core.services.text_search import coincide_busqueda
from app.core.storage.session_store import get_data, persist_data

CESTA_SESSION_KEY = "bm_cesta_desayuno"
CESTA_RECETAS_KEY = "bm_cesta_recetas"
GRUPO_COUNTER_KEY = "bm_grupo_receta_counter"


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


@dataclass
class LineaCestaIngrediente:
    producto_id: str
    nombre: str
    unidad: str
    cantidad: float
    es_base_receta: bool = True
    es_extra: bool = False


@dataclass
class GrupoRecetaCesta:
    grupo_id: str
    receta_id: str
    nombre_receta: str
    porciones: float
    ingredientes: list[LineaCestaIngrediente] = field(default_factory=list)


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


def get_cesta_recetas() -> list[GrupoRecetaCesta]:
    import streamlit as st

    if CESTA_RECETAS_KEY not in st.session_state:
        st.session_state[CESTA_RECETAS_KEY] = []
    return st.session_state[CESTA_RECETAS_KEY]


def _guardar_cesta_recetas(grupos: list[GrupoRecetaCesta]) -> None:
    import streamlit as st

    st.session_state[CESTA_RECETAS_KEY] = grupos


def _nuevo_grupo_id() -> str:
    import streamlit as st

    contador = st.session_state.get(GRUPO_COUNTER_KEY, 0) + 1
    st.session_state[GRUPO_COUNTER_KEY] = contador
    return f"grupo_{contador:03d}"


def limpiar_cesta() -> None:
    import streamlit as st

    st.session_state[CESTA_SESSION_KEY] = []
    st.session_state[CESTA_RECETAS_KEY] = []


def cesta_vacia() -> bool:
    return not get_cesta() and not get_cesta_recetas()


def _cantidad_en_cesta_producto(producto_id: str) -> float:
    total = sum(l.cantidad for l in get_cesta() if l.producto_id == producto_id)
    for grupo in get_cesta_recetas():
        for ing in grupo.ingredientes:
            if ing.producto_id == producto_id:
                total += ing.cantidad
    return total


def _validar_stock_producto(
    data: AppData,
    producto_id: str,
    cantidad_adicional: float,
) -> ResultadoOperacion | None:
    repo = DataRepository(data)
    producto = repo.get_producto(producto_id)
    if not producto:
        return ResultadoOperacion(False, "Producto no encontrado.")

    disponible = stock_disponible(data, producto_id)
    en_cesta = _cantidad_en_cesta_producto(producto_id)
    if en_cesta + cantidad_adicional > disponible:
        return ResultadoOperacion(
            False,
            f"Stock insuficiente de «{producto.nombre}». Disponible: {disponible:g} {producto.unidad.value}.",
        )
    return None


def anadir_a_cesta(producto_id: str, cantidad: float) -> ResultadoOperacion:
    if cantidad <= 0:
        return ResultadoOperacion(False, "La cantidad debe ser mayor que 0.")

    data = get_data()
    error = _validar_stock_producto(data, producto_id, cantidad)
    if error:
        return error

    repo = DataRepository(data)
    producto = repo.get_producto(producto_id)
    if not producto:
        return ResultadoOperacion(False, "Producto no encontrado.")

    cesta = get_cesta()
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


def anadir_receta_a_cesta(receta_id: str, porciones: float) -> ResultadoOperacion:
    if porciones <= 0:
        return ResultadoOperacion(False, "Las porciones deben ser mayores que 0.")

    data = get_data()
    repo = DataRepository(data)
    receta = repo.get_receta(receta_id)
    if not receta:
        return ResultadoOperacion(False, "Receta no encontrada.")
    if not receta.ingredientes:
        return ResultadoOperacion(False, f"La receta «{receta.nombre}» no tiene ingredientes.")

    ingredientes: list[LineaCestaIngrediente] = []
    for ing in receta.ingredientes:
        producto = repo.get_producto(ing.producto_id)
        if not producto:
            return ResultadoOperacion(False, "Un ingrediente de la receta ya no existe en el catálogo.")
        cantidad = round(ing.cantidad * porciones, 4)
        error = _validar_stock_producto(data, ing.producto_id, cantidad)
        if error:
            return error
        ingredientes.append(LineaCestaIngrediente(
            producto_id=producto.id,
            nombre=producto.nombre,
            unidad=producto.unidad.value,
            cantidad=cantidad,
            es_base_receta=True,
            es_extra=False,
        ))

    grupo = GrupoRecetaCesta(
        _nuevo_grupo_id(),
        receta.id,
        receta.nombre,
        porciones,
        ingredientes,
    )
    grupos = get_cesta_recetas()
    grupos.append(grupo)
    _guardar_cesta_recetas(grupos)
    return ResultadoOperacion(True, f"«{receta.nombre}» (×{porciones:g}) añadida a la cesta.")


def quitar_de_cesta(producto_id: str) -> None:
    import streamlit as st

    cesta = get_cesta()
    st.session_state[CESTA_SESSION_KEY] = [l for l in cesta if l.producto_id != producto_id]


def quitar_grupo_receta(grupo_id: str) -> None:
    grupos = [g for g in get_cesta_recetas() if g.grupo_id != grupo_id]
    _guardar_cesta_recetas(grupos)


def _buscar_grupo(grupo_id: str) -> GrupoRecetaCesta | None:
    return next((g for g in get_cesta_recetas() if g.grupo_id == grupo_id), None)


def quitar_ingrediente_grupo(grupo_id: str, producto_id: str) -> None:
    grupo = _buscar_grupo(grupo_id)
    if not grupo:
        return
    grupo.ingredientes = [i for i in grupo.ingredientes if i.producto_id != producto_id]
    _guardar_cesta_recetas(get_cesta_recetas())


def modificar_cantidad_ingrediente(
    grupo_id: str,
    producto_id: str,
    cantidad: float,
) -> ResultadoOperacion:
    if cantidad <= 0:
        return ResultadoOperacion(False, "La cantidad debe ser mayor que 0.")

    data = get_data()
    grupo = _buscar_grupo(grupo_id)
    if not grupo:
        return ResultadoOperacion(False, "Grupo de receta no encontrado.")

    ingrediente = next((i for i in grupo.ingredientes if i.producto_id == producto_id), None)
    if not ingrediente:
        return ResultadoOperacion(False, "Ingrediente no encontrado en la receta.")

    delta = cantidad - ingrediente.cantidad
    if delta > 0:
        error = _validar_stock_producto(data, producto_id, delta)
        if error:
            return error

    ingrediente.cantidad = round(cantidad, 4)
    _guardar_cesta_recetas(get_cesta_recetas())
    return ResultadoOperacion(True, "Cantidad actualizada.")


def anadir_extra_a_grupo(
    grupo_id: str,
    producto_id: str,
    cantidad: float,
) -> ResultadoOperacion:
    if cantidad <= 0:
        return ResultadoOperacion(False, "La cantidad debe ser mayor que 0.")

    data = get_data()
    repo = DataRepository(data)
    producto = repo.get_producto(producto_id)
    if not producto:
        return ResultadoOperacion(False, "Producto no encontrado.")

    grupo = _buscar_grupo(grupo_id)
    if not grupo:
        return ResultadoOperacion(False, "Grupo de receta no encontrado.")

    error = _validar_stock_producto(data, producto_id, cantidad)
    if error:
        return error

    for ing in grupo.ingredientes:
        if ing.producto_id == producto_id and ing.es_extra:
            ing.cantidad = round(ing.cantidad + cantidad, 4)
            _guardar_cesta_recetas(get_cesta_recetas())
            return ResultadoOperacion(True, f"Extra «{producto.nombre}» actualizado.")

    grupo.ingredientes.append(LineaCestaIngrediente(
        producto_id=producto.id,
        nombre=producto.nombre,
        unidad=producto.unidad.value,
        cantidad=cantidad,
        es_base_receta=False,
        es_extra=True,
    ))
    _guardar_cesta_recetas(get_cesta_recetas())
    return ResultadoOperacion(True, f"Extra «{producto.nombre}» añadido.")


def coste_total_cesta() -> float:
    data = get_data()
    total = sum(calcular_coste_linea(data, l.producto_id, l.cantidad) for l in get_cesta())
    for grupo in get_cesta_recetas():
        for ing in grupo.ingredientes:
            total += calcular_coste_linea(data, ing.producto_id, ing.cantidad)
    return round(total, 2)


def _aplanar_cesta() -> dict[str, tuple[float, bool]]:
    """Fusiona productos sueltos e ingredientes de recetas."""
    fusionado: dict[str, tuple[float, bool]] = {}
    for linea in get_cesta():
        cantidad, es_extra = fusionado.get(linea.producto_id, (0.0, False))
        fusionado[linea.producto_id] = (round(cantidad + linea.cantidad, 4), es_extra)
    for grupo in get_cesta_recetas():
        for ing in grupo.ingredientes:
            cantidad, es_extra = fusionado.get(ing.producto_id, (0.0, False))
            fusionado[ing.producto_id] = (
                round(cantidad + ing.cantidad, 4),
                es_extra or ing.es_extra,
            )
    return fusionado


def _construir_registros_recetas(data: AppData, grupos: list[GrupoRecetaCesta]) -> list[RegistroRecetaDesayuno]:
    repo = DataRepository(data)
    registros: list[RegistroRecetaDesayuno] = []
    for grupo in grupos:
        receta = repo.get_receta(grupo.receta_id)
        template_ids = {i.producto_id for i in receta.ingredientes} if receta else set()
        presentes_base = {
            i.producto_id for i in grupo.ingredientes if i.es_base_receta and not i.es_extra
        }
        omisiones = [
            OmisionRecetaDesayuno(pid)
            for pid in sorted(template_ids - presentes_base)
        ]
        extras = [
            ExtraRecetaDesayuno(i.producto_id, i.cantidad)
            for i in grupo.ingredientes if i.es_extra
        ]
        registros.append(RegistroRecetaDesayuno(
            grupo.receta_id,
            grupo.nombre_receta,
            grupo.porciones,
            extras,
            omisiones,
        ))
    return registros


def registrar_desayuno(fecha: date, num_huespedes: int) -> ResultadoOperacion:
    if cesta_vacia():
        return ResultadoOperacion(
            False,
            "La cesta está vacía. Añada productos o recetas antes de registrar.",
        )

    if fecha > date.today():
        return ResultadoOperacion(False, "No puede registrar desayunos en fechas futuras.")

    if num_huespedes < 1:
        return ResultadoOperacion(False, "Indique al menos 1 huésped.")

    data = get_data()
    if _desayuno_existe(data, fecha):
        return ResultadoOperacion(
            False,
            f"Ya existe un desayuno registrado para el {fecha.strftime('%d/%m/%Y')}.",
        )

    repo = DataRepository(data)
    fusionado = _aplanar_cesta()
    grupos = list(get_cesta_recetas())

    for producto_id, (cantidad, _) in fusionado.items():
        disponible = stock_disponible(data, producto_id)
        if cantidad > disponible:
            nombre = repo.get_nombre_producto(producto_id)
            return ResultadoOperacion(
                False,
                f"Stock insuficiente de «{nombre}» al registrar.",
            )

    lineas: list[LineaDesayuno] = []
    for producto_id, (cantidad, es_extra) in fusionado.items():
        coste = _descontar_fifo(data, producto_id, cantidad)
        lineas.append(LineaDesayuno(producto_id, cantidad, coste, es_extra))

    registros_recetas = _construir_registros_recetas(data, grupos)
    coste_total = round(sum(l.coste for l in lineas), 2)
    registro = RegistroDesayuno(
        _next_id("d", [d.id for d in data.desayunos]),
        fecha,
        lineas,
        coste_total,
        _nombre_usuario(data),
        num_huespedes,
        registros_recetas,
    )
    data.desayunos.append(registro)

    detalle_recetas = ""
    if registros_recetas:
        detalle_recetas = f" — {len(registros_recetas)} receta(s)"

    _registrar_actividad(
        data,
        "Registro desayuno",
        f"Desayuno del {fecha.strftime('%d/%m/%Y')} — {coste_total:.2f} € — {num_huespedes} huéspedes{detalle_recetas}",
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
    termino = buscar.strip()

    for producto in sorted(data.productos, key=lambda p: p.nombre):
        stock = stock_disponible(data, producto.id)
        if stock <= 0:
            continue
        if termino and not coincide_busqueda(producto.nombre, termino):
            continue
        resultado.append({
            "id": producto.id,
            "nombre": producto.nombre,
            "unidad": producto.unidad.value,
            "stock": stock,
            "etiqueta": f"{producto.nombre} ({stock:g} {producto.unidad.value})",
        })
    return resultado
