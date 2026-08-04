"""Proveedores, impuestos y relación producto–proveedor (Fase 8).

Sin facturas. No reescribe ``marca_proveedor`` de lotes históricos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.core.application.context import AppContext
from app.core.application.id_generator import next_id
from app.core.models import (
    AppData,
    Impuesto,
    Proveedor,
    RelacionProductoProveedor,
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


def _norm(valor: str | None) -> str:
    if not valor:
        return ""
    return re.sub(r"\s+", " ", valor.strip()).lower()


def _presentacion(valor: str | None) -> str:
    return re.sub(r"\s+", " ", (valor or "").strip())


def parse_porcentaje(raw: str | float | Decimal | None) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        if isinstance(raw, Decimal):
            d = raw
        else:
            d = Decimal(str(raw).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return None
    if d < 0 or d > 100:
        return None
    return d.quantize(Decimal("0.0001"))


def etiqueta_proveedor(data: AppData, proveedor_id: str | None) -> str:
    if not proveedor_id:
        return "No configurado"
    p = next((x for x in getattr(data, "proveedores", []) or [] if x.id == proveedor_id), None)
    if p is None:
        return ETIQUETA_REF_NO_ENCONTRADA
    return p.nombre_comercial or p.nombre_fiscal


def snapshot_proveedor(prov: Proveedor) -> tuple[str, str | None]:
    """Nombre y NIF congelados para histórico."""
    nombre = prov.nombre_comercial or prov.nombre_fiscal
    return nombre, prov.nif_cif


# --- Proveedores ---

def listar_proveedores(
    ctx: AppContext | None = None, *, solo_activos: bool = False
) -> list[Proveedor]:
    data = _ctx(ctx).uow.get_data()
    items = list(getattr(data, "proveedores", []) or [])
    if solo_activos:
        items = [p for p in items if p.activo]
    return sorted(items, key=lambda p: _norm(p.nombre_fiscal))


def crear_proveedor(
    nombre_fiscal: str,
    *,
    codigo: str,
    nombre_comercial: str | None = None,
    nif_cif: str | None = None,
    direccion: str | None = None,
    contacto: str | None = None,
    telefono: str | None = None,
    email: str | None = None,
    condiciones_pago: str | None = None,
    observaciones: str | None = None,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    from app.core.services.money import normalizar_codigo_funcional

    c = _ctx(ctx)
    data = c.uow.get_data()
    if not hasattr(data, "proveedores") or data.proveedores is None:
        data.proveedores = []
    nombre = _presentacion(nombre_fiscal)
    if len(nombre) < 2:
        return ResultadoOperacion(False, "El nombre fiscal debe tener al menos 2 caracteres.")
    codigo_n = normalizar_codigo_funcional(codigo)
    if not codigo_n:
        return ResultadoOperacion(False, "El código es obligatorio en altas nuevas.")
    if any(
        normalizar_codigo_funcional(getattr(p, "codigo", None)) == codigo_n
        for p in data.proveedores
    ):
        return ResultadoOperacion(False, f"Ya existe un proveedor con código «{codigo_n}».")
    clave = _norm(nombre)
    if any(_norm(p.nombre_fiscal) == clave for p in data.proveedores):
        return ResultadoOperacion(False, f"Ya existe un proveedor «{nombre}».")
    nif = _presentacion(nif_cif) or None
    if nif and any(
        (p.nif_cif or "").strip().lower() == nif.lower() for p in data.proveedores
    ):
        return ResultadoOperacion(False, f"Ya existe un proveedor con NIF/CIF «{nif}».")

    obs = _presentacion(observaciones) or None
    prov = Proveedor(
        id=next_id("prv", [p.id for p in data.proveedores]),
        nombre_fiscal=nombre,
        nombre_comercial=_presentacion(nombre_comercial) or None,
        nif_cif=nif,
        direccion=_presentacion(direccion) or None,
        contacto=_presentacion(contacto) or None,
        telefono=_presentacion(telefono) or None,
        email=_presentacion(email) or None,
        condiciones_pago=_presentacion(condiciones_pago) or None,
        activo=True,
        observaciones=obs,
        codigo=codigo_n,
    )
    data.proveedores.append(prov)
    _registrar_actividad(c, "Crear proveedor", f"Proveedor «{nombre}» ({prov.id})")
    c.uow.commit(data)
    return ResultadoOperacion(True, f"Proveedor «{nombre}» creado.")


def editar_proveedor(
    proveedor_id: str,
    *,
    nombre_fiscal: str | None = None,
    nombre_comercial: str | None = None,
    nif_cif: str | None = None,
    direccion: str | None = None,
    contacto: str | None = None,
    telefono: str | None = None,
    email: str | None = None,
    condiciones_pago: str | None = None,
    observaciones: str | None = None,
    codigo: str | None = None,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    c = _ctx(ctx)
    data = c.uow.get_data()
    prov = next((p for p in data.proveedores if p.id == proveedor_id), None)
    if prov is None:
        return ResultadoOperacion(False, "Proveedor no encontrado.")
    if nombre_fiscal is not None:
        nombre = _presentacion(nombre_fiscal)
        if len(nombre) < 2:
            return ResultadoOperacion(False, "El nombre fiscal debe tener al menos 2 caracteres.")
        clave = _norm(nombre)
        if any(
            p.id != proveedor_id and _norm(p.nombre_fiscal) == clave
            for p in data.proveedores
        ):
            return ResultadoOperacion(False, f"Ya existe un proveedor «{nombre}».")
        prov.nombre_fiscal = nombre
    if nombre_comercial is not None:
        prov.nombre_comercial = _presentacion(nombre_comercial) or None
    if nif_cif is not None:
        nif = _presentacion(nif_cif) or None
        if nif and any(
            p.id != proveedor_id and (p.nif_cif or "").strip().lower() == nif.lower()
            for p in data.proveedores
        ):
            return ResultadoOperacion(False, f"Ya existe un proveedor con NIF/CIF «{nif}».")
        prov.nif_cif = nif
    if direccion is not None:
        prov.direccion = _presentacion(direccion) or None
    if contacto is not None:
        prov.contacto = _presentacion(contacto) or None
    if telefono is not None:
        prov.telefono = _presentacion(telefono) or None
    if email is not None:
        prov.email = _presentacion(email) or None
    if condiciones_pago is not None:
        prov.condiciones_pago = _presentacion(condiciones_pago) or None
    if observaciones is not None:
        prov.observaciones = _presentacion(observaciones) or None
    if codigo is not None:
        from app.core.services.money import normalizar_codigo_funcional

        codigo_n = normalizar_codigo_funcional(codigo)
        if not codigo_n:
            return ResultadoOperacion(False, "El código no puede quedar vacío.")
        if any(
            p.id != proveedor_id
            and normalizar_codigo_funcional(getattr(p, "codigo", None)) == codigo_n
            for p in data.proveedores
        ):
            return ResultadoOperacion(
                False, f"Ya existe un proveedor con código «{codigo_n}»."
            )
        prov.codigo = codigo_n
    # No reescribe marca_proveedor ni snapshots de relaciones existentes.
    _registrar_actividad(c, "Editar proveedor", f"Proveedor {proveedor_id} actualizado")
    c.uow.commit(data)
    return ResultadoOperacion(True, "Proveedor actualizado.")


def desactivar_proveedor(
    proveedor_id: str, *, ctx: AppContext | None = None
) -> ResultadoOperacion:
    c = _ctx(ctx)
    data = c.uow.get_data()
    prov = next((p for p in data.proveedores if p.id == proveedor_id), None)
    if prov is None:
        return ResultadoOperacion(False, "Proveedor no encontrado.")
    if not prov.activo:
        return ResultadoOperacion(False, "El proveedor ya está inactivo.")
    prov.activo = False
    _registrar_actividad(c, "Desactivar proveedor", f"Proveedor {proveedor_id}")
    c.uow.commit(data)
    return ResultadoOperacion(True, "Proveedor desactivado.")


def reactivar_proveedor(
    proveedor_id: str, *, ctx: AppContext | None = None
) -> ResultadoOperacion:
    c = _ctx(ctx)
    data = c.uow.get_data()
    prov = next((p for p in data.proveedores if p.id == proveedor_id), None)
    if prov is None:
        return ResultadoOperacion(False, "Proveedor no encontrado.")
    if prov.activo:
        return ResultadoOperacion(False, "El proveedor ya está activo.")
    prov.activo = True
    _registrar_actividad(c, "Reactivar proveedor", f"Proveedor {proveedor_id}")
    c.uow.commit(data)
    return ResultadoOperacion(True, "Proveedor reactivado.")


# --- Impuestos ---

def listar_impuestos(
    ctx: AppContext | None = None, *, solo_activos: bool = False
) -> list[Impuesto]:
    data = _ctx(ctx).uow.get_data()
    items = list(getattr(data, "impuestos", []) or [])
    if solo_activos:
        items = [i for i in items if i.activo]
    return sorted(items, key=lambda i: _norm(i.nombre))


def crear_impuesto(
    nombre: str,
    porcentaje: str | float | Decimal,
    *,
    vigencia_desde: date | None = None,
    vigencia_hasta: date | None = None,
    descripcion: str | None = None,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    c = _ctx(ctx)
    data = c.uow.get_data()
    if not hasattr(data, "impuestos") or data.impuestos is None:
        data.impuestos = []
    nom = _presentacion(nombre)
    if len(nom) < 2:
        return ResultadoOperacion(False, "El nombre del impuesto debe tener al menos 2 caracteres.")
    pct = parse_porcentaje(porcentaje)
    if pct is None:
        return ResultadoOperacion(False, "Porcentaje no válido (0–100).")
    if vigencia_desde and vigencia_hasta and vigencia_hasta < vigencia_desde:
        return ResultadoOperacion(False, "La vigencia hasta no puede ser anterior al desde.")
    if any(_norm(i.nombre) == _norm(nom) for i in data.impuestos):
        return ResultadoOperacion(False, f"Ya existe un impuesto «{nom}».")

    imp = Impuesto(
        id=next_id("imp", [i.id for i in data.impuestos]),
        nombre=nom,
        porcentaje=pct,
        vigencia_desde=vigencia_desde,
        vigencia_hasta=vigencia_hasta,
        activo=True,
        descripcion=_presentacion(descripcion) or None,
    )
    data.impuestos.append(imp)
    _registrar_actividad(
        c, "Crear impuesto", f"Impuesto «{nom}» {pct}% ({imp.id})"
    )
    c.uow.commit(data)
    return ResultadoOperacion(True, f"Impuesto «{nom}» creado.")


def editar_impuesto(
    impuesto_id: str,
    *,
    nombre: str | None = None,
    porcentaje: str | float | Decimal | None = None,
    vigencia_desde: date | None = ...,  # type: ignore[assignment]
    vigencia_hasta: date | None = ...,  # type: ignore[assignment]
    descripcion: str | None = None,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    """Editar metadatos. Cambiar % no reescribe snapshots de líneas futuras (aún no hay)."""
    c = _ctx(ctx)
    data = c.uow.get_data()
    imp = next((i for i in data.impuestos if i.id == impuesto_id), None)
    if imp is None:
        return ResultadoOperacion(False, "Impuesto no encontrado.")
    if nombre is not None:
        nom = _presentacion(nombre)
        if len(nom) < 2:
            return ResultadoOperacion(False, "Nombre demasiado corto.")
        if any(
            i.id != impuesto_id and _norm(i.nombre) == _norm(nom) for i in data.impuestos
        ):
            return ResultadoOperacion(False, f"Ya existe un impuesto «{nom}».")
        imp.nombre = nom
    if porcentaje is not None:
        pct = parse_porcentaje(porcentaje)
        if pct is None:
            return ResultadoOperacion(False, "Porcentaje no válido (0–100).")
        imp.porcentaje = pct
    if vigencia_desde is not ...:
        imp.vigencia_desde = vigencia_desde
    if vigencia_hasta is not ...:
        imp.vigencia_hasta = vigencia_hasta
    if (
        imp.vigencia_desde
        and imp.vigencia_hasta
        and imp.vigencia_hasta < imp.vigencia_desde
    ):
        return ResultadoOperacion(False, "Vigencia inconsistente.")
    if descripcion is not None:
        imp.descripcion = _presentacion(descripcion) or None
    _registrar_actividad(c, "Editar impuesto", f"Impuesto {impuesto_id}")
    c.uow.commit(data)
    return ResultadoOperacion(True, "Impuesto actualizado.")


def desactivar_impuesto(
    impuesto_id: str, *, ctx: AppContext | None = None
) -> ResultadoOperacion:
    c = _ctx(ctx)
    data = c.uow.get_data()
    imp = next((i for i in data.impuestos if i.id == impuesto_id), None)
    if imp is None:
        return ResultadoOperacion(False, "Impuesto no encontrado.")
    if not imp.activo:
        return ResultadoOperacion(False, "El impuesto ya está inactivo.")
    imp.activo = False
    _registrar_actividad(c, "Desactivar impuesto", f"Impuesto {impuesto_id}")
    c.uow.commit(data)
    return ResultadoOperacion(True, "Impuesto desactivado.")


def reactivar_impuesto(
    impuesto_id: str, *, ctx: AppContext | None = None
) -> ResultadoOperacion:
    c = _ctx(ctx)
    data = c.uow.get_data()
    imp = next((i for i in data.impuestos if i.id == impuesto_id), None)
    if imp is None:
        return ResultadoOperacion(False, "Impuesto no encontrado.")
    if imp.activo:
        return ResultadoOperacion(False, "El impuesto ya está activo.")
    imp.activo = True
    _registrar_actividad(c, "Reactivar impuesto", f"Impuesto {impuesto_id}")
    c.uow.commit(data)
    return ResultadoOperacion(True, "Impuesto reactivado.")


# --- Relación producto–proveedor ---

def listar_relaciones(
    ctx: AppContext | None = None,
    *,
    producto_id: str | None = None,
    proveedor_id: str | None = None,
    solo_activas: bool = False,
) -> list[RelacionProductoProveedor]:
    data = _ctx(ctx).uow.get_data()
    items = list(getattr(data, "relaciones_producto_proveedor", []) or [])
    if producto_id:
        items = [r for r in items if r.producto_id == producto_id]
    if proveedor_id:
        items = [r for r in items if r.proveedor_id == proveedor_id]
    if solo_activas:
        items = [r for r in items if r.activo]
    return items


def vincular_producto_proveedor(
    producto_id: str,
    proveedor_id: str,
    *,
    codigo_proveedor: str | None = None,
    preferente: bool = False,
    ctx: AppContext | None = None,
) -> ResultadoOperacion:
    c = _ctx(ctx)
    data = c.uow.get_data()
    if not hasattr(data, "relaciones_producto_proveedor") or data.relaciones_producto_proveedor is None:
        data.relaciones_producto_proveedor = []
    prod = next((p for p in data.productos if p.id == producto_id), None)
    if prod is None:
        return ResultadoOperacion(False, "Producto no encontrado.")
    prov = next((p for p in data.proveedores if p.id == proveedor_id), None)
    if prov is None:
        return ResultadoOperacion(False, "Proveedor no encontrado.")
    if any(
        r.producto_id == producto_id
        and r.proveedor_id == proveedor_id
        and r.activo
        for r in data.relaciones_producto_proveedor
    ):
        return ResultadoOperacion(False, "Ya existe un vínculo activo entre este producto y proveedor.")

    snap_nombre, snap_nif = snapshot_proveedor(prov)
    if preferente:
        for r in data.relaciones_producto_proveedor:
            if r.producto_id == producto_id and r.activo:
                r.preferente = False

    rel = RelacionProductoProveedor(
        id=next_id("ppv", [r.id for r in data.relaciones_producto_proveedor]),
        producto_id=producto_id,
        proveedor_id=proveedor_id,
        codigo_proveedor=_presentacion(codigo_proveedor) or None,
        preferente=preferente,
        proveedor_nombre_snapshot=snap_nombre,
        nif_cif_snapshot=snap_nif,
        activo=True,
    )
    data.relaciones_producto_proveedor.append(rel)
    _registrar_actividad(
        c,
        "Vincular producto-proveedor",
        f"{prod.nombre} ↔ {snap_nombre} ({rel.id})",
    )
    c.uow.commit(data)
    return ResultadoOperacion(True, f"Vínculo creado ({rel.id}).")


def desactivar_relacion(
    relacion_id: str, *, ctx: AppContext | None = None
) -> ResultadoOperacion:
    c = _ctx(ctx)
    data = c.uow.get_data()
    rel = next(
        (r for r in data.relaciones_producto_proveedor if r.id == relacion_id),
        None,
    )
    if rel is None:
        return ResultadoOperacion(False, "Relación no encontrada.")
    if not rel.activo:
        return ResultadoOperacion(False, "La relación ya está inactiva.")
    rel.activo = False
    _registrar_actividad(c, "Desactivar vínculo producto-proveedor", relacion_id)
    c.uow.commit(data)
    return ResultadoOperacion(True, "Vínculo desactivado.")


def marcar_preferente(
    relacion_id: str, *, ctx: AppContext | None = None
) -> ResultadoOperacion:
    c = _ctx(ctx)
    data = c.uow.get_data()
    rel = next(
        (r for r in data.relaciones_producto_proveedor if r.id == relacion_id),
        None,
    )
    if rel is None:
        return ResultadoOperacion(False, "Relación no encontrada.")
    if not rel.activo:
        return ResultadoOperacion(False, "Reactive el vínculo antes de marcarlo preferente.")
    for r in data.relaciones_producto_proveedor:
        if r.producto_id == rel.producto_id and r.activo:
            r.preferente = r.id == relacion_id
    _registrar_actividad(c, "Marcar proveedor preferente", relacion_id)
    c.uow.commit(data)
    return ResultadoOperacion(True, "Proveedor marcado como preferente.")
