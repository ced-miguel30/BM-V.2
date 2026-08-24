"""Paneles economato Flet — compras Noray (panel, albarán, factura, docs…)."""

from __future__ import annotations

from typing import Any

import flet as ft

from app.presentation.flet import theme as ui_theme
from app.presentation.flet import ui_components as ui
from app.presentation.flet.inventory_document_viewmodels import (
    MAESTRO_TABS,
    TIPOS_UBICACION,
    EconomatoPanelVM,
)
from app.presentation.flet.inventory_viewmodels import InventarioScreenVM

def build_economato_body(
    screen: InventarioScreenVM,
    callbacks: dict[str, Any],
) -> ft.Control:
    eco = screen.economato
    if eco is None:
        return ft.Text("Cargando economato…", color=ui_theme.MID_GRAY)
    espacio = screen.espacio_activo
    try:
        if espacio == "compras_panel":
            body = _panel(screen, eco, callbacks)
        elif espacio in ("compras_albaran", "compras_factura"):
            body = _recepcion(screen, eco, callbacks)
        elif espacio == "compras_documentos":
            body = _documentos(screen, eco, callbacks)
        elif espacio == "compras_pendientes":
            body = _pendientes(screen, eco, callbacks)
        elif espacio == "compras_conciliacion":
            body = _conciliacion(screen, eco, callbacks)
        elif espacio == "compras_proveedores":
            body = _maestros(screen, eco, callbacks)
        elif espacio == "compras_historial":
            body = _historial(screen, eco, callbacks)
        else:
            body = ft.Text("Espacio no soportado", color=ui_theme.MID_GRAY)
        return body
    except TypeError as exc:
        raise

def _section_title(text: str) -> ft.Control:
    return ft.Text(text, size=18, weight=ft.FontWeight.BOLD, color=ui_theme.NAVY)


def _panel(
    screen: InventarioScreenVM, eco: EconomatoPanelVM, cbs: dict[str, Any]
) -> ft.Control:
    goto = cbs.get("on_goto_espacio")

    def _kpi(label: str, value: int, espacio: str) -> ft.Control:
        return ft.Container(
            padding=16,
            bgcolor=ui_theme.SURFACE_CARD,
            border_radius=ui_theme.RADIUS_SM,
            border=ft.border.all(1, ui_theme.BORDER),
            content=ft.Column(
                spacing=4,
                controls=[
                    ft.Text(str(value), size=28, weight=ft.FontWeight.BOLD, color=ui_theme.TEAL),
                    ft.Text(label, size=13, color=ui_theme.MID_GRAY),
                ],
            ),
            on_click=(lambda _e, eid=espacio: goto(eid)) if goto else None,
        )

    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        controls=[
            _section_title("Panel de compras"),
            ft.Text(
                "Resumen operativo · pulse un KPI para ir al espacio",
                size=12,
                color=ui_theme.MID_GRAY,
            ),
            ft.Row(
                wrap=True,
                spacing=16,
                controls=[
                    _kpi("Borradores", eco.n_borradores, "compras_albaran"),
                    _kpi(
                        "Albaranes pendientes de facturar",
                        eco.n_albaranes_pendientes_facturar,
                        "compras_pendientes",
                    ),
                    _kpi("Documentos del mes", eco.n_docs_mes, "compras_documentos"),
                ],
            ),
        ],
    )


def _pendientes(
    screen: InventarioScreenVM, eco: EconomatoPanelVM, cbs: dict[str, Any]
) -> ft.Control:
    rows: list[ft.Control] = []
    if not eco.pendientes_filas:
        rows.append(ft.Text("Sin pendientes de facturar.", color=ui_theme.MID_GRAY))
    else:
        for p in eco.pendientes_filas:
            rows.append(
                ft.Container(
                    padding=8,
                    border=ft.border.only(bottom=ft.BorderSide(1, ui_theme.BORDER)),
                    content=ft.Row(
                        controls=[
                            ft.Text(p.albaran_etiqueta, width=160, weight=ft.FontWeight.W_600),
                            ft.Text(p.producto, expand=True),
                            ft.Text(f"Pend. {p.cantidad_pendiente}", width=100),
                        ]
                    ),
                )
            )
    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        controls=[
            _section_title("Pendientes de facturar"),
            ft.Text(
                "Líneas de albarán confirmado aún no conciliadas en factura.",
                size=12,
                color=ui_theme.MID_GRAY,
            ),
            ft.Column(controls=rows),
        ],
    )


