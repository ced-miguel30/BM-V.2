"""Motor de cesta de registro parametrizado por prefijo de store.

Cada tipo de servicio (desayuno, comida, cena, bebidas) usa su propio
espacio en ``BasketStore`` para no mezclar cestas. Desayuno conserva
las claves históricas exactas. El adaptador Streamlit vive fuera de este módulo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.bootstrap import get_container
from app.core.application.ports.basket_store import BasketStore
from app.core.repositories.data_repository import DataRepository
from app.core.services.receta_service import calcular_factor_escalado
from app.core.services.unidad_service import cantidad_para_mostrar, presentacion_legible, resolver_presentacion
from app.core.storage.session_store import get_data

PASO_CANTIDAD = 1.0  # Fallback genérico (Ud); preferir paso_unidad() en inputs.


def validar_cantidad_operativa(
    cantidad: float,
    *,
    permitir_cero: bool = False,
    permitir_negativo: bool = False,
) -> str | None:
    """Valida cantidad de cesta (operativo). Devuelve mensaje de error o None."""
    try:
        valor = float(cantidad)
    except (TypeError, ValueError):
        return "La cantidad no es un número válido."
    if not math.isfinite(valor):
        return "La cantidad no puede ser NaN ni infinito."
    if valor == 0 and not permitir_cero:
        return "La cantidad no puede ser 0."
    if valor < 0 and not permitir_negativo:
        return "La cantidad no puede ser negativa."
    return None



@dataclass
class ResultadoOperacionCesta:
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
    cantidad_mostrar: float | None = None
    unidad_mostrar: str | None = None


@dataclass
class GrupoRecetaCesta:
    grupo_id: str
    receta_id: str
    nombre_receta: str
    porciones: float
    ingredientes: list[LineaCestaIngrediente] = field(default_factory=list)
    porciones_estandar: float | None = None
    factor_aplicado: float | None = None


@dataclass
class ModPendienteReceta:
    mod_id: str
    producto_id: str
    nombre: str
    unidad: str
    cantidad: float
    es_extra: bool
    es_omision: bool


def _claves_sesion(prefix: str) -> dict[str, str]:
    """Desayuno mantiene las claves históricas; el resto usa sufijo `{prefix}`."""
    if prefix == "desayuno":
        return {
            "cesta": "bm_cesta_desayuno",
            "recetas": "bm_cesta_recetas",
            "grupo_counter": "bm_grupo_receta_counter",
            "linea_counter": "bm_linea_cesta_counter",
            "mods": "bm_receta_pendiente_mods",
        }
    return {
        "cesta": f"bm_cesta_{prefix}",
        "recetas": f"bm_cesta_recetas_{prefix}",
        "grupo_counter": f"bm_grupo_receta_counter_{prefix}",
        "linea_counter": f"bm_linea_cesta_counter_{prefix}",
        "mods": f"bm_receta_pendiente_mods_{prefix}",
    }


class MotorCesta:
    """Cesta de productos sueltos + grupos de receta, aislada por prefijo."""

    def __init__(
        self,
        session_prefix: str,
        store: BasketStore | None = None,
    ) -> None:
        self.prefix = session_prefix
        self.keys = _claves_sesion(session_prefix)
        self._store = store

    @property
    def store(self) -> BasketStore:
        return self._store if self._store is not None else get_container().basket_store

    def _nueva_linea_id(self) -> str:
        key = self.keys["linea_counter"]
        contador = self.store.get_counter(key) + 1
        self.store.set_counter(key, contador)
        return f"lin_{contador:04d}"

    def _nuevo_grupo_id(self) -> str:
        key = self.keys["grupo_counter"]
        contador = self.store.get_counter(key) + 1
        self.store.set_counter(key, contador)
        return f"grupo_{contador:03d}"

    def get_cesta(self) -> list[LineaCesta]:
        return self.store.get_list(self.keys["cesta"])

    def get_cesta_recetas(self) -> list[GrupoRecetaCesta]:
        key = self.keys["recetas"]
        grupos = self.store.get_list(key)
        # Compat sesión pre-Fase 8: sin factor → vaciar para no mezclar semánticas.
        if grupos and not hasattr(grupos[0], "factor_aplicado"):
            self.store.set_list(key, [])
            return self.store.get_list(key)
        return grupos

    def _guardar_cesta(self, cesta: list[LineaCesta]) -> None:
        self.store.set_list(self.keys["cesta"], cesta)

    def _guardar_cesta_recetas(self, grupos: list[GrupoRecetaCesta]) -> None:
        self.store.set_list(self.keys["recetas"], grupos)

    def get_mods_pendientes(self) -> list[ModPendienteReceta]:
        return self.store.get_list(self.keys["mods"])

    def limpiar_mods_pendientes(self) -> None:
        self.store.set_list(self.keys["mods"], [])

    def limpiar_cesta(self) -> None:
        self.store.set_list(self.keys["cesta"], [])
        self.store.set_list(self.keys["recetas"], [])
        self.limpiar_mods_pendientes()

    def cesta_vacia(self) -> bool:
        return not self.get_cesta() and not self.get_cesta_recetas()

    def anadir_mod_pendiente_receta(self, producto_id: str, cantidad: float) -> ResultadoOperacionCesta:
        error = validar_cantidad_operativa(cantidad, permitir_negativo=True)
        if error:
            return ResultadoOperacionCesta(False, error)

        data = get_data()
        repo = DataRepository(data)
        producto = repo.get_producto(producto_id)
        if not producto:
            return ResultadoOperacionCesta(False, "Producto no encontrado.")

        mods = self.get_mods_pendientes()
        mods.append(ModPendienteReceta(
            self._nueva_linea_id(),
            producto.id,
            producto.nombre,
            producto.unidad.value,
            cantidad,
            es_extra=cantidad > 0,
            es_omision=cantidad < 0,
        ))
        self.store.set_list(self.keys["mods"], mods)

        etiqueta = "c/ extra" if cantidad > 0 else "s/"
        return ResultadoOperacionCesta(True, f"{etiqueta} {producto.nombre} añadido a la receta pendiente.")

    def quitar_mod_pendiente(self, mod_id: str) -> None:
        mods = [m for m in self.get_mods_pendientes() if m.mod_id != mod_id]
        self.store.set_list(self.keys["mods"], mods)

    def anadir_a_cesta(self, producto_id: str, cantidad: float) -> ResultadoOperacionCesta:
        error = validar_cantidad_operativa(cantidad, permitir_negativo=False)
        if error:
            return ResultadoOperacionCesta(False, error)

        data = get_data()
        repo = DataRepository(data)
        producto = repo.get_producto(producto_id)
        if not producto:
            return ResultadoOperacionCesta(False, "Producto no encontrado.")
        if not getattr(producto, "activo", True):
            return ResultadoOperacionCesta(
                False,
                f"«{producto.nombre}» está desactivado y no puede añadirse a registros nuevos.",
            )

        cesta = self.get_cesta()
        paso = abs(cantidad) if cantidad != 0 else PASO_CANTIDAD
        for linea in cesta:
            if linea.producto_id == producto_id:
                nueva = round(linea.cantidad + cantidad, 4)
                err_nueva = validar_cantidad_operativa(nueva, permitir_cero=True, permitir_negativo=False)
                if err_nueva and nueva != 0:
                    return ResultadoOperacionCesta(False, err_nueva)
                if nueva == 0:
                    self.quitar_linea_suelta(linea.linea_id)
                    return ResultadoOperacionCesta(
                        True, f"«{producto.nombre}» eliminado de la cesta.",
                    )
                linea.cantidad = nueva
                linea.es_extra = linea.cantidad > 0
                linea.es_omision = False
                if linea.paso_edicion <= 0:
                    linea.paso_edicion = paso
                self._guardar_cesta(cesta)
                return ResultadoOperacionCesta(
                    True, f"{etiqueta_linea_suelta(linea)} actualizado en la cesta.",
                )

        cesta.append(LineaCesta(
            self._nueva_linea_id(),
            producto_id,
            producto.nombre,
            producto.unidad.value,
            cantidad,
            es_extra=True,
            es_omision=False,
            paso_edicion=paso,
        ))
        self._guardar_cesta(cesta)
        return ResultadoOperacionCesta(
            True, f"{etiqueta_linea_suelta(cesta[-1])} añadido a la cesta.",
        )

    def _linea_ingrediente_desde_mod(self, mod: ModPendienteReceta) -> LineaCestaIngrediente:
        paso = abs(mod.cantidad) if mod.cantidad != 0 else PASO_CANTIDAD
        return LineaCestaIngrediente(
            self._nueva_linea_id(),
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
        self,
        receta_id: str,
        porciones: float,
        mods_pendientes: list[ModPendienteReceta] | None = None,
        *,
        categorias_permitidas: list | None = None,
    ) -> ResultadoOperacionCesta:
        error_cant = validar_cantidad_operativa(porciones, permitir_negativo=False)
        if error_cant:
            return ResultadoOperacionCesta(False, error_cant)

        data = get_data()
        repo = DataRepository(data)
        receta = repo.get_receta(receta_id)
        if not receta:
            return ResultadoOperacionCesta(False, "Receta no encontrada.")
        if not getattr(receta, "activo", True):
            return ResultadoOperacionCesta(
                False,
                f"La receta «{receta.nombre}» está desactivada y no puede usarse en registros nuevos.",
            )
        if categorias_permitidas is not None and receta.categoria not in categorias_permitidas:
            return ResultadoOperacionCesta(
                False,
                f"La receta «{receta.nombre}» no está permitida en este registro.",
            )
        if not receta.ingredientes:
            return ResultadoOperacionCesta(False, f"La receta «{receta.nombre}» no tiene ingredientes.")

        factor, estandar, error = calcular_factor_escalado(porciones, receta.porciones_estandar)
        if error or factor is None or estandar is None:
            return ResultadoOperacionCesta(False, error or "No se pudo calcular el factor de escalado.")

        ingredientes: list[LineaCestaIngrediente] = []
        for ing in receta.ingredientes:
            producto = repo.get_producto(ing.producto_id)
            if not producto:
                return ResultadoOperacionCesta(False, "Un ingrediente de la receta ya no existe en el catálogo.")
            cantidad = round(ing.cantidad * factor, 4)
            cantidad_mostrar, unidad_mostrar = resolver_presentacion(
                ing.cantidad,
                producto.unidad,
                cantidad_presentacion=ing.cantidad_presentacion,
                unidad_presentacion=ing.unidad_presentacion,
                factor=factor,
            )
            paso = (ing.cantidad / estandar) if ing.cantidad > 0 else PASO_CANTIDAD
            ingredientes.append(LineaCestaIngrediente(
                self._nueva_linea_id(),
                producto.id,
                producto.nombre,
                producto.unidad.value,
                cantidad,
                es_base_receta=True,
                es_extra=False,
                es_omision=False,
                paso_edicion=paso,
                cantidad_mostrar=cantidad_mostrar,
                unidad_mostrar=unidad_mostrar,
            ))

        for mod in mods_pendientes or []:
            ingredientes.append(self._linea_ingrediente_desde_mod(mod))

        grupo = GrupoRecetaCesta(
            self._nuevo_grupo_id(),
            receta.id,
            receta.nombre,
            porciones,
            ingredientes,
            porciones_estandar=estandar,
            factor_aplicado=factor,
        )
        grupos = self.get_cesta_recetas()
        grupos.append(grupo)
        self._guardar_cesta_recetas(grupos)
        self.limpiar_mods_pendientes()
        return ResultadoOperacionCesta(
            True,
            f"«{receta.nombre}» ({porciones:g} porciones, factor {factor:g}) añadida a la cesta.",
        )

    def quitar_grupo_receta(self, grupo_id: str) -> str | None:
        """Quita un grupo de receta. Devuelve el nombre si existía."""
        grupo = self._buscar_grupo(grupo_id)
        nombre = grupo.nombre_receta if grupo else None
        grupos = [g for g in self.get_cesta_recetas() if g.grupo_id != grupo_id]
        self._guardar_cesta_recetas(grupos)
        return nombre

    def _buscar_grupo(self, grupo_id: str) -> GrupoRecetaCesta | None:
        return next((g for g in self.get_cesta_recetas() if g.grupo_id == grupo_id), None)

    def _buscar_linea_grupo(self, grupo_id: str, linea_id: str) -> LineaCestaIngrediente | None:
        grupo = self._buscar_grupo(grupo_id)
        if not grupo:
            return None
        return next((i for i in grupo.ingredientes if i.linea_id == linea_id), None)

    def quitar_linea_grupo(self, grupo_id: str, linea_id: str) -> None:
        grupo = self._buscar_grupo(grupo_id)
        if not grupo:
            return
        grupo.ingredientes = [i for i in grupo.ingredientes if i.linea_id != linea_id]
        self._guardar_cesta_recetas(self.get_cesta_recetas())

    def paso_linea_grupo(self, grupo_id: str, linea_id: str) -> float:
        grupo = self._buscar_grupo(grupo_id)
        linea = self._buscar_linea_grupo(grupo_id, linea_id)
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

    def ajustar_linea_grupo(self, grupo_id: str, linea_id: str, delta: float) -> ResultadoOperacionCesta:
        grupo = self._buscar_grupo(grupo_id)
        if not grupo:
            return ResultadoOperacionCesta(False, "Grupo no encontrado.")
        linea = self._buscar_linea_grupo(grupo_id, linea_id)
        if not linea:
            return ResultadoOperacionCesta(False, "Línea no encontrada.")

        nueva = round(linea.cantidad + delta, 4)
        if nueva == 0:
            self.quitar_linea_grupo(grupo_id, linea_id)
            return ResultadoOperacionCesta(True, "Línea eliminada.")
        return self.modificar_linea_grupo(grupo_id, linea_id, nueva)

    def modificar_linea_grupo(self, grupo_id: str, linea_id: str, cantidad: float) -> ResultadoOperacionCesta:
        if cantidad == 0:
            self.quitar_linea_grupo(grupo_id, linea_id)
            return ResultadoOperacionCesta(True, "Línea eliminada.")

        linea = self._buscar_linea_grupo(grupo_id, linea_id)
        if not linea:
            return ResultadoOperacionCesta(False, "Línea no encontrada.")

        linea.cantidad = round(cantidad, 4)
        linea.es_extra = not linea.es_base_receta and cantidad > 0
        linea.es_omision = cantidad < 0 or (not linea.es_base_receta and cantidad < 0)
        if linea.es_base_receta and cantidad < 0:
            linea.es_omision = True
        if linea.unidad_mostrar:
            producto = DataRepository(get_data()).get_producto(linea.producto_id)
            if producto:
                linea.cantidad_mostrar = cantidad_para_mostrar(linea.cantidad, producto.unidad, linea.unidad_mostrar)
        else:
            producto = DataRepository(get_data()).get_producto(linea.producto_id)
            if producto:
                linea.cantidad_mostrar, linea.unidad_mostrar = presentacion_legible(linea.cantidad, producto.unidad)
        self._guardar_cesta_recetas(self.get_cesta_recetas())
        return ResultadoOperacionCesta(True, "Cantidad actualizada.")

    def modificar_porciones_grupo(self, grupo_id: str, porciones: float) -> ResultadoOperacionCesta:
        error_cant = validar_cantidad_operativa(porciones, permitir_negativo=False)
        if error_cant:
            return ResultadoOperacionCesta(False, error_cant)

        data = get_data()
        repo = DataRepository(data)
        grupo = self._buscar_grupo(grupo_id)
        if not grupo:
            return ResultadoOperacionCesta(False, "Grupo no encontrado.")

        receta = repo.get_receta(grupo.receta_id)
        if not receta:
            return ResultadoOperacionCesta(False, "Receta no encontrada.")

        estandar_ref = grupo.porciones_estandar if grupo.porciones_estandar else receta.porciones_estandar
        factor, estandar, error = calcular_factor_escalado(porciones, estandar_ref)
        if error or factor is None or estandar is None:
            return ResultadoOperacionCesta(False, error or "No se pudo calcular el factor de escalado.")

        grupo.porciones = porciones
        grupo.porciones_estandar = estandar
        grupo.factor_aplicado = factor

        for linea in grupo.ingredientes:
            if not linea.es_base_receta:
                continue
            ing_template = next((i for i in receta.ingredientes if i.producto_id == linea.producto_id), None)
            if not ing_template:
                continue
            producto = repo.get_producto(linea.producto_id)
            if not producto:
                continue
            linea.cantidad = round(ing_template.cantidad * factor, 4)
            linea.paso_edicion = (
                (ing_template.cantidad / estandar) if ing_template.cantidad > 0 else PASO_CANTIDAD
            )
            linea.cantidad_mostrar, linea.unidad_mostrar = resolver_presentacion(
                ing_template.cantidad,
                producto.unidad,
                cantidad_presentacion=ing_template.cantidad_presentacion,
                unidad_presentacion=ing_template.unidad_presentacion,
                factor=factor,
            )

        self._guardar_cesta_recetas(self.get_cesta_recetas())
        return ResultadoOperacionCesta(True, f"Porciones actualizadas (factor {factor:g}).")

    def ajustar_porciones_grupo(self, grupo_id: str, delta: float) -> ResultadoOperacionCesta:
        grupo = self._buscar_grupo(grupo_id)
        if not grupo:
            return ResultadoOperacionCesta(False, "Grupo no encontrado.")
        nuevas = round(grupo.porciones + delta, 4)
        if nuevas <= 0:
            self.quitar_grupo_receta(grupo_id)
            return ResultadoOperacionCesta(True, "Receta eliminada de la cesta.")
        return self.modificar_porciones_grupo(grupo_id, nuevas)

    def _buscar_linea_suelta(self, linea_id: str) -> LineaCesta | None:
        return next((l for l in self.get_cesta() if l.linea_id == linea_id), None)

    def paso_linea_suelta(self, linea_id: str) -> float:
        linea = self._buscar_linea_suelta(linea_id)
        if not linea:
            return PASO_CANTIDAD
        if linea.paso_edicion > 0:
            return linea.paso_edicion
        if linea.cantidad != 0:
            return abs(linea.cantidad)
        return PASO_CANTIDAD

    def quitar_linea_suelta(self, linea_id: str) -> str | None:
        """Quita una línea suelta. Devuelve el nombre eliminado si existía."""
        linea = self._buscar_linea_suelta(linea_id)
        nombre = linea.nombre if linea else None
        cesta = [l for l in self.get_cesta() if l.linea_id != linea_id]
        self._guardar_cesta(cesta)
        return nombre

    def ajustar_cantidad_suelto(self, linea_id: str, delta: float) -> ResultadoOperacionCesta:
        linea = self._buscar_linea_suelta(linea_id)
        if not linea:
            return ResultadoOperacionCesta(False, "Línea no encontrada.")
        nueva = round(linea.cantidad + delta, 4)
        if nueva == 0:
            self.quitar_linea_suelta(linea_id)
            return ResultadoOperacionCesta(True, "Producto eliminado de la cesta.")
        return self.modificar_cantidad_suelto(linea_id, nueva)

    def modificar_cantidad_suelto(self, linea_id: str, cantidad: float) -> ResultadoOperacionCesta:
        error = validar_cantidad_operativa(
            cantidad, permitir_cero=True, permitir_negativo=False,
        )
        if error and cantidad != 0:
            return ResultadoOperacionCesta(False, error)
        if cantidad == 0:
            linea = self._buscar_linea_suelta(linea_id)
            nombre = linea.nombre if linea else "Producto"
            self.quitar_linea_suelta(linea_id)
            return ResultadoOperacionCesta(True, f"«{nombre}» eliminado de la cesta.")

        linea = self._buscar_linea_suelta(linea_id)
        if not linea:
            return ResultadoOperacionCesta(False, "Línea no encontrada.")

        linea.cantidad = round(cantidad, 4)
        linea.es_extra = cantidad > 0
        linea.es_omision = False
        self._guardar_cesta(self.get_cesta())
        return ResultadoOperacionCesta(True, "Cantidad actualizada.")


def etiqueta_linea_suelta(linea: LineaCesta) -> str:
    cant = abs(linea.cantidad)
    return f"{linea.nombre} — {cant:g} {linea.unidad}"


def etiqueta_linea_receta(ing: LineaCestaIngrediente) -> str:
    if ing.unidad_mostrar and ing.cantidad_mostrar is not None:
        cant, unidad = abs(ing.cantidad_mostrar), ing.unidad_mostrar
    else:
        from app.core.models import UnidadProducto
        cant, unidad = presentacion_legible(abs(ing.cantidad), UnidadProducto(ing.unidad))
    if ing.es_omision or ing.cantidad < 0:
        return f"s/ {ing.nombre} — {cant:g} {unidad}"
    if ing.es_extra:
        return f"c/ extra {ing.nombre} — {cant:g} {unidad}"
    return f"{ing.nombre} — {cant:g} {unidad}"


def cantidad_texto_linea_receta(ing: LineaCestaIngrediente) -> str:
    if ing.unidad_mostrar and ing.cantidad_mostrar is not None:
        return f"{abs(ing.cantidad_mostrar):g}"
    from app.core.models import UnidadProducto
    cant, _ = presentacion_legible(abs(ing.cantidad), UnidadProducto(ing.unidad))
    return f"{cant:g}"


def crear_motor_cesta(session_prefix: str) -> MotorCesta:
    return MotorCesta(session_prefix)
