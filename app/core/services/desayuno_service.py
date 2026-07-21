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
LINEA_COUNTER_KEY = "bm_linea_cesta_counter"
MODS_PENDIENTES_KEY = "bm_receta_pendiente_mods"
PASO_CANTIDAD = 0.5


@dataclass
class ResultadoOperacion:
    ok: bool
    mensaje: str
    codigo: str | None = None
    detalle_stock: list[str] | None = None


@dataclass
class LineaCesta:
    linea_id: str
    producto_id: str
    nombre: str
    unidad: str
    cantidad: float
    es_extra: bool = False
    es_omision: bool = False
    paso_edicion: float = 0


@dataclass
class LineaCestaIngrediente:
    linea_id: str
    producto_id: str
    nombre: str
    unidad: str
    cantidad: float
    es_base_receta: bool = True
    es_extra: bool = False
    es_omision: bool = False
    paso_edicion: float = 0


@dataclass
class GrupoRecetaCesta:
    grupo_id: str
    receta_id: str
    nombre_receta: str
    porciones: float
    ingredientes: list[LineaCestaIngrediente] = field(default_factory=list)


@dataclass
class ModPendienteReceta:
    mod_id: str
    producto_id: str
    nombre: str
    unidad: str
    cantidad: float
    es_extra: bool
    es_omision: bool


def _next_id(prefix: str, ids: list[str]) -> str:
    numeros = []
    for item_id in ids:
        sufijo = item_id[len(prefix):]
        if item_id.startswith(prefix) and sufijo.isdigit():
            numeros.append(int(sufijo))
    return f"{prefix}{(max(numeros, default=0) + 1):02d}"


def _nueva_linea_id() -> str:
    import streamlit as st

    contador = st.session_state.get(LINEA_COUNTER_KEY, 0) + 1
    st.session_state[LINEA_COUNTER_KEY] = contador
    return f"lin_{contador:04d}"


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


def _ultimo_lote_producto(data: AppData, producto_id: str) -> LoteStock | None:
    lotes = [l for l in data.lotes if l.producto_id == producto_id]
    if not lotes:
        return None
    return sorted(lotes, key=lambda l: (l.fecha_compra or date.min, l.id))[-1]


def _coste_unidad_lote(lote: LoteStock) -> float:
    if lote.cantidad <= 0:
        return 0.0
    return lote.precio_total / lote.cantidad


def stock_disponible(data: AppData, producto_id: str) -> float:
    return sum(l.cantidad_restante for l in data.lotes if l.producto_id == producto_id)


def calcular_coste_linea(data: AppData, producto_id: str, cantidad: float) -> float:
    if cantidad <= 0:
        return 0.0
    restante = cantidad
    coste = 0.0
    for lote in _lotes_fifo(data, producto_id):
        if restante <= 0:
            break
        tomar = min(restante, lote.cantidad_restante)
        coste += tomar * _coste_unidad_lote(lote)
        restante -= tomar
    return round(coste, 2)


def _descontar_fifo(
    data: AppData,
    producto_id: str,
    cantidad: float,
    *,
    permitir_negativo: bool = False,
) -> float:
    if cantidad <= 0:
        return 0.0
    restante = cantidad
    coste = 0.0
    ultimo_lote_tocado: LoteStock | None = None
    for lote in _lotes_fifo(data, producto_id):
        if restante <= 0:
            break
        tomar = min(restante, lote.cantidad_restante)
        coste += tomar * _coste_unidad_lote(lote)
        lote.cantidad_restante = round(lote.cantidad_restante - tomar, 4)
        restante -= tomar
        ultimo_lote_tocado = lote

    if restante > 0 and permitir_negativo:
        lote_destino = ultimo_lote_tocado or _ultimo_lote_producto(data, producto_id)
        if lote_destino:
            lote_destino.cantidad_restante = round(lote_destino.cantidad_restante - restante, 4)

    return round(coste, 2)


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


def _guardar_cesta(grupos_o_cesta) -> None:
    import streamlit as st

    if grupos_o_cesta and isinstance(grupos_o_cesta[0], GrupoRecetaCesta):
        st.session_state[CESTA_RECETAS_KEY] = grupos_o_cesta
    else:
        st.session_state[CESTA_SESSION_KEY] = grupos_o_cesta


def _guardar_cesta_recetas(grupos: list[GrupoRecetaCesta]) -> None:
    import streamlit as st

    st.session_state[CESTA_RECETAS_KEY] = grupos