def _conciliacion(
    screen: InventarioScreenVM, eco: EconomatoPanelVM, cbs: dict[str, Any]
) -> ft.Control:
    lista: list[ft.Control] = []
    for d in eco.documentos:
        if (d.tipo or "").lower() != "factura":
            continue
        lista.append(
            ft.ListTile(
                title=ft.Text(f"FACTURA · {d.referencia or d.id}"),
                subtitle=ft.Text(f"{d.proveedor} · {d.fecha} · {d.estado}"),
                on_click=lambda _e, did=d.id: cbs["on_sel_documento"](did),
            )
        )
    diffs: list[ft.Control] = []
    if eco.documento_detalle:
        diffs.append(
            ft.Text(
                f"Seleccionada: {eco.documento_detalle.referencia or eco.documento_detalle.id}",
                weight=ft.FontWeight.W_600,
            )
        )
    if not eco.diferencias_conciliacion:
        diffs.append(
            ft.Text(
                "Sin diferencias (seleccione una factura o no hay vínculos).",
                size=12,
                color=ui_theme.MID_GRAY,
            )
        )
    else:
        for dif in eco.diferencias_conciliacion:
            diffs.append(ft.Text(f"[{dif.tipo}] {dif.detalle}", size=13))
    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        controls=[
            _section_title("Conciliación albarán ↔ factura"),
            ft.Text(
                "Seleccione una factura para ver diferencias.",
                size=12,
                color=ui_theme.MID_GRAY,
            ),
            ft.Column(controls=lista or [ft.Text("Sin facturas.", color=ui_theme.MID_GRAY)]),
            _section_title("Diferencias"),
            ft.Column(controls=diffs),
        ],
    )

