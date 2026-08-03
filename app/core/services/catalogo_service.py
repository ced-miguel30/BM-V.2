"""Catálogos de inventario — departamentos, categorías, subcategorías (Fase 6A).

Usa AppContext / UoW. No toca FIFO ni flujos de consumo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.application.context import AppContext
from app.core.application.id_generator import next_id
from app.core.models import AppData, Categoria, Departamento, Subcategoria, Ubicacion
from app.core.models.enums import (
    TIPO_ARTICULO_LABEL,
    TIPO_ARTICULO_VALORES,
    TipoArticulo,
)
from app.core.storage.session_store import get_data, persist_data

ETIQUETA_REF_NO_ENCONTRADA = "Referencia no encontrada"


@dataclass
class ResultadoOperacion:
    ok: bool
    mensaje: str


class _CompatSessionUow:
    def get_data(self) -> AppData:
        return get_data()

    def commit(self, data: AppData | None = None) -> AppData:
        return persist_data(data if data is not None else get_data())


def _ctx(ctx: AppContext | None = None) -> AppContext:
    if ctx is not None:
        return ctx
    from app.core.application.actor import actor_desde_appdata
    from app.core.application.clock import SystemClock

    uow = _CompatSessionUow()
    return AppContext(
        uow=uow,
        actor=actor_desde_appdata(uow.get_data()),
        clock=SystemClock(),
    )


def _registrar_actividad(ctx: AppContext, accion: str, detalle: str) -> None:
    from app.core.application.auditoria import registrar_actividad

    registrar_actividad(ctx, accion, detalle, commit=False)


def normalizar_nombre_catalogo(valor: str | None) -> str:
    """Normaliza para unicidad: trim, colapsar espacios, minúsculas."""
    if not valor:
        return ""
    return re.sub(r"\s+", " ", valor.strip()).lower()


def _nombre_presentacion(valor: str) -> str:
    return re.sub(r"\s+", " ", (valor or "").strip())


# --- Resolución de etiquetas (UI / diagnóstico) ---

def etiqueta_departamento(data: AppData, departamento_id: str | None) -> str:
    if not departamento_id:
        return "No configurado"
    dep = next((d for d in data.departamentos if d.id == departamento_id), None)
    return dep.nombre if dep else ETIQUETA_REF_NO_ENCONTRADA


def etiqueta_categoria(data: AppData, categoria_id: str | None) -> str:
    if not categoria_id:
        return "No configurado"
    cat = next((c for c in data.categorias if c.id == categoria_id), None)
    return cat.nombre if cat else ETIQUETA_REF_NO_ENCONTRADA


def etiqueta_subcategoria(data: AppData, subcategoria_id: str | None) -> str:
    if not subcategoria_id:
        return "No configurado"
    sub = next((s for s in data.subcategorias if s.id == subcategoria_id), None)
    return sub.nombre if sub else ETIQUETA_REF_NO_ENCONTRADA


def etiqueta_ubicacion(data: AppData, ubicacion_id: str | None) -> str:
    if not ubicacion_id:
        return "No configurado"
    ubi = next((u for u in data.ubicaciones if u.id == ubicacion_id), None)
    return ubi.nombre if ubi else ETIQUETA_REF_NO_ENCONTRADA


# --- Tipo de artículo (Fase 6C) ---

def parse_tipo_articulo(valor: TipoArticulo | str | None) -> TipoArticulo | str | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, TipoArticulo):
        return valor
    try:
        return TipoArticulo(str(valor))
    except ValueError:
        return str(valor)


def es_tipo_articulo_conocido(valor: TipoArticulo | str | None) -> bool:
    if valor is None:
        return False
    if isinstance(valor, TipoArticulo):
        return True
    return str(valor) in TIPO_ARTICULO_VALORES


def etiqueta_tipo_articulo(valor: TipoArticulo | str | None) -> str:
    if valor is None or valor == "":
        return "Sin clasificar"
    if isinstance(valor, TipoArticulo):
        return TIPO_ARTICULO_LABEL[valor]
    try:
        return TIPO_ARTICULO_LABEL[TipoArticulo(str(valor))]
    except ValueError:
        return f"Valor desconocido ({valor})"


def validar_tipo_articulo(
    valor: TipoArticulo | str | None,
    *,
    obligatorio: bool = False,
) -> ResultadoOperacion:
    """Validación central de tipo de artículo.

    - Alta nueva: obligatorio=True → exige enum conocido.
    - Histórico: obligatorio=False → None permitido temporalmente.
    """
    if valor is None or valor == "":
        if obligatorio:
            return ResultadoOperacion(False, "Seleccione el tipo de artículo.")
        return ResultadoOperacion(True, "OK")
    if isinstance(valor, TipoArticulo):
        return ResultadoOperacion(True, "OK")
    try:
        TipoArticulo(str(valor))
        return ResultadoOperacion(True, "OK")
    except ValueError:
        return ResultadoOperacion(
            False,
            f"Tipo de artículo no válido: «{valor}». "
            "Use Consumible o Reutilizable.",
        )


def normalizar_tipo_articulo_conocido(
    valor: TipoArticulo | str | None,
) -> TipoArticulo | None:
    """Devuelve enum o None; no convierte desconocidos a consumible."""
    parsed = parse_tipo_articulo(valor)
    if parsed is None:
        return None
    if isinstance(parsed, TipoArticulo):
        return parsed
    try:
        return TipoArticulo(str(parsed))
    except ValueError:
        return None


# --- Listados ---

def listar_departamentos(
    *,
    solo_activos: bool = False,
    ctx: AppContext | None = None,
) -> list[Departamento]:
    data = _ctx(ctx).data()
    items = list(data.departamentos)
    if solo_activos:
        items = [d for d in items if d.activo]
    return sorted(items, key=lambda d: d.nombre.lower())


def listar_categorias(
    *,
    solo_activos: bool = False,
    ctx: AppContext | None = None,
) -> list[Categoria]:
    data = _ctx(ctx).data()
    items = list(data.categorias)
    if solo_activos:
        items = [c for c in items if c.activo]
    return sorted(items, key=lambda c: c.nombre.lower())


def listar_subcategorias(
    *,
    categoria_id: str | None = None,
    solo_activos: bool = False,
    ctx: AppContext | None = None,
) -> list[Subcategoria]:
    data = _ctx(ctx).data()
    items = list(data.subcategorias)
    if categoria_id is not None:
        items = [s for s in items if s.categoria_id == categoria_id]
    if solo_activos:
        items = [s for s in items if s.activo]
    return sorted(items, key=lambda s: s.nombre.lower())


def opciones_categoria_asignacion(
    data: AppData,
    *,
    conservar_id: str | None = None,
) -> list[Categoria]:
    """Activas + conservar inactiva/huérfana ya asignada (sin ofrecer otras inactivas)."""
    activas = [c for c in data.categorias if c.activo]
    if conservar_id and not any(c.id == conservar_id for c in activas):
        actual = next((c for c in data.categorias if c.id == conservar_id), None)
        if actual is not None:
            return sorted([*activas, actual], key=lambda c: c.nombre.lower())
    return sorted(activas, key=lambda c: c.nombre.lower())


def opciones_subcategoria_asignacion(
    data: AppData,
    categoria_id: str | None,
    *,
    conservar_id: str | None = None,
) -> list[Subcategoria]:
    """Subcategorías activas de una categoría activa; conserva la asignada."""
    if not categoria_id:
        if conservar_id:
            actual = next((s for s in data.subcategorias if s.id == conservar_id), None)
            return [actual] if actual is not None else []
        return []
    cat = next((c for c in data.categorias if c.id == categoria_id), None)
    if cat is None or not cat.activo:
        # Categoría inactiva: no ofrecer nuevas; solo conservar.
        if conservar_id:
            actual = next((s for s in data.subcategorias if s.id == conservar_id), None)
            return [actual] if actual is not None else []
        return []
    activas = [
        s for s in data.subcategorias
        if s.categoria_id == categoria_id and s.activo
    ]
    if conservar_id and not any(s.id == conservar_id for s in activas):
        actual = next((s for s in data.subcategorias if s.id == conservar_id), None)
        if actual is not None:
            return sorted([*activas, actual], key=lambda s: s.nombre.lower())
    return sorted(activas, key=lambda s: s.nombre.lower())


def opciones_departamento_asignacion(
    data: AppData,
    *,
    conservar_ids: list[str] | None = None,
) -> list[Departamento]:
    conservar = set(conservar_ids or [])
    activas = [d for d in data.departamentos if d.activo]
    ids_activos = {d.id for d in activas}
    extras = [
        d for d in data.departamentos
        if d.id in conservar and d.id not in ids_activos
    ]
    return sorted([*activas, *extras], key=lambda d: d.nombre.lower())


def listar_ubicaciones(
    *,
    solo_activos: bool = False,
    ctx: AppContext | None = None,
) -> list[Ubicacion]:
    data = _ctx(ctx).data()
    items = list(data.ubicaciones)
    if solo_activos:
        items = [u for u in items if u.activo]
    return sorted(items, key=lambda u: u.nombre.lower())


def opciones_ubicacion_asignacion(
    data: AppData,
    *,
    conservar_ids: list[str] | None = None,
) -> list[Ubicacion]:
    """Activas + inactivas ya asignadas (para conservar en edición)."""
    conservar = set(conservar_ids or [])
    activas = [u for u in data.ubicaciones if u.activo]
    ids_activos = {u.id for u in activas}
    extras = [
        u for u in data.ubicaciones
        if u.id in conservar and u.id not in ids_activos
    ]
    return sorted([*activas, *extras], key=lambda u: u.nombre.lower())


# --- Validación de producto (centralizada) ---

def validar_referencias_producto(
    data: AppData,
    *,
    categoria_id: str | None,
    subcategoria_id: str | None,
    departamento_ids: list[str] | None,
    ubicacion_ids: list[str] | None = None,
    categoria_id_anterior: str | None = None,
    subcategoria_id_anterior: str | None = None,
    departamento_ids_anteriores: list[str] | None = None,
    ubicacion_ids_anteriores: list[str] | None = None,
) -> ResultadoOperacion:
    """Valida FKs de catálogo. Permite conservar referencias inactivas ya asignadas."""
    ant_deps = list(departamento_ids_anteriores or [])
    ant_ubis = list(ubicacion_ids_anteriores or [])

    if categoria_id:
        cat = next((c for c in data.categorias if c.id == categoria_id), None)
        if cat is None:
            return ResultadoOperacion(False, "La categoría seleccionada no existe.")
        if not cat.activo and categoria_id != categoria_id_anterior:
            return ResultadoOperacion(
                False,
                "La categoría está inactiva y no puede asignarse de nuevo.",
            )

    if subcategoria_id:
        sub = next((s for s in data.subcategorias if s.id == subcategoria_id), None)
        if sub is None:
            return ResultadoOperacion(False, "La subcategoría seleccionada no existe.")
        if not categoria_id:
            return ResultadoOperacion(
                False,
                "Indique la categoría antes de asignar una subcategoría.",
            )
        if sub.categoria_id != categoria_id:
            return ResultadoOperacion(
                False,
                "La subcategoría no pertenece a la categoría seleccionada.",
            )
        cat_padre = next((c for c in data.categorias if c.id == sub.categoria_id), None)
        if cat_padre is not None and not cat_padre.activo and subcategoria_id != subcategoria_id_anterior:
            return ResultadoOperacion(
                False,
                "La categoría de la subcategoría está inactiva; no se admiten nuevas asignaciones.",
            )
        if not sub.activo and subcategoria_id != subcategoria_id_anterior:
            return ResultadoOperacion(
                False,
                "La subcategoría está inactiva y no puede asignarse de nuevo.",
            )

    deps = list(departamento_ids or [])
    if len(deps) != len(set(deps)):
        return ResultadoOperacion(False, "Hay departamentos duplicados en la selección.")
    for dep_id in deps:
        dep = next((d for d in data.departamentos if d.id == dep_id), None)
        if dep is None:
            return ResultadoOperacion(
                False, f"El departamento «{dep_id}» no existe.",
            )
        if not dep.activo and dep_id not in ant_deps:
            return ResultadoOperacion(
                False,
                f"El departamento «{dep.nombre}» está inactivo y no puede asignarse de nuevo.",
            )

    ubis = list(ubicacion_ids or [])
    if len(ubis) != len(set(ubis)):
        return ResultadoOperacion(False, "Hay ubicaciones duplicadas en la selección.")
    for ubi_id in ubis:
        ubi = next((u for u in data.ubicaciones if u.id == ubi_id), None)
        if ubi is None:
            return ResultadoOperacion(
                False, f"La ubicación «{ubi_id}» no existe.",
            )
        if not ubi.activo and ubi_id not in ant_ubis:
            return ResultadoOperacion(
                False,
                f"La ubicación «{ubi.nombre}» está inactiva y no puede asignarse de nuevo.",
            )
    return ResultadoOperacion(True, "OK")


def normalizar_departamento_ids(ids: list[str] | None) -> list[str]:
    return _normalizar_lista_ids(ids)


def normalizar_ubicacion_ids(ids: list[str] | None) -> list[str]:
    return _normalizar_lista_ids(ids)


def _normalizar_lista_ids(ids: list[str] | None) -> list[str]:
    if not ids:
        return []
    vistos: set[str] = set()
    out: list[str] = []
    for i in ids:
        if not isinstance(i, str) or not i or i in vistos:
            continue
        vistos.add(i)
        out.append(i)
    return out


# --- CRUD Departamentos ---

def crear_departamento(
    nombre: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    texto = _nombre_presentacion(nombre)
    if not texto:
        return ResultadoOperacion(False, "Indique un nombre de departamento.")
    context = _ctx(ctx)
    data = context.data()
    clave = normalizar_nombre_catalogo(texto)
    if any(normalizar_nombre_catalogo(d.nombre) == clave for d in data.departamentos):
        return ResultadoOperacion(False, "Ya existe un departamento con ese nombre.")
    nuevo = Departamento(
        next_id("dep", [d.id for d in data.departamentos]),
        texto,
        True,
    )
    data.departamentos.append(nuevo)
    _registrar_actividad(context, "Catálogo departamento", f"Alta: {texto}")
    context.uow.commit(data)
    return ResultadoOperacion(True, f"Departamento «{texto}» creado.")


def renombrar_departamento(
    departamento_id: str,
    nombre: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    texto = _nombre_presentacion(nombre)
    if not texto:
        return ResultadoOperacion(False, "Indique un nombre de departamento.")
    context = _ctx(ctx)
    data = context.data()
    actual = next((d for d in data.departamentos if d.id == departamento_id), None)
    if not actual:
        return ResultadoOperacion(False, "Departamento no encontrado.")
    clave = normalizar_nombre_catalogo(texto)
    if any(
        d.id != departamento_id and normalizar_nombre_catalogo(d.nombre) == clave
        for d in data.departamentos
    ):
        return ResultadoOperacion(False, "Ya existe un departamento con ese nombre.")
    anterior = actual.nombre
    actual.nombre = texto
    _registrar_actividad(
        context, "Catálogo departamento", f"Renombrado: {anterior} → {texto}",
    )
    context.uow.commit(data)
    return ResultadoOperacion(True, f"Departamento actualizado a «{texto}».")


def desactivar_departamento(
    departamento_id: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    context = _ctx(ctx)
    data = context.data()
    actual = next((d for d in data.departamentos if d.id == departamento_id), None)
    if not actual:
        return ResultadoOperacion(False, "Departamento no encontrado.")
    if not actual.activo:
        return ResultadoOperacion(False, "El departamento ya está inactivo.")
    actual.activo = False
    _registrar_actividad(context, "Catálogo departamento", f"Desactivado: {actual.nombre}")
    context.uow.commit(data)
    return ResultadoOperacion(True, f"Departamento «{actual.nombre}» desactivado.")


def reactivar_departamento(
    departamento_id: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    context = _ctx(ctx)
    data = context.data()
    actual = next((d for d in data.departamentos if d.id == departamento_id), None)
    if not actual:
        return ResultadoOperacion(False, "Departamento no encontrado.")
    if actual.activo:
        return ResultadoOperacion(False, "El departamento ya está activo.")
    clave = normalizar_nombre_catalogo(actual.nombre)
    if any(
        d.id != departamento_id and d.activo and normalizar_nombre_catalogo(d.nombre) == clave
        for d in data.departamentos
    ):
        return ResultadoOperacion(
            False,
            "No se puede reactivar: ya hay un departamento activo con ese nombre.",
        )
    actual.activo = True
    _registrar_actividad(context, "Catálogo departamento", f"Reactivado: {actual.nombre}")
    context.uow.commit(data)
    return ResultadoOperacion(True, f"Departamento «{actual.nombre}» reactivado.")


# --- CRUD Categorías ---

def crear_categoria(
    nombre: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    texto = _nombre_presentacion(nombre)
    if not texto:
        return ResultadoOperacion(False, "Indique un nombre de categoría.")
    context = _ctx(ctx)
    data = context.data()
    clave = normalizar_nombre_catalogo(texto)
    if any(normalizar_nombre_catalogo(c.nombre) == clave for c in data.categorias):
        return ResultadoOperacion(False, "Ya existe una categoría con ese nombre.")
    nuevo = Categoria(
        next_id("cat", [c.id for c in data.categorias]),
        texto,
        True,
    )
    data.categorias.append(nuevo)
    _registrar_actividad(context, "Catálogo categoría", f"Alta: {texto}")
    context.uow.commit(data)
    return ResultadoOperacion(True, f"Categoría «{texto}» creada.")


def renombrar_categoria(
    categoria_id: str,
    nombre: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    texto = _nombre_presentacion(nombre)
    if not texto:
        return ResultadoOperacion(False, "Indique un nombre de categoría.")
    context = _ctx(ctx)
    data = context.data()
    actual = next((c for c in data.categorias if c.id == categoria_id), None)
    if not actual:
        return ResultadoOperacion(False, "Categoría no encontrada.")
    clave = normalizar_nombre_catalogo(texto)
    if any(
        c.id != categoria_id and normalizar_nombre_catalogo(c.nombre) == clave
        for c in data.categorias
    ):
        return ResultadoOperacion(False, "Ya existe una categoría con ese nombre.")
    anterior = actual.nombre
    actual.nombre = texto
    _registrar_actividad(
        context, "Catálogo categoría", f"Renombrado: {anterior} → {texto}",
    )
    context.uow.commit(data)
    return ResultadoOperacion(True, f"Categoría actualizada a «{texto}».")


def desactivar_categoria(
    categoria_id: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    context = _ctx(ctx)
    data = context.data()
    actual = next((c for c in data.categorias if c.id == categoria_id), None)
    if not actual:
        return ResultadoOperacion(False, "Categoría no encontrada.")
    if not actual.activo:
        return ResultadoOperacion(False, "La categoría ya está inactiva.")
    actual.activo = False
    _registrar_actividad(context, "Catálogo categoría", f"Desactivada: {actual.nombre}")
    context.uow.commit(data)
    return ResultadoOperacion(
        True,
        f"Categoría «{actual.nombre}» desactivada. "
        "Sus subcategorías no se ofrecen para nuevas asignaciones.",
    )


def reactivar_categoria(
    categoria_id: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    context = _ctx(ctx)
    data = context.data()
    actual = next((c for c in data.categorias if c.id == categoria_id), None)
    if not actual:
        return ResultadoOperacion(False, "Categoría no encontrada.")
    if actual.activo:
        return ResultadoOperacion(False, "La categoría ya está activa.")
    clave = normalizar_nombre_catalogo(actual.nombre)
    if any(
        c.id != categoria_id and c.activo and normalizar_nombre_catalogo(c.nombre) == clave
        for c in data.categorias
    ):
        return ResultadoOperacion(
            False,
            "No se puede reactivar: ya hay una categoría activa con ese nombre.",
        )
    actual.activo = True
    _registrar_actividad(context, "Catálogo categoría", f"Reactivada: {actual.nombre}")
    context.uow.commit(data)
    return ResultadoOperacion(True, f"Categoría «{actual.nombre}» reactivada.")


# --- CRUD Subcategorías ---

def crear_subcategoria(
    nombre: str,
    categoria_id: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    texto = _nombre_presentacion(nombre)
    if not texto:
        return ResultadoOperacion(False, "Indique un nombre de subcategoría.")
    if not categoria_id:
        return ResultadoOperacion(False, "Seleccione la categoría padre.")
    context = _ctx(ctx)
    data = context.data()
    cat = next((c for c in data.categorias if c.id == categoria_id), None)
    if cat is None:
        return ResultadoOperacion(False, "La categoría seleccionada no existe.")
    clave = normalizar_nombre_catalogo(texto)
    if any(
        s.categoria_id == categoria_id and normalizar_nombre_catalogo(s.nombre) == clave
        for s in data.subcategorias
    ):
        return ResultadoOperacion(
            False,
            "Ya existe una subcategoría con ese nombre en esta categoría.",
        )
    nuevo = Subcategoria(
        next_id("sub", [s.id for s in data.subcategorias]),
        texto,
        categoria_id,
        True,
    )
    data.subcategorias.append(nuevo)
    _registrar_actividad(
        context,
        "Catálogo subcategoría",
        f"Alta: {texto} (categoría {cat.nombre})",
    )
    context.uow.commit(data)
    return ResultadoOperacion(True, f"Subcategoría «{texto}» creada.")


def renombrar_subcategoria(
    subcategoria_id: str,
    nombre: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    texto = _nombre_presentacion(nombre)
    if not texto:
        return ResultadoOperacion(False, "Indique un nombre de subcategoría.")
    context = _ctx(ctx)
    data = context.data()
    actual = next((s for s in data.subcategorias if s.id == subcategoria_id), None)
    if not actual:
        return ResultadoOperacion(False, "Subcategoría no encontrada.")
    clave = normalizar_nombre_catalogo(texto)
    if any(
        s.id != subcategoria_id
        and s.categoria_id == actual.categoria_id
        and normalizar_nombre_catalogo(s.nombre) == clave
        for s in data.subcategorias
    ):
        return ResultadoOperacion(
            False,
            "Ya existe una subcategoría con ese nombre en esta categoría.",
        )
    anterior = actual.nombre
    actual.nombre = texto
    _registrar_actividad(
        context, "Catálogo subcategoría", f"Renombrado: {anterior} → {texto}",
    )
    context.uow.commit(data)
    return ResultadoOperacion(True, f"Subcategoría actualizada a «{texto}».")


def desactivar_subcategoria(
    subcategoria_id: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    context = _ctx(ctx)
    data = context.data()
    actual = next((s for s in data.subcategorias if s.id == subcategoria_id), None)
    if not actual:
        return ResultadoOperacion(False, "Subcategoría no encontrada.")
    if not actual.activo:
        return ResultadoOperacion(False, "La subcategoría ya está inactiva.")
    actual.activo = False
    _registrar_actividad(context, "Catálogo subcategoría", f"Desactivada: {actual.nombre}")
    context.uow.commit(data)
    return ResultadoOperacion(True, f"Subcategoría «{actual.nombre}» desactivada.")


def reactivar_subcategoria(
    subcategoria_id: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    context = _ctx(ctx)
    data = context.data()
    actual = next((s for s in data.subcategorias if s.id == subcategoria_id), None)
    if not actual:
        return ResultadoOperacion(False, "Subcategoría no encontrada.")
    if actual.activo:
        return ResultadoOperacion(False, "La subcategoría ya está activa.")
    clave = normalizar_nombre_catalogo(actual.nombre)
    if any(
        s.id != subcategoria_id
        and s.categoria_id == actual.categoria_id
        and s.activo
        and normalizar_nombre_catalogo(s.nombre) == clave
        for s in data.subcategorias
    ):
        return ResultadoOperacion(
            False,
            "No se puede reactivar: ya hay una subcategoría activa con ese nombre "
            "en esta categoría.",
        )
    actual.activo = True
    _registrar_actividad(context, "Catálogo subcategoría", f"Reactivada: {actual.nombre}")
    context.uow.commit(data)
    return ResultadoOperacion(True, f"Subcategoría «{actual.nombre}» reactivada.")


# --- CRUD Ubicaciones (Fase 6B) ---

def crear_ubicacion(
    nombre: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    texto = _nombre_presentacion(nombre)
    if not texto:
        return ResultadoOperacion(False, "Indique un nombre de ubicación.")
    context = _ctx(ctx)
    data = context.data()
    clave = normalizar_nombre_catalogo(texto)
    if any(normalizar_nombre_catalogo(u.nombre) == clave for u in data.ubicaciones):
        return ResultadoOperacion(False, "Ya existe una ubicación con ese nombre.")
    nuevo = Ubicacion(
        next_id("ubi", [u.id for u in data.ubicaciones]),
        texto,
        True,
    )
    data.ubicaciones.append(nuevo)
    _registrar_actividad(context, "Catálogo ubicación", f"Alta: {texto}")
    context.uow.commit(data)
    return ResultadoOperacion(True, f"Ubicación «{texto}» creada.")


def renombrar_ubicacion(
    ubicacion_id: str,
    nombre: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    texto = _nombre_presentacion(nombre)
    if not texto:
        return ResultadoOperacion(False, "Indique un nombre de ubicación.")
    context = _ctx(ctx)
    data = context.data()
    actual = next((u for u in data.ubicaciones if u.id == ubicacion_id), None)
    if not actual:
        return ResultadoOperacion(False, "Ubicación no encontrada.")
    clave = normalizar_nombre_catalogo(texto)
    if any(
        u.id != ubicacion_id and normalizar_nombre_catalogo(u.nombre) == clave
        for u in data.ubicaciones
    ):
        return ResultadoOperacion(False, "Ya existe una ubicación con ese nombre.")
    anterior = actual.nombre
    actual.nombre = texto
    _registrar_actividad(
        context, "Catálogo ubicación", f"Renombrado: {anterior} → {texto}",
    )
    context.uow.commit(data)
    return ResultadoOperacion(True, f"Ubicación actualizada a «{texto}».")


def desactivar_ubicacion(
    ubicacion_id: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    context = _ctx(ctx)
    data = context.data()
    actual = next((u for u in data.ubicaciones if u.id == ubicacion_id), None)
    if not actual:
        return ResultadoOperacion(False, "Ubicación no encontrada.")
    if not actual.activo:
        return ResultadoOperacion(False, "La ubicación ya está inactiva.")
    actual.activo = False
    _registrar_actividad(context, "Catálogo ubicación", f"Desactivada: {actual.nombre}")
    context.uow.commit(data)
    return ResultadoOperacion(True, f"Ubicación «{actual.nombre}» desactivada.")


def reactivar_ubicacion(
    ubicacion_id: str,
    *,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    context = _ctx(ctx)
    data = context.data()
    actual = next((u for u in data.ubicaciones if u.id == ubicacion_id), None)
    if not actual:
        return ResultadoOperacion(False, "Ubicación no encontrada.")
    if actual.activo:
        return ResultadoOperacion(False, "La ubicación ya está activa.")
    clave = normalizar_nombre_catalogo(actual.nombre)
    if any(
        u.id != ubicacion_id and u.activo and normalizar_nombre_catalogo(u.nombre) == clave
        for u in data.ubicaciones
    ):
        return ResultadoOperacion(
            False,
            "No se puede reactivar: ya hay una ubicación activa con ese nombre.",
        )
    actual.activo = True
    _registrar_actividad(context, "Catálogo ubicación", f"Reactivada: {actual.nombre}")
    context.uow.commit(data)
    return ResultadoOperacion(True, f"Ubicación «{actual.nombre}» reactivada.")


# --- Diagnóstico (solo lectura) ---

def incidencias_catalogo(data: AppData) -> list[str]:
    """Incidencias de catálogo 6A/6B/6C; no corrige nada."""
    out: list[str] = []
    cat_ids = {c.id for c in data.categorias}
    dep_ids = {d.id for d in data.departamentos}
    sub_ids = {s.id for s in data.subcategorias}
    ubi_ids = {u.id for u in getattr(data, "ubicaciones", []) or []}

    out.extend(
        f"Departamento id duplicado: {i}"
        for i in _dupes([d.id for d in data.departamentos])
    )
    out.extend(
        f"Categoría id duplicado: {i}"
        for i in _dupes([c.id for c in data.categorias])
    )
    out.extend(
        f"Subcategoría id duplicado: {i}"
        for i in _dupes([s.id for s in data.subcategorias])
    )
    out.extend(
        f"Ubicación id duplicado: {i}"
        for i in _dupes([u.id for u in getattr(data, "ubicaciones", []) or []])
    )

    out.extend(_nombres_dup_global(
        [(d.id, d.nombre) for d in data.departamentos], "Departamento",
    ))
    out.extend(_nombres_dup_global(
        [(c.id, c.nombre) for c in data.categorias], "Categoría",
    ))
    out.extend(_nombres_dup_global(
        [(u.id, u.nombre) for u in getattr(data, "ubicaciones", []) or []],
        "Ubicación",
    ))
    # Subcategorías: unicidad por categoría
    por_cat: dict[str, list[tuple[str, str]]] = {}
    for s in data.subcategorias:
        por_cat.setdefault(s.categoria_id, []).append((s.id, s.nombre))
    for cid, pares in por_cat.items():
        claves: dict[str, list[str]] = {}
        for sid, nom in pares:
            k = normalizar_nombre_catalogo(nom)
            claves.setdefault(k, []).append(sid)
        for k, ids in claves.items():
            if k and len(ids) > 1:
                out.append(
                    f"Subcategoría nombre duplicado en categoría {cid}: «{k}» "
                    f"({', '.join(ids)})"
                )

    for s in data.subcategorias:
        if s.categoria_id not in cat_ids:
            out.append(
                f"Subcategoría {s.id} → categoría inexistente {s.categoria_id}"
            )

    for p in data.productos:
        if p.categoria_id and p.categoria_id not in cat_ids:
            out.append(
                f"Producto {p.id} ({p.nombre}) → categoría inexistente {p.categoria_id}"
            )
        if p.subcategoria_id and p.subcategoria_id not in sub_ids:
            out.append(
                f"Producto {p.id} ({p.nombre}) → subcategoría inexistente {p.subcategoria_id}"
            )
        elif p.subcategoria_id:
            sub = next(s for s in data.subcategorias if s.id == p.subcategoria_id)
            if p.categoria_id and sub.categoria_id != p.categoria_id:
                out.append(
                    f"Producto {p.id} ({p.nombre}) → subcategoría incompatible "
                    f"({p.subcategoria_id} pertenece a {sub.categoria_id}, "
                    f"producto tiene {p.categoria_id})"
                )
            elif not p.categoria_id:
                out.append(
                    f"Producto {p.id} ({p.nombre}) → subcategoría sin categoría en producto"
                )
        for did in p.departamento_ids:
            if did not in dep_ids:
                out.append(
                    f"Producto {p.id} ({p.nombre}) → departamento inexistente {did}"
                )
        if len(p.departamento_ids) != len(set(p.departamento_ids)):
            out.append(
                f"Producto {p.id} ({p.nombre}) → departamentos duplicados en lista"
            )
        ubi_prod = list(getattr(p, "ubicacion_ids", []) or [])
        for uid in ubi_prod:
            if uid not in ubi_ids:
                out.append(
                    f"Producto {p.id} ({p.nombre}) → ubicación inexistente {uid}"
                )
        if len(ubi_prod) != len(set(ubi_prod)):
            out.append(
                f"Producto {p.id} ({p.nombre}) → ubicaciones duplicadas en lista"
            )
        tipo = getattr(p, "tipo_articulo", None)
        if tipo is None or tipo == "":
            out.append(
                f"Advertencia compatibilidad: producto {p.id} ({p.nombre}) "
                "sin clasificar (tipo_articulo)"
            )
        elif not es_tipo_articulo_conocido(tipo):
            out.append(
                f"Producto {p.id} ({p.nombre}) → tipo_articulo desconocido «{tipo}»"
            )

    return out


def _dupes(ids: list[str]) -> list[str]:
    vistos: set[str] = set()
    d: set[str] = set()
    for i in ids:
        if i in vistos:
            d.add(i)
        else:
            vistos.add(i)
    return sorted(d)


def _nombres_dup_global(pares: list[tuple[str, str]], etiqueta: str) -> list[str]:
    claves: dict[str, list[str]] = {}
    for i, nom in pares:
        k = normalizar_nombre_catalogo(nom)
        if not k:
            continue
        claves.setdefault(k, []).append(i)
    return [
        f"{etiqueta} nombre duplicado: «{k}» ({', '.join(ids)})"
        for k, ids in sorted(claves.items())
        if len(ids) > 1
    ]