def _nuevo_grupo_id() -> str:
    import streamlit as st

    contador = st.session_state.get(GRUPO_COUNTER_KEY, 0) + 1
    st.session_state[GRUPO_COUNTER_KEY] = contador
    return f"grupo_{contador:03d}"


def get_mods_pendientes() -> list[ModPendienteReceta]:
    import streamlit as st

    if MODS_PENDIENTES_KEY not in st.session_state:
        st.session_state[MODS_PENDIENTES_KEY] = []
    return st.session_state[MODS_PENDIENTES_KEY]


def limpiar_mods_pendientes() -> None:
    import streamlit as st

    st.session_state[MODS_PENDIENTES_KEY] = []


def limpiar_cesta() -> None:
    import streamlit as st

    st.session_state[CESTA_SESSION_KEY] = []
    st.session_state[CESTA_RECETAS_KEY] = []
    limpiar_mods_pendientes()


def cesta_vacia() -> bool:
    return not get_cesta() and not get_cesta_recetas()


def etiqueta_linea_suelta(linea: LineaCesta) -> str:
    cant = abs(linea.cantidad)
    if linea.es_omision or linea.cantidad < 0:
        return f"s/ {linea.nombre} — {cant:g} {linea.unidad}"
    if linea.es_extra or linea.cantidad > 0:
        return f"c/ extra {linea.nombre} — {cant:g} {linea.unidad}"
    return f"{linea.nombre} — {cant:g} {linea.unidad}"


def etiqueta_linea_receta(ing: LineaCestaIngrediente) -> str:
    cant = abs(ing.cantidad)
    if ing.es_omision or ing.cantidad < 0:
        return f"s/ {ing.nombre} — {cant:g} {ing.unidad}"
    if ing.es_extra:
        return f"c/ extra {ing.nombre} — {cant:g} {ing.unidad}"
    return f"{ing.nombre} — {cant:g} {ing.unidad}"


def productos_catalogo(buscar: str = "") -> list[dict]:
    """Todos los productos del catálogo (sin filtrar por stock)."""
    data = get_data()
    resultado = []
    termino = buscar.strip()
    for producto in sorted(data.productos, key=lambda p: p.nombre):
        if termino and not coincide_busqueda(producto.nombre, termino):
            continue
        stock = stock_disponible(data, producto.id)
        resultado.append({
            "id": producto.id,
            "nombre": producto.nombre,
            "unidad": producto.unidad.value,
            "stock": stock,
            "etiqueta": f"{producto.nombre} ({stock:g} {producto.unidad.value})",
        })
    return resultado


def productos_disponibles(buscar: str = "") -> list[dict]:
    """Productos con stock > 0, opcionalmente filtrados por nombre."""
    return [p for p in productos_catalogo(buscar) if p["stock"] > 0]


def anadir_mod_pendiente_receta(producto_id: str, cantidad: float) -> ResultadoOperacion:
    if cantidad == 0:
        return ResultadoOperacion(False, "La cantidad no puede ser 0.")

    data = get_data()
    repo = DataRepository(data)
    producto = repo.get_producto(producto_id)
    if not producto:
        return ResultadoOperacion(False, "Producto no encontrado.")

    mods = get_mods_pendientes()
    mods.append(ModPendienteReceta(
        _nueva_linea_id(),
        producto.id,
        producto.nombre,
        producto.unidad.value,
        cantidad,
        es_extra=cantidad > 0,
        es_omision=cantidad < 0,
    ))
    import streamlit as st
    st.session_state[MODS_PENDIENTES_KEY] = mods

    etiqueta = "c/ extra" if cantidad > 0 else "s/"
    return ResultadoOperacion(True, f"{etiqueta} {producto.nombre} añadido a la receta pendiente.")


def quitar_mod_pendiente(mod_id: str) -> None:
    import streamlit as st

    mods = [m for m in get_mods_pendientes() if m.mod_id != mod_id]
    st.session_state[MODS_PENDIENTES_KEY] = mods