def _recepcion(
    screen: InventarioScreenVM, eco: EconomatoPanelVM, cbs: dict[str, Any]
) -> ft.Control:

    tipo_forzado = eco.compra_tipo or "albaran"
    titulo = "Nuevo albarán" if tipo_forzado == "albaran" else "Nueva factura"
    tipo_dd = ft.Dropdown(
        label="Tipo documento",
        value=tipo_forzado,
        options=[
            ft.dropdown.Option("albaran", "Albarán"),
            ft.dropdown.Option("factura", "Factura"),
        ],
        width=180,
        on_select=lambda e: cbs["on_compra_tipo"](e.control.value or "albaran"),
    )
    prov_dd = ft.Dropdown(
        label="Proveedor",
        value=eco.compra_proveedor_id or None,
        options=[
            ft.dropdown.Option(o.id, o.etiqueta) for o in eco.compra_proveedores
        ],
        width=280,
        on_select=lambda e: cbs["on_compra_cabecera"](
            proveedor_id=e.control.value or ""
        ),
    )
    ref_tf = ft.TextField(
        label="Nº albarán / factura",
        value=eco.compra_referencia,
        width=200,
        on_blur=lambda e: cbs["on_compra_cabecera"](referencia=e.control.value or ""),
    )
    dto_tf = ft.TextField(
        label="Dto cabecera €",
        value=eco.compra_descuento_cabecera,
        width=120,
        on_blur=lambda e: cbs["on_compra_cabecera"](
            descuento_cabecera=e.control.value or "0"
        ),
    )
    ubi_dd = ft.Dropdown(
        label="Ubicación entrada",
        value=eco.compra_ubicacion_entrada_id or None,
        options=[
            ft.dropdown.Option(o.id, o.etiqueta) for o in eco.compra_ubicaciones
        ],
        width=260,
        on_select=lambda e: cbs["on_compra_cabecera"](
            ubicacion_entrada_id=e.control.value or ""
        ),
    )
    notas_tf = ft.TextField(
        label="Observaciones",
        value=eco.compra_notas,
        expand=True,
        on_blur=lambda e: cbs["on_compra_cabecera"](notas=e.control.value or ""),
    )

    busq = ft.TextField(
        label="Buscar producto (código / nombre)",
        value=eco.compra_prod_busqueda,
        width=320,
        on_change=lambda e: cbs["on_compra_busqueda"](e.control.value or ""),
        on_submit=lambda e: cbs["on_add_linea_busqueda"](e.control.value or ""),
    )
    cant_tf = ft.TextField(label="Cant.", value="1", width=80)
    prec_tf = ft.TextField(label="Precio ud.", value="0", width=100)
    igic_tf = ft.TextField(
        label="IGIC %", value=eco.compra_impuestos_default, width=80
    )

    def _add(_e=None):
        texto = (busq.value or "").strip()
        if eco.compra_prod_sugerencias and len(eco.compra_prod_sugerencias) == 1:
            cbs["on_add_linea"](
                eco.compra_prod_sugerencias[0].id,
                cantidad=cant_tf.value or "1",
                precio_unitario=prec_tf.value or "0",
                igic_pct=igic_tf.value or "",
            )
        else:
            cbs["on_add_linea_busqueda"](
                texto,
                cantidad=cant_tf.value or "1",
                precio_unitario=prec_tf.value or "0",
            )

    sugerencias: list[ft.Control] = []
    if eco.compra_prod_busqueda.strip() and len(eco.compra_prod_busqueda.strip()) >= 2:
        if not eco.compra_prod_sugerencias:
            sugerencias.append(
                ft.Text("Sin coincidencias", size=12, color=ui_theme.MID_GRAY)
            )
        else:
            for p in eco.compra_prod_sugerencias:
                sugerencias.append(
                    ft.TextButton(
                        p.etiqueta,
                        on_click=lambda _e, pid=p.id: cbs["on_add_linea"](
                            pid,
                            cantidad=cant_tf.value or "1",
                            precio_unitario=prec_tf.value or "0",
                            igic_pct=igic_tf.value or "",
                        ),
                    )
                )

    on_update = cbs.get("on_update_linea")
    lineas_rows: list[ft.Control] = []
    for i, ln in enumerate(eco.compra_lineas):
        cant_ln = ft.TextField(value=ln.cantidad, width=70, dense=True, label="Cant.")
        prec_ln = ft.TextField(
            value=ln.precio_unitario, width=80, dense=True, label="P.ud"
        )
        dto_p_ln = ft.TextField(value=ln.dto_pct, width=60, dense=True, label="Dto%")
        dto_e_ln = ft.TextField(value=ln.dto_eur, width=60, dense=True, label="Dto€")
        igic_ln = ft.TextField(value=ln.igic_pct, width=60, dense=True, label="IGIC%")

        def _commit_ln(
            _e=None,
            idx=i,
            c=cant_ln,
            p=prec_ln,
            dp=dto_p_ln,
            de=dto_e_ln,
            ig=igic_ln,
            orig=ln,
        ):
            if on_update is None:
                return
            campos = {
                "cantidad": c.value or "0",
                "precio_unitario": p.value or "0",
                "dto_pct": dp.value or "0",
                "dto_eur": de.value or "0",
                "igic_pct": ig.value or "0",
            }
            if (
                campos["cantidad"] == orig.cantidad
                and campos["precio_unitario"] == orig.precio_unitario
                and campos["dto_pct"] == orig.dto_pct
                and campos["dto_eur"] == orig.dto_eur
                and campos["igic_pct"] == orig.igic_pct
            ):
                return
            on_update(idx, **campos)

        for tf in (cant_ln, prec_ln, dto_p_ln, dto_e_ln, igic_ln):
            tf.on_blur = _commit_ln
            tf.on_submit = _commit_ln

        lineas_rows.append(
            ft.Container(
                padding=8,
                border=ft.border.only(bottom=ft.BorderSide(1, ui_theme.BORDER)),
                content=ft.Row(
                    wrap=True,
                    spacing=8,
                    controls=[
                        ft.Text(ln.producto_nombre, width=160, weight=ft.FontWeight.W_600),
                        cant_ln,
                        ft.Text(ln.unidad, width=40, size=12),
                        prec_ln,
                        dto_p_ln,
                        dto_e_ln,
                        igic_ln,
                        ft.Text(f"= {ln.total_linea} €", width=90),
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE,
                            icon_color=ui_theme.ERROR,
                            on_click=lambda _e, idx=i: cbs["on_quitar_linea"](idx),
                        ),
                    ],
                ),
            )
        )

    totales = eco.compra_totales
    tot_panel = ft.Container(
        bgcolor=ui_theme.SURFACE_CARD,
        padding=12,
        border_radius=ui_theme.RADIUS_SM,
        content=ft.Row(
            spacing=24,
            controls=[
                ft.Text(
                    f"Base: {totales.base_imponible if totales else '0'} €",
                    weight=ft.FontWeight.W_600,
                ),
                ft.Text(
                    f"IGIC: {totales.impuesto_total if totales else '0'} €",
                ),
                ft.Text(
                    f"Total: {totales.total if totales else '0'} €",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=ui_theme.TEAL,
                ),
                ft.Text(
                    f"Doc: {eco.compra_documento_id or 'nuevo'}",
                    size=12,
                    color=ui_theme.MID_GRAY,
                ),
            ],
        ),
    )

    alb_panel: list[ft.Control] = []
    if eco.compra_tipo == "factura":
        alb_panel.append(_section_title("Conciliar albaranes"))
        if not eco.albaranes_conciliables:
            alb_panel.append(
                ft.Text(
                    "No hay albaranes pendientes para este proveedor.",
                    color=ui_theme.MID_GRAY,
                    size=12,
                )
            )
        else:
            for a in eco.albaranes_conciliables:
                alb_panel.append(
                    ft.Checkbox(
                        label=f"{a.etiqueta} · {a.total} €",
                        value=a.seleccionado,
                        on_change=lambda _e, aid=a.id: cbs["on_toggle_albaran"](aid),
                    )
                )
            alb_panel.append(
                ui.primary_button(
                    "Incorporar albaranes seleccionados",
                    lambda: cbs["on_incorporar_albaranes"](),
                    icon=ft.Icons.MERGE_TYPE,
                )
            )

    borradores: list[ft.Control] = [_section_title("Borradores guardados")]
    if not eco.compra_borradores:
        borradores.append(ft.Text("Ninguno", size=12, color=ui_theme.MID_GRAY))
    else:
        for d in eco.compra_borradores:
            borradores.append(
                ft.Row(
                    controls=[
                        ft.Text(
                            f"{d.tipo} {d.referencia or d.id} · {d.proveedor} · {d.total}",
                            expand=True,
                        ),
                        ft.TextButton(
                            "Cargar",
                            on_click=lambda _e, did=d.id: cbs["on_cargar_borrador"](did),
                        ),
                        ft.TextButton(
                            "Anular",
                            on_click=lambda _e, did=d.id: cbs["on_anular_borrador"](did),
                        ),
                    ]
                )
            )

    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        controls=[
            _section_title(titulo),
            ft.Text(
                "Cabecera + líneas editables · paridad 13.5",
                size=12,
                color=ui_theme.MID_GRAY,
            ),
            ft.Row(wrap=True, spacing=12, controls=[tipo_dd, prov_dd, ref_tf, dto_tf, ubi_dd]),
            notas_tf,
            ft.Row(
                wrap=True,
                spacing=8,
                controls=[
                    busq,
                    cant_tf,
                    prec_tf,
                    igic_tf,
                    ui.primary_button("Añadir línea", _add, icon=ft.Icons.ADD),
                ],
            ),
            ft.Row(wrap=True, controls=sugerencias),
            ft.Column(controls=lineas_rows or [ft.Text("Sin líneas", color=ui_theme.MID_GRAY)]),
            tot_panel,
            ft.Column(controls=alb_panel),
            ft.Row(
                spacing=12,
                controls=[
                    ui.primary_button(
                        "Guardar borrador",
                        lambda: cbs["on_guardar_borrador"](),
                        icon=ft.Icons.SAVE,
                    ),
                    ui.primary_button(
                        "Confirmar compra",
                        lambda: cbs["on_confirmar_compra"](),
                        icon=ft.Icons.CHECK_CIRCLE,
                    ),
                    ft.OutlinedButton(
                        "Limpiar",
                        on_click=lambda _e: cbs["on_limpiar_compra"](),
                    ),
                ],
            ),
            ft.Column(controls=borradores),
        ],
    )

