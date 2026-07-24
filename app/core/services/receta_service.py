"""Servicio de gestión de recetas."""

from dataclasses import dataclass
from datetime import datetime

from app.core.models import (
    CATEGORIA_RECETA_LABEL,
    AppData,
    CategoriaReceta,
    IngredienteReceta,
    Receta,
)
from app.core.repositories.data_repository import DataRepository
from app.core.services.stock_service import (
    disponible_en_servicio,
    normalizar_servicios_disponibles,
)
from app.core.services.unidad_service import cantidad_y_unidad_mostrar
from app.core.storage.session_store import get_data, persist_data


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
    from app.core.models import Actividad

    actividad = Actividad(
        _next_id("act", [a.id for a in data.actividades]),
        datetime.now(),
        _nombre_usuario(data),
        accion,
        detalle,
    )
    data.actividades.insert(0, actividad)


def _normalizar_nombre(nombre: str) -> str:
    return " ".join(nombre.strip().split())


def _resolver_categoria(categoria: CategoriaReceta | str) -> CategoriaReceta | ResultadoOperacion:
    """Acepta el enum o su valor interno; rechaza cualquier otra cadena."""
    if isinstance(categoria, CategoriaReceta):
        return categoria
    try:
        return CategoriaReceta(categoria)
    except ValueError:
        return ResultadoOperacion(False, f"Categoría no válida: «{categoria}».")


def etiqueta_categoria(categoria: CategoriaReceta) -> str:
    return CATEGORIA_RECETA_LABEL.get(categoria, categoria.value)


def _validar_ingredientes(
    data: AppData,
    ingredientes: list[IngredienteReceta],
) -> ResultadoOperacion | None:
    if not ingredientes:
        return ResultadoOperacion(False, "Añada al menos un ingrediente.")
    repo = DataRepository(data)
    vistos: set[str] = set()
    for ing in ingredientes:
        if ing.cantidad <= 0:
            return ResultadoOperacion(False, "Las cantidades deben ser mayores que 0.")
        if ing.producto_id in vistos:
            producto = repo.get_producto(ing.producto_id)
            nombre = producto.nombre if producto else ing.producto_id
            return ResultadoOperacion(False, f"El producto «{nombre}» está duplicado en la receta.")
        vistos.add(ing.producto_id)
        if not repo.get_producto(ing.producto_id):
            return ResultadoOperacion(False, "Uno de los productos seleccionados no existe.")
    return None


def _nombre_duplicado(data: AppData, nombre: str, excluir_id: str | None = None) -> bool:
    nombre_norm = _normalizar_nombre(nombre).lower()
    for receta in data.recetas:
        if excluir_id and receta.id == excluir_id:
            continue
        if receta.nombre.strip().lower() == nombre_norm:
            return True
    return False


def listar_recetas(
    categoria: CategoriaReceta | None = None,
    categorias: list[CategoriaReceta] | None = None,
    *,
    servicio_disponible: str | None = None,
) -> list[Receta]:
    data = get_data()
    recetas = data.recetas
    if categorias is not None:
        permitidas = set(categorias)
        recetas = [r for r in recetas if r.categoria in permitidas]
    elif categoria is not None:
        recetas = [r for r in recetas if r.categoria == categoria]
    if servicio_disponible is not None:
        recetas = [
            r for r in recetas
            if disponible_en_servicio(r.servicios_disponibles, servicio_disponible)
        ]
    return sorted(recetas, key=lambda r: r.nombre.lower())


def obtener_receta(receta_id: str) -> Receta | None:
    data = get_data()
    return next((r for r in data.recetas if r.id == receta_id), None)


def resumen_ingredientes(receta: Receta) -> str:
    data = get_data()
    repo = DataRepository(data)
    partes = []
    for ing in receta.ingredientes:
        producto = repo.get_producto(ing.producto_id)
        if producto:
            cantidad, unidad = cantidad_y_unidad_mostrar(
                ing.cantidad, producto.unidad, ing.cantidad_presentacion, ing.unidad_presentacion,
            )
            partes.append(f"{producto.nombre} {cantidad:g} {unidad}")
    return ", ".join(partes)