def anadir_a_cesta(producto_id: str, cantidad: float) -> ResultadoOperacion:
    if cantidad == 0:
        return ResultadoOperacion(False, "La cantidad no puede ser 0.")

    data = get_data()
    repo = DataRepository(data)
    producto = repo.get_producto(producto_id)
    if not producto:
        return ResultadoOperacion(False, "Producto no encontrado.")

    cesta = get_cesta()
    paso = abs(cantidad) if cantidad != 0 else PASO_CANTIDAD
    for linea in cesta:
        if linea.producto_id == producto_id:
            linea.cantidad = round(linea.cantidad + cantidad, 4)
            linea.es_extra = linea.cantidad > 0
            linea.es_omision = linea.cantidad < 0
            if linea.paso_edicion <= 0:
                linea.paso_edicion = paso
            etiqueta = etiqueta_linea_suelta(linea)
            import streamlit as st
            st.session_state[CESTA_SESSION_KEY] = cesta
            return ResultadoOperacion(True, f"{etiqueta} actualizado en la cesta.")

    cesta.append(LineaCesta(
        _nueva_linea_id(),
        producto_id,
        producto.nombre,
        producto.unidad.value,
        cantidad,
        es_extra=cantidad > 0,
        es_omision=cantidad < 0,
        paso_edicion=paso,
    ))
    import streamlit as st
    st.session_state[CESTA_SESSION_KEY] = cesta
    return ResultadoOperacion(True, f"{etiqueta_linea_suelta(cesta[-1])} añadido a la cesta.")


def _linea_ingrediente_desde_mod(mod: ModPendienteReceta) -> LineaCestaIngrediente:
    paso = abs(mod.cantidad) if mod.cantidad != 0 else PASO_CANTIDAD
    return LineaCestaIngrediente(
        _nueva_linea_id(),
        mod.producto_id,
        mod.nombre,
        mod.unidad,
        mod.cantidad,
        es_base_receta=False,
        es_extra=mod.es_extra,
        es_omision=mod.es_omision,
        paso_edicion=paso,
    )


def anadir_receta_a_cesta(
    receta_id: str,
    porciones: float,
    mods_pendientes: list[ModPendienteReceta] | None = None,
) -> ResultadoOperacion:
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
        ingredientes.append(LineaCestaIngrediente(
            _nueva_linea_id(),
            producto.id,
            producto.nombre,
            producto.unidad.value,
            cantidad,
            es_base_receta=True,
            es_extra=False,
            es_omision=False,
            paso_edicion=ing.cantidad if ing.cantidad > 0 else PASO_CANTIDAD,
        ))

    for mod in mods_pendientes or []:
        ingredientes.append(_linea_ingrediente_desde_mod(mod))

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
    limpiar_mods_pendientes()
    return ResultadoOperacion(True, f"«{receta.nombre}» (×{porciones:g}) añadida a la cesta.")


def quitar_grupo_receta(grupo_id: str) -> None:
    grupos = [g for g in get_cesta_recetas() if g.grupo_id != grupo_id]
    _guardar_cesta_recetas(grupos)


def _buscar_grupo(grupo_id: str) -> GrupoRecetaCesta | None:
    return next((g for g in get_cesta_recetas() if g.grupo_id == grupo_id), None)


def _buscar_linea_grupo(grupo_id: str, linea_id: str) -> LineaCestaIngrediente | None:
    grupo = _buscar_grupo(grupo_id)
    if not grupo:
        return None
    return next((i for i in grupo.ingredientes if i.linea_id == linea_id), None)


def quitar_linea_grupo(grupo_id: str, linea_id: str) -> None:
    grupo = _buscar_grupo(grupo_id)
    if not grupo:
        return
    grupo.ingredientes = [i for i in grupo.ingredientes if i.linea_id != linea_id]
    _guardar_cesta_recetas(get_cesta_recetas())


def paso_linea_grupo(grupo_id: str, linea_id: str) -> float:
    """Incremento al editar un ingrediente del desglose de receta en la cesta."""
    grupo = _buscar_grupo(grupo_id)
    linea = _buscar_linea_grupo(grupo_id, linea_id)
    if not linea or not grupo:
        return PASO_CANTIDAD

    if linea.paso_edicion > 0:
        return linea.paso_edicion

    if linea.es_base_receta:
        repo = DataRepository(get_data())
        receta = repo.get_receta(grupo.receta_id)
        if receta:
            ing_template = next(
                (i for i in receta.ingredientes if i.producto_id == linea.producto_id),
                None,
            )
            if ing_template and ing_template.cantidad > 0:
                return ing_template.cantidad

    if linea.cantidad != 0:
        return abs(linea.cantidad)

    return PASO_CANTIDAD