def _documentos(
    screen: InventarioScreenVM, eco: EconomatoPanelVM, cbs: dict[str, Any]
) -> ft.Control:
    texto = ft.TextField(
        label="Buscar",
        value=eco.doc_filtro_texto,
        width=220,
        on_submit=lambda e: cbs["on_doc_filtros"](texto=e.control.value or ""),
    )
    tipo = ft.Dropdown(
        label="Tipo",
        value=eco.doc_filtro_tipo or "",
        options=[
            ft.dropdown.Option("", "Todos"),
            ft.dropdown.Option("albaran", "Albarán"),
            ft.dropdown.Option("factura", "Factura"),
            ft.dropdown.Option("rectificativa", "Rectificativa"),
        ],
        width=160,
        on_select=lambda e: cbs["on_doc_filtros"](tipo=e.control.value or ""),
    )
    estado = ft.Dropdown(
        label="Estado",
        value=eco.doc_filtro_estado or "",
        options=[
            ft.dropdown.Option("", "Todos"),
            ft.dropdown.Option("borrador", "Borrador"),
            ft.dropdown.Option("confirmado", "Confirmado"),
            ft.dropdown.Option("anulado", "Anulado"),
            ft.dropdown.Option("rectificado", "Rectificado"),
        ],
        width=160,
        on_select=lambda e: cbs["on_doc_filtros"](estado=e.control.value or ""),
    )

    lista: list[ft.Control] = []
    for d in eco.documentos:
        lista.append(
            ft.ListTile(
                title=ft.Text(f"{d.tipo.upper()} · {d.referencia or d.id}"),
                subtitle=ft.Text(
                    f"{d.proveedor} · {d.fecha} · {d.estado} · {d.total} € · {d.lineas} ln"
                ),
                on_click=lambda _e, did=d.id: cbs["on_sel_documento"](did),
            )
        )

    detalle_ctrls: list[ft.Control] = []
    det = eco.documento_detalle
    if det:
        detalle_ctrls.extend(
            [
                _section_title(f"Detalle {det.id}"),
                ft.Text(
                    f"{det.tipo} · {det.estado} · {det.proveedor} · ref {det.referencia}"
                ),
                ft.Text(
                    f"Base {det.base} · Impuesto {det.impuesto} · Total {det.total} €",
                    weight=ft.FontWeight.W_600,
                ),
            ]
        )
        for ln in det.lineas:
            detalle_ctrls.append(
                ft.Text(
                    f"· {ln.producto}: {ln.cantidad} × {ln.precio_unitario} "
                    f"= {ln.total} (IGIC {ln.igic})"
                    + (f" ← {ln.origen_albaran}" if ln.origen_albaran else "")
                )
            )
        motivo = ft.TextField(label="Motivo anulación / rectificativa", width=320)
        detalle_ctrls.append(
            ft.Row(
                controls=[
                    motivo,
                    ft.OutlinedButton(
                        "Anular confirmado",
                        on_click=lambda _e: cbs["on_anular_doc"](
                            det.id, motivo.value or ""
                        ),
                    ),
                    ft.OutlinedButton(
                        "Crear rectificativa",
                        on_click=lambda _e: cbs["on_rectificativa"](
                            det.id, motivo.value or "Rectificación"
                        ),
                    ),
                ]
            )
        )

    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        controls=[
            _section_title("Documentos"),
            ft.Row(
                wrap=True,
                spacing=8,
                controls=[
                    texto,
                    tipo,
                    estado,
                    ui.primary_button(
                        "Filtrar",
                        lambda: cbs["on_doc_filtros"](
                            texto=texto.value or "",
                            tipo=tipo.value or "",
                            estado=estado.value or "",
                        ),
                    ),
                ],
            ),
            ft.Column(controls=lista or [ft.Text("Sin documentos", color=ui_theme.MID_GRAY)]),
            ft.Column(controls=detalle_ctrls),
        ],
    )

