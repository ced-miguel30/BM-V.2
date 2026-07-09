"""Servicio de gestión de recetas."""

from dataclasses import dataclass
from datetime import datetime

from app.core.models import AppData, IngredienteReceta, Receta
from app.core.repositories.data_repository import DataRepository
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


def listar_recetas() -> list[Receta]:
    data = get_data()
    return sorted(data.recetas, key=lambda r: r.nombre.lower())


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
            partes.append(f"{producto.nombre} {ing.cantidad:g} {producto.unidad.value}")
    return ", ".join(partes)


def recetas_para_selector() -> list[dict]:
    resultado = []
    for receta in listar_recetas():
        resultado.append({
            "id": receta.id,
            "nombre": receta.nombre,
            "etiqueta": f"{receta.nombre} ({len(receta.ingredientes)} ingredientes)",
        })
    return resultado


def crear_receta(nombre: str, ingredientes: list[IngredienteReceta]) -> ResultadoOperacion:
    nombre = _normalizar_nombre(nombre)
    if not nombre:
        return ResultadoOperacion(False, "El nombre de la receta es obligatorio.")

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
    )
    data.recetas.append(receta)
    _registrar_actividad(data, "Crear receta", f"«{nombre}» creada con {len(ingredientes)} ingrediente(s)")
    persist_data(data)
    return ResultadoOperacion(True, f"Receta «{nombre}» creada correctamente.")


def editar_receta(
    receta_id: str,
    nombre: str,
    ingredientes: list[IngredienteReceta],
) -> ResultadoOperacion:
    nombre = _normalizar_nombre(nombre)
    if not nombre:
        return ResultadoOperacion(False, "El nombre de la receta es obligatorio.")

    data = get_data()
    receta = obtener_receta(receta_id)
    if not receta:
        return ResultadoOperacion(False, "Receta no encontrada.")

    if _nombre_duplicado(data, nombre, excluir_id=receta_id):
        return ResultadoOperacion(False, f"Ya existe una receta llamada «{nombre}».")

    error = _validar_ingredientes(data, ingredientes)
    if error:
        return error

    receta.nombre = nombre
    receta.ingredientes = ingredientes
    _registrar_actividad(data, "Editar receta", f"«{nombre}» actualizada")
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