def ajustar_linea_grupo(grupo_id: str, linea_id: str, delta: float) -> ResultadoOperacion:
    grupo = _buscar_grupo(grupo_id)
    if not grupo:
        return ResultadoOperacion(False, "Grupo no encontrado.")
    linea = _buscar_linea_grupo(grupo_id, linea_id)
    if not linea:
        return ResultadoOperacion(False, "Línea no encontrada.")

    nueva = round(linea.cantidad + delta, 4)
    if nueva == 0:
        quitar_linea_grupo(grupo_id, linea_id)
        return ResultadoOperacion(True, "Línea eliminada.")
    return modificar_linea_grupo(grupo_id, linea_id, nueva)


def modificar_linea_grupo(grupo_id: str, linea_id: str, cantidad: float) -> ResultadoOperacion:
    if cantidad == 0:
        quitar_linea_grupo(grupo_id, linea_id)
        return ResultadoOperacion(True, "Línea eliminada.")

    linea = _buscar_linea_grupo(grupo_id, linea_id)
    if not linea:
        return ResultadoOperacion(False, "Línea no encontrada.")

    linea.cantidad = round(cantidad, 4)
    linea.es_extra = not linea.es_base_receta and cantidad > 0
    linea.es_omision = cantidad < 0 or (not linea.es_base_receta and cantidad < 0)
    if linea.es_base_receta and cantidad < 0:
        linea.es_omision = True
    _guardar_cesta_recetas(get_cesta_recetas())
    return ResultadoOperacion(True, "Cantidad actualizada.")


def modificar_porciones_grupo(grupo_id: str, porciones: float) -> ResultadoOperacion:
    if porciones <= 0:
        return ResultadoOperacion(False, "Las porciones deben ser mayores que 0.")

    data = get_data()
    repo = DataRepository(data)
    grupo = _buscar_grupo(grupo_id)
    if not grupo:
        return ResultadoOperacion(False, "Grupo no encontrado.")

    receta = repo.get_receta(grupo.receta_id)
    if not receta:
        return ResultadoOperacion(False, "Receta no encontrada.")

    grupo.porciones = porciones

    for linea in grupo.ingredientes:
        if not linea.es_base_receta:
            continue
        ing_template = next((i for i in receta.ingredientes if i.producto_id == linea.producto_id), None)
        if not ing_template:
            continue
        nueva_cant = round(ing_template.cantidad * porciones, 4)
        linea.cantidad = nueva_cant

    _guardar_cesta_recetas(get_cesta_recetas())
    return ResultadoOperacion(True, "Porciones actualizadas.")


def ajustar_porciones_grupo(grupo_id: str, delta: float) -> ResultadoOperacion:
    grupo = _buscar_grupo(grupo_id)
    if not grupo:
        return ResultadoOperacion(False, "Grupo no encontrado.")
    nuevas = round(grupo.porciones + delta, 4)
    if nuevas <= 0:
        quitar_grupo_receta(grupo_id)
        return ResultadoOperacion(True, "Receta eliminada de la cesta.")
    return modificar_porciones_grupo(grupo_id, nuevas)


def _buscar_linea_suelta(linea_id: str) -> LineaCesta | None:
    return next((l for l in get_cesta() if l.linea_id == linea_id), None)


def paso_linea_suelta(linea_id: str) -> float:
    """Incremento al editar un producto suelto en la cesta."""
    linea = _buscar_linea_suelta(linea_id)
    if not linea:
        return PASO_CANTIDAD
    if linea.paso_edicion > 0:
        return linea.paso_edicion
    if linea.cantidad != 0:
        return abs(linea.cantidad)
    return PASO_CANTIDAD


def quitar_linea_suelta(linea_id: str) -> None:
    import streamlit as st

    cesta = [l for l in get_cesta() if l.linea_id != linea_id]
    st.session_state[CESTA_SESSION_KEY] = cesta


def ajustar_cantidad_suelto(linea_id: str, delta: float) -> ResultadoOperacion:
    linea = _buscar_linea_suelta(linea_id)
    if not linea:
        return ResultadoOperacion(False, "Línea no encontrada.")
    nueva = round(linea.cantidad + delta, 4)
    if nueva == 0:
        quitar_linea_suelta(linea_id)
        return ResultadoOperacion(True, "Producto eliminado de la cesta.")
    return modificar_cantidad_suelto(linea_id, nueva)


def modificar_cantidad_suelto(linea_id: str, cantidad: float) -> ResultadoOperacion:
    if cantidad == 0:
        quitar_linea_suelta(linea_id)
        return ResultadoOperacion(True, "Producto eliminado de la cesta.")

    linea = _buscar_linea_suelta(linea_id)
    if not linea:
        return ResultadoOperacion(False, "Línea no encontrada.")

    linea.cantidad = round(cantidad, 4)
    linea.es_extra = cantidad > 0
    linea.es_omision = cantidad < 0
    import streamlit as st
    st.session_state[CESTA_SESSION_KEY] = get_cesta()
    return ResultadoOperacion(True, "Cantidad actualizada.")