def _maestros(
    screen: InventarioScreenVM, eco: EconomatoPanelVM, cbs: dict[str, Any]
) -> ft.Control:
    tabs = ft.Row(
        wrap=True,
        spacing=8,
        controls=[
            ft.FilledButton(
                t.capitalize(),
                bgcolor=ui_theme.TEAL if eco.maestro_tab == t else ui_theme.SURFACE_CARD,
                color=ui_theme.WHITE if eco.maestro_tab == t else ui_theme.NAVY,
                on_click=lambda _e, tab=t: cbs["on_maestro_tab"](tab),
            )
            for t in MAESTRO_TABS
        ],
    )
    body: ft.Control
    tab = eco.maestro_tab
    if tab == "departamentos":
        nombre = ft.TextField(label="Nuevo departamento", width=240)
        body = ft.Column(
            controls=[
                ft.Text(
                    "Departamento = centro de uso (no ubicación física).",
                    size=12,
                    color=ui_theme.MID_GRAY,
                ),
                ft.Row(
                    controls=[
                        nombre,
                        ui.primary_button(
                            "Crear",
                            lambda: cbs["on_crear_depto"](nombre.value or ""),
                        ),
                    ]
                ),
                *[
                    ft.Text(f"· {d.nombre} ({d.id})" + ("" if d.activo else " [inactivo]"))
                    for d in eco.departamentos
                ],
            ]
        )
    elif tab == "ubicaciones":
        nom = ft.TextField(label="Nombre", width=180)
        cod = ft.TextField(label="Código", width=100)
        tipo = ft.Dropdown(
            label="Tipo",
            value="economato",
            options=[ft.dropdown.Option(t, t) for t in TIPOS_UBICACION],
            width=140,
        )
        body = ft.Column(
            controls=[
                ft.Text(
                    "Ubicación = dónde está el stock (economato, cocina, bar…).",
                    size=12,
                    color=ui_theme.MID_GRAY,
                ),
                ft.Row(
                    controls=[
                        nom,
                        cod,
                        tipo,
                        ui.primary_button(
                            "Crear",
                            lambda: cbs["on_crear_ubicacion"](
                                nom.value or "",
                                cod.value or "",
                                tipo.value or "otro",
                            ),
                        ),
                    ]
                ),
                *[
                    ft.Row(
                        controls=[
                            ft.Text(
                                f"{u.codigo or '—'} · {u.nombre} [{u.tipo}]",
                                expand=True,
                            ),
                            ft.Dropdown(
                                value=u.tipo,
                                options=[
                                    ft.dropdown.Option(t, t) for t in TIPOS_UBICACION
                                ],
                                width=130,
                                on_select=lambda e, uid=u.id: cbs["on_tipo_ubicacion"](
                                    uid, e.control.value or "otro"
                                ),
                            ),
                        ]
                    )
                    for u in eco.ubicaciones_maestro
                ],
            ]
        )
    elif tab == "proveedores":
        nf = ft.TextField(label="Nombre fiscal", width=220)
        cd = ft.TextField(label="Código", width=100)
        nif = ft.TextField(label="NIF/CIF", width=120)
        body = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        nf,
                        cd,
                        nif,
                        ui.primary_button(
                            "Crear",
                            lambda: cbs["on_crear_proveedor"](
                                nf.value or "", cd.value or "", nif.value or ""
                            ),
                        ),
                    ]
                ),
                *[
                    ft.Text(
                        f"{p.codigo} · {p.nombre_fiscal} · {p.nif}"
                        + ("" if p.activo else " [inactivo]")
                    )
                    for p in eco.proveedores_maestro
                ],
            ]
        )
    elif tab == "impuestos":
        ni = ft.TextField(label="Nombre", width=160)
        pct = ft.TextField(label="% ", width=80, value="7")
        body = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ni,
                        pct,
                        ui.primary_button(
                            "Crear",
                            lambda: cbs["on_crear_impuesto"](
                                ni.value or "", pct.value or "0"
                            ),
                        ),
                    ]
                ),
                *[
                    ft.Row(
                        controls=[
                            ft.Text(f"{i.nombre}: {i.porcentaje}%", expand=True),
                            ft.TextButton(
                                "Desactivar",
                                on_click=lambda _e, iid=i.id: cbs["on_desactivar_impuesto"](
                                    iid
                                ),
                                visible=i.activo,
                            ),
                        ]
                    )
                    for i in eco.impuestos_maestro
                ],
            ]
        )
    else:  # vinculos
        prod = ft.Dropdown(
            label="Producto",
            options=[
                ft.dropdown.Option(o.id, o.etiqueta) for o in eco.productos_opciones
            ],
            width=260,
        )
        prov = ft.Dropdown(
            label="Proveedor",
            options=[
                ft.dropdown.Option(o.id, o.etiqueta) for o in eco.compra_proveedores
            ],
            width=220,
        )
        uc = ft.TextField(label="Ud compra", width=90)
        fac = ft.TextField(label="Factor", value="1", width=80)
        prec = ft.TextField(label="Último precio", width=100)
        body = ft.Column(
            controls=[
                ft.Row(
                    wrap=True,
                    controls=[
                        prod,
                        prov,
                        uc,
                        fac,
                        prec,
                        ui.primary_button(
                            "Vincular",
                            lambda: cbs["on_vincular"](
                                prod.value or "",
                                prov.value or "",
                                uc.value or "",
                                fac.value or "1",
                                prec.value or "",
                            ),
                        ),
                    ],
                ),
                *[
                    ft.Text(
                        f"{v.producto} ↔ {v.proveedor} · {v.unidad_compra} ×{v.factor}"
                        f" · {v.ultimo_precio} €"
                    )
                    for v in eco.vinculos_maestro
                    if v.activo
                ],
            ]
        )

    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        controls=[_section_title("Proveedores / maestros"), tabs, body],
    )