def recetas_para_selector(
    categoria: CategoriaReceta | None = None,
    categorias: list[CategoriaReceta] | None = None,
) -> list[dict]:
    resultado = []
    for receta in listar_recetas(categoria=categoria, categorias=categorias):
        resultado.append({
            "id": receta.id,
            "nombre": receta.nombre,
            "categoria": receta.categoria.value,
            "etiqueta": (
                f"{receta.nombre} ({etiqueta_categoria(receta.categoria)}, "
                f"{len(receta.ingredientes)} ingredientes)"
            ),
        })
    return resultado


def crear_receta(
    nombre: str,
    ingredientes: list[IngredienteReceta],
    categoria: CategoriaReceta | str = CategoriaReceta.DESAYUNO,
    *,
    servicios_disponibles: list[str] | None = None,
) -> ResultadoOperacion:
    nombre = _normalizar_nombre(nombre)
    if not nombre:
        return ResultadoOperacion(False, "El nombre de la receta es obligatorio.")

    categoria_resuelta = _resolver_categoria(categoria)
    if isinstance(categoria_resuelta, ResultadoOperacion):
        return categoria_resuelta

    data = get_data()
    if _nombre_duplicado(data, nombre):
        return ResultadoOperacion(False, f"Ya existe una receta llamada «{nombre}».")

    error = _validar_ingredientes(data, ingredientes)
    if error:
        return error

    receta = Receta(
        _next_id("r", [r.id for r in data.recetas]),
        nombre,
        ingredientes,
        categoria_resuelta,
        normalizar_servicios_disponibles(servicios_disponibles),
    )
    data.recetas.append(receta)
    _registrar_actividad(
        data,
        "Crear receta",
        (
            f"«{nombre}» creada ({etiqueta_categoria(categoria_resuelta)}) "
            f"con {len(ingredientes)} ingrediente(s)"
        ),
    )
    persist_data(data)
    return ResultadoOperacion(True, f"Receta «{nombre}» creada correctamente.")


def editar_receta(
    receta_id: str,
    nombre: str,
    ingredientes: list[IngredienteReceta],
    categoria: CategoriaReceta | str = CategoriaReceta.DESAYUNO,
    *,
    servicios_disponibles: list[str] | None = None,
) -> ResultadoOperacion:
    nombre = _normalizar_nombre(nombre)
    if not nombre:
        return ResultadoOperacion(False, "El nombre de la receta es obligatorio.")

    categoria_resuelta = _resolver_categoria(categoria)
    if isinstance(categoria_resuelta, ResultadoOperacion):
        return categoria_resuelta

    data = get_data()
    receta = obtener_receta(receta_id)
    if not receta:
        return ResultadoOperacion(False, "Receta no encontrada.")

    if _nombre_duplicado(data, nombre, excluir_id=receta_id):
        return ResultadoOperacion(False, f"Ya existe una receta llamada «{nombre}».")

    error = _validar_ingredientes(data, ingredientes)
    if error:
        return error

    servicios = normalizar_servicios_disponibles(servicios_disponibles)
    solo_categoria = (
        receta.nombre == nombre
        and receta.ingredientes == ingredientes
        and receta.categoria != categoria_resuelta
        and receta.servicios_disponibles == servicios
    )
    categoria_anterior = receta.categoria

    receta.nombre = nombre
    receta.ingredientes = ingredientes
    receta.categoria = categoria_resuelta
    receta.servicios_disponibles = servicios

    if solo_categoria:
        detalle = (
            f"«{nombre}»: categoría "
            f"{etiqueta_categoria(categoria_anterior)} → {etiqueta_categoria(categoria_resuelta)}"
        )
    else:
        detalle = (
            f"«{nombre}» actualizada ({etiqueta_categoria(categoria_resuelta)})"
        )
    _registrar_actividad(data, "Editar receta", detalle)
    persist_data(data)
    return ResultadoOperacion(True, f"Receta «{nombre}» guardada correctamente.")


def eliminar_receta(receta_id: str) -> ResultadoOperacion:
    data = get_data()
    receta = next((r for r in data.recetas if r.id == receta_id), None)
    if not receta:
        return ResultadoOperacion(False, "Receta no encontrada.")

    nombre = receta.nombre
    data.recetas = [r for r in data.recetas if r.id != receta_id]
    _registrar_actividad(data, "Eliminar receta", f"«{nombre}» eliminada")
    persist_data(data)
    return ResultadoOperacion(True, f"Receta «{nombre}» eliminada.")