def coste_total_cesta() -> float:
    data = get_data()
    total = sum(
        calcular_coste_linea(data, l.producto_id, max(l.cantidad, 0))
        for l in get_cesta()
    )
    for grupo in get_cesta_recetas():
        for ing in grupo.ingredientes:
            total += calcular_coste_linea(data, ing.producto_id, max(ing.cantidad, 0))
    return round(total, 2)


def _aplanar_cesta() -> dict[str, tuple[float, bool]]:
    fusionado: dict[str, tuple[float, bool]] = {}
    for linea in get_cesta():
        cantidad, es_extra = fusionado.get(linea.producto_id, (0.0, False))
        fusionado[linea.producto_id] = (
            round(cantidad + linea.cantidad, 4),
            es_extra or linea.es_extra,
        )
    for grupo in get_cesta_recetas():
        for ing in grupo.ingredientes:
            cantidad, es_extra = fusionado.get(ing.producto_id, (0.0, False))
            fusionado[ing.producto_id] = (
                round(cantidad + ing.cantidad, 4),
                es_extra or ing.es_extra,
            )
    return {pid: (max(c, 0), e) for pid, (c, e) in fusionado.items() if c != 0}


def _construir_registros_recetas(data: AppData, grupos: list[GrupoRecetaCesta]) -> list[RegistroRecetaDesayuno]:
    repo = DataRepository(data)
    registros: list[RegistroRecetaDesayuno] = []
    for grupo in grupos:
        receta = repo.get_receta(grupo.receta_id)
        template_ids = {i.producto_id for i in receta.ingredientes} if receta else set()
        presentes_base = {
            i.producto_id for i in grupo.ingredientes
            if i.es_base_receta and i.cantidad > 0
        }
        omisiones = [
            OmisionRecetaDesayuno(pid)
            for pid in sorted(template_ids - presentes_base)
        ]
        extras: list[ExtraRecetaDesayuno] = []
        for i in grupo.ingredientes:
            if i.es_base_receta and i.cantidad < 0:
                extras.append(ExtraRecetaDesayuno(i.producto_id, i.cantidad))
            elif i.es_extra or (not i.es_base_receta and i.cantidad > 0):
                extras.append(ExtraRecetaDesayuno(i.producto_id, i.cantidad))
            elif i.es_omision or (not i.es_base_receta and i.cantidad < 0):
                extras.append(ExtraRecetaDesayuno(i.producto_id, i.cantidad))
        registros.append(RegistroRecetaDesayuno(
            grupo.receta_id,
            grupo.nombre_receta,
            grupo.porciones,
            extras,
            omisiones,
        ))
    return registros


def _validar_stock_registro(
    data: AppData,
    fusionado: dict[str, tuple[float, bool]],
) -> list[str]:
    repo = DataRepository(data)
    deficits: list[str] = []
    for producto_id, (cantidad, _) in fusionado.items():
        if cantidad <= 0:
            continue
        disponible = stock_disponible(data, producto_id)
        if cantidad > disponible:
            nombre = repo.get_nombre_producto(producto_id)
            producto = repo.get_producto(producto_id)
            unidad = producto.unidad.value if producto else ""
            deficits.append(
                f"{nombre}: necesita {cantidad:g} {unidad}, disponible {disponible:g} {unidad}",
            )
    return deficits


def registrar_desayuno(
    fecha: date,
    num_huespedes: int,
    *,
    ignorar_stock: bool = False,
) -> ResultadoOperacion:
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

    fusionado = _aplanar_cesta()
    grupos = list(get_cesta_recetas())

    if not ignorar_stock:
        deficits = _validar_stock_registro(data, fusionado)
        if deficits:
            return ResultadoOperacion(
                False,
                "Stock insuficiente para registrar el desayuno.",
                codigo="STOCK_INSUFICIENTE",
                detalle_stock=deficits,
            )

    lineas: list[LineaDesayuno] = []
    for producto_id, (cantidad, es_extra) in fusionado.items():
        coste = _descontar_fifo(
            data,
            producto_id,
            cantidad,
            permitir_negativo=ignorar_stock,
        )
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
        datetime.now().time(),
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