def _historial(
    screen: InventarioScreenVM, eco: EconomatoPanelVM, cbs: dict[str, Any]
) -> ft.Control:
    texto = ft.TextField(
        label="Buscar producto / tipo / ref",
        value=eco.hist_texto,
        width=260,
        on_submit=lambda e: cbs["on_hist_filtros"](texto=e.control.value or ""),
    )
    ubi = ft.Dropdown(
        label="Ubicación",
        value=eco.hist_ubicacion_id or None,
        options=[ft.dropdown.Option("", "Todas")]
        + [ft.dropdown.Option(o.id, o.etiqueta) for o in eco.compra_ubicaciones],
        width=220,
        on_select=lambda e: cbs["on_hist_filtros"](ubicacion_id=e.control.value or ""),
    )
    prov = ft.Dropdown(
        label="Proveedor (docs)",
        value=eco.hist_proveedor_id or None,
        options=[ft.dropdown.Option("", "Todos")]
        + [ft.dropdown.Option(o.id, o.etiqueta) for o in eco.compra_proveedores],
        width=220,
        on_select=lambda e: cbs["on_hist_filtros"](proveedor_id=e.control.value or ""),
    )
    rows = [
        ft.DataRow(
            cells=[
                ft.DataCell(ft.Text(e.fecha, size=11)),
                ft.DataCell(ft.Text(e.tipo, size=11)),
                ft.DataCell(ft.Text(e.producto, size=11)),
                ft.DataCell(ft.Text(e.ubicacion, size=11)),
                ft.DataCell(ft.Text(e.cantidad, size=11)),
                ft.DataCell(ft.Text(e.documento or e.detalle, size=11)),
            ]
        )
        for e in eco.historial
    ]
    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        controls=[
            _section_title("Historial unificado"),
            ft.Row(
                wrap=True,
                spacing=8,
                controls=[
                    texto,
                    ubi,
                    prov,
                    ui.primary_button(
                        "Filtrar",
                        lambda: cbs["on_hist_filtros"](
                            texto=texto.value or "",
                            ubicacion_id=ubi.value or "",
                            proveedor_id=prov.value or "",
                        ),
                    ),
                    ft.OutlinedButton(
                        "Exportar CSV",
                        on_click=lambda _e: cbs["on_export_hist"](),
                    ),
                ],
            ),
            ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("Fecha")),
                    ft.DataColumn(ft.Text("Tipo")),
                    ft.DataColumn(ft.Text("Producto")),
                    ft.DataColumn(ft.Text("Ubicación")),
                    ft.DataColumn(ft.Text("Cant.")),
                    ft.DataColumn(ft.Text("Doc / detalle")),
                ],
                rows=rows,
            )
            if rows
            else ft.Text("Sin eventos", color=ui_theme.MID_GRAY),
        ],
    )
