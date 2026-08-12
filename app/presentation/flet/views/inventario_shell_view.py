"""Vistas Flet — Terminal Inventario."""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.core.models import EstadoAlerta
from app.presentation.flet import theme as ui_theme
from app.presentation.flet import ui_components as ui
from app.presentation.flet.inventory_viewmodels import InventarioScreenVM
from app.presentation.flet.views.menu_nav import (
    build_volver_al_menu_button,
    header_action_row,
)


def build_login_inventario(
    *,
    on_enter: Callable[[], None],
    on_volver_menu: Callable[[], None] | None = None,
) -> ft.Control:
    extras: list[ft.Control] = [
        ui.primary_button(
            "Entrar al terminal",
            on_enter,
            icon=ft.Icons.INVENTORY_2,
        ),
    ]
    volver = build_volver_al_menu_button(on_volver_menu)
    if volver is not None:
        extras.append(volver)
    extras.append(
        ft.Text(
            "Alertas, caducidad, merma, stock, traslados y recuentos · sin costes",
            size=11,
            color=ui_theme.MID_GRAY,
            text_align=ft.TextAlign.CENTER,
        )
    )
    return ui.branded_page(
        ui.auth_card(
            *extras,
            titulo="Terminal Inventario",
            subtitulo="Control de stock y merma operativa",
        )
    )


def build_inventario_shell(
    screen: InventarioScreenVM,
    *,
    on_espacio: Callable[[str], None],
    on_logout: Callable[[], None],
    on_volver_menu: Callable[[], None] | None = None,
    on_alerta_estado: Callable[[str, str], None],
    on_caducidad_a_merma: Callable[[str, float], None],
    on_anadir_merma: Callable[[str, float, str], None],
    on_seleccionar_responsable: Callable[[str | None], None],
    on_vaciar_merma: Callable[[], None],
    on_confirmar_merma: Callable[[], None],
    on_preview_ajuste: Callable[[str, float, str], None],
    on_confirmar_ajuste: Callable[[], None],
    on_stock_busqueda: Callable[[str], None] | None = None,
    on_stock_filtro_ubicacion: Callable[[str | None], None] | None = None,
    on_traslado_producto: Callable[[str | None], None] | None = None,
    on_traslado_lote: Callable[[str | None], None] | None = None,
    on_traslado_origen: Callable[[str | None], None] | None = None,
    on_traslado_destino: Callable[[str | None], None] | None = None,
    on_traslado_cantidad: Callable[[str], None] | None = None,
    on_preview_traslado: Callable[[], None] | None = None,
    on_confirmar_traslado: Callable[[], None] | None = None,
    on_cancelar_traslado: Callable[[], None] | None = None,
    on_recuento_ubicacion: Callable[[str | None], None] | None = None,
    on_recuento_producto: Callable[[str | None], None] | None = None,
    on_recuento_lote: Callable[[str | None], None] | None = None,
    on_recuento_cantidad: Callable[[str], None] | None = None,
    on_anadir_linea_recuento: Callable[[], None] | None = None,
    on_quitar_linea_recuento: Callable[[str], None] | None = None,
    on_preview_recuento: Callable[[], None] | None = None,
    on_confirmar_recuento: Callable[[], None] | None = None,
    on_cancelar_recuento: Callable[[], None] | None = None,
    on_seleccionar_borrador: Callable[[str], None] | None = None,
    on_descartar_borrador: Callable[[], None] | None = None,
    on_abandonar_borrador: Callable[[], None] | None = None,
    narrow: bool = False,
) -> ft.Control:
    header = ft.Container(
        bgcolor=ui_theme.NAVY,
        padding=ft.Padding.symmetric(horizontal=20, vertical=14),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Column(
                    spacing=2,
                    tight=True,
                    controls=[
                        ft.Text(
                            ui_theme.HOTEL_DEFAULT,
                            color=ui_theme.GOLD_SOFT,
                            size=12,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Text(
                            "Terminal Inventario",
                            color=ui_theme.WHITE,
                            size=20,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            f"Identidad: {screen.session.actor_label}",
                            color="#B8C4D6",
                            size=13,
                        ),
                    ],
                ),
                header_action_row(
                    on_logout=on_logout,
                    on_volver_menu=on_volver_menu,
                    light=True,
                ),
            ],
        ),
    )

    nav = ft.Row(
        wrap=True,
        spacing=8,
        controls=[
            ft.FilledButton(
                e.etiqueta,
                style=ft.ButtonStyle(
                    padding=16,
                    bgcolor=ui_theme.TEAL if e.activo else None,
                    color=ui_theme.WHITE if e.activo else ui_theme.NAVY,
                ),
                on_click=lambda _e, eid=e.id: on_espacio(eid),
            )
            for e in screen.espacios
        ],
    )

    feedback = ft.Container()
    if screen.feedback:
        feedback = ft.Container(
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            bgcolor=ui_theme.SURFACE,
            content=ui.alert_banner(
                screen.feedback.mensaje,
                severity="success" if screen.feedback.ok else "error",
            ),
        )

    body: ft.Control
    if screen.espacio_activo == "alertas":
        body = _alertas_body(screen, on_alerta_estado)
    elif screen.espacio_activo == "caducidad":
        body = _caducidad_body(screen, on_caducidad_a_merma, on_seleccionar_responsable)
    elif screen.espacio_activo == "merma":
        body = _merma_body(
            screen,
            on_anadir_merma,
            on_seleccionar_responsable,
            on_vaciar_merma,
            on_confirmar_merma,
        )
    elif screen.espacio_activo == "stock":
        body = _stock_body(
            screen,
            on_busqueda=on_stock_busqueda or (lambda _t: None),
            on_filtro=on_stock_filtro_ubicacion or (lambda _u: None),
        )
    elif screen.espacio_activo == "traslados":
        body = _traslados_body(
            screen,
            on_producto=on_traslado_producto or (lambda _p: None),
            on_lote=on_traslado_lote or (lambda _l: None),
            on_origen=on_traslado_origen or (lambda _o: None),
            on_destino=on_traslado_destino or (lambda _d: None),
            on_cantidad=on_traslado_cantidad or (lambda _c: None),
            on_preview=on_preview_traslado or (lambda: None),
            on_confirm=on_confirmar_traslado or (lambda: None),
            on_cancel=on_cancelar_traslado or (lambda: None),
        )
    elif screen.espacio_activo == "recuentos":
        body = _recuentos_body(
            screen,
            on_ubicacion=on_recuento_ubicacion or (lambda _u: None),
            on_producto=on_recuento_producto or (lambda _p: None),
            on_lote=on_recuento_lote or (lambda _l: None),
            on_cantidad=on_recuento_cantidad or (lambda _c: None),
            on_anadir=on_anadir_linea_recuento or (lambda: None),
            on_quitar=on_quitar_linea_recuento or (lambda _lid: None),
            on_preview=on_preview_recuento or (lambda: None),
            on_confirm=on_confirmar_recuento or (lambda: None),
            on_cancel=on_cancelar_recuento or (lambda: None),
            on_seleccionar_borrador=on_seleccionar_borrador or (lambda _rid: None),
            on_descartar=on_descartar_borrador or (lambda: None),
            on_abandonar=on_abandonar_borrador or (lambda: None),
        )
    else:
        body = _ajustes_body(screen, on_preview_ajuste, on_confirmar_ajuste)

    return ft.Column(
        expand=True,
        spacing=12,
        controls=[
            header,
            nav,
            feedback,
            ft.Container(content=body, expand=True, padding=12),
        ],
    )


def _alertas_body(screen: InventarioScreenVM, on_estado) -> ft.Control:
    if not screen.alertas:
        return ft.Text("No hay alertas activas.", italic=True, color=ft.Colors.OUTLINE)
    rows: list[ft.Control] = []
    for a in screen.alertas:
        rows.append(
            ft.Container(
                bgcolor=ft.Colors.AMBER_50,
                padding=12,
                border_radius=8,
                content=ft.Column(
                    spacing=6,
                    controls=[
                        ft.Text(a.titulo, weight=ft.FontWeight.BOLD, size=16),
                        ft.Text(f"{a.tipo} · {a.estado}", size=12),
                        ft.Text(a.mensaje, size=13),
                        ft.Row(
                            controls=[
                                ft.FilledTonalButton(
                                    "Revisada",
                                    on_click=lambda _e, i=a.id: on_estado(
                                        i, EstadoAlerta.REVISADA.value
                                    ),
                                ),
                                ft.TextButton(
                                    "Resuelta",
                                    on_click=lambda _e, i=a.id: on_estado(
                                        i, EstadoAlerta.RESUELTA.value
                                    ),
                                ),
                                ft.TextButton(
                                    "Ignorar",
                                    on_click=lambda _e, i=a.id: on_estado(
                                        i, EstadoAlerta.IGNORADA.value
                                    ),
                                ),
                            ]
                        ),
                    ],
                ),
            )
        )
    return ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=8, controls=rows)


def _responsable_dropdown(
    screen: InventarioScreenVM,
    on_seleccionar: Callable[[str | None], None],
) -> ft.Control:
    if not screen.responsables_merma:
        return ft.Text(
            "No hay responsables activos. Configúrelos en Administración.",
            color=ft.Colors.RED_700,
            size=13,
        )
    return ft.Dropdown(
        label="Responsable",
        hint_text="Selecciona un responsable",
        value=screen.responsable_seleccionado,
        options=[
            ft.DropdownOption(key=r.id, text=r.etiqueta)
            for r in screen.responsables_merma
        ],
        on_select=lambda e: on_seleccionar(getattr(e.control, "value", None)),
        expand=True,
    )


def _caducidad_body(
    screen: InventarioScreenVM,
    on_enviar,
    on_seleccionar_responsable: Callable[[str | None], None],
) -> ft.Control:
    if not screen.lotes_caducidad:
        return ft.Column(
            spacing=8,
            controls=[
                _responsable_dropdown(screen, on_seleccionar_responsable),
                ft.Text(
                    "No hay lotes próximos a caducar ni vencidos.",
                    italic=True,
                    color=ft.Colors.OUTLINE,
                ),
            ],
        )
    rows: list[ft.Control] = [
        _responsable_dropdown(screen, on_seleccionar_responsable),
        ft.Text(
            "El responsable debe elegirse antes de enviar a merma.",
            size=12,
            color=ft.Colors.OUTLINE,
        ),
    ]
    for l in screen.lotes_caducidad:
        badge = "VENCIDO" if l.estado == "vencido" else "PRÓXIMO"
        rows.append(
            ft.Container(
                bgcolor=ft.Colors.RED_50 if l.estado == "vencido" else ft.Colors.ORANGE_50,
                padding=12,
                border_radius=8,
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Column(
                            expand=True,
                            spacing=2,
                            controls=[
                                ft.Text(badge, size=11, weight=ft.FontWeight.W_600),
                                ft.Text(l.nombre_producto, size=16, weight=ft.FontWeight.BOLD),
                                ft.Text(
                                    f"Lote {l.lote_id} · {l.cantidad_restante:g} {l.unidad} · "
                                    f"caduca {l.fecha_expiracion} ({l.dias_restantes} d)",
                                    size=12,
                                ),
                            ],
                        ),
                        ft.FilledButton(
                            "A merma",
                            height=48,
                            on_click=lambda _e, lid=l.lote_id, c=l.cantidad_restante: on_enviar(
                                lid, c
                            ),
                        ),
                    ],
                ),
            )
        )
    return ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=8, controls=rows)


def _merma_body(
    screen,
    on_anadir,
    on_seleccionar_responsable,
    on_vaciar,
    on_confirmar,
) -> ft.Control:
    add_hint = ft.Text(
        "Añada líneas desde Caducidad o use el selector de lote abajo.",
        size=12,
        color=ft.Colors.OUTLINE,
    )
    lote_dd = ft.Dropdown(
        label="Lote",
        options=[
            ft.DropdownOption(key=l.lote_id, text=l.etiqueta) for l in screen.lotes_ajuste
        ],
        expand=True,
    )
    qty = ft.TextField(label="Cantidad", value="1", width=120)
    motivo = ft.Dropdown(
        label="Motivo",
        options=[ft.DropdownOption(key=m, text=m) for m in screen.motivos_merma],
        value=screen.motivos_merma[0] if screen.motivos_merma else None,
        expand=True,
    )
    resp_dd = _responsable_dropdown(screen, on_seleccionar_responsable)

    def _add(_e):
        if not lote_dd.value:
            return
        try:
            cant = float(qty.value or "0")
        except ValueError:
            return
        on_anadir(lote_dd.value, cant, motivo.value or screen.motivos_merma[0])

    cesta_rows: list[ft.Control] = [ft.Text("Cesta merma", weight=ft.FontWeight.BOLD)]
    if screen.cesta_merma_vacia:
        cesta_rows.append(ft.Text("Cesta vacía.", color=ft.Colors.OUTLINE))
    else:
        for ln in screen.cesta_merma:
            cesta_rows.append(
                ft.Text(
                    f"{ln.nombre}: {ln.cantidad:g} {ln.unidad} · {ln.motivo} · "
                    f"{ln.servicio} · resp. {ln.responsable or '—'}",
                    size=13,
                )
            )
        cesta_rows.append(ft.TextButton("Vaciar", on_click=lambda _e: on_vaciar()))
    cesta_rows.append(
        ft.FilledButton(
            "Confirmar merma",
            disabled=screen.confirmando or screen.cesta_merma_vacia,
            bgcolor=ft.Colors.ORANGE_800,
            on_click=lambda _e: on_confirmar(),
        )
    )
    return ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=10,
        controls=[
            add_hint,
            resp_dd,
            ft.Row(controls=[lote_dd]),
            ft.Row(controls=[qty, motivo, ft.FilledTonalButton("Añadir", on_click=_add)]),
            ft.Divider(),
            *cesta_rows,
        ],
    )


def _stock_body(
    screen: InventarioScreenVM,
    *,
    on_busqueda: Callable[[str], None],
    on_filtro: Callable[[str | None], None],
) -> ft.Control:
    search = ft.TextField(
        label="Buscar producto o lote",
        value=screen.stock_busqueda,
        expand=True,
        on_submit=lambda e: on_busqueda(getattr(e.control, "value", "") or ""),
    )
    filtro = ft.Dropdown(
        label="Ubicación",
        value=screen.stock_filtro_ubicacion or "__todas__",
        options=[
            ft.DropdownOption(key=u.id, text=u.etiqueta) for u in screen.stock_ubicaciones
        ],
        on_select=lambda e: on_filtro(getattr(e.control, "value", None)),
        width=260,
    )
    if not screen.stock_filas:
        lista: ft.Control = ft.Text(
            "No hay saldos por ubicación para mostrar. "
            "Los lotes sin movimientos de ubicación aparecen solo sin filtro "
            "como cobertura «Sin movimientos».",
            italic=True,
            color=ft.Colors.OUTLINE,
        )
    else:
        rows: list[ft.Control] = []
        for r in screen.stock_filas:
            badge = ""
            if r.es_historico_sin_ubicacion:
                badge = " · histórico sin ubicación"
            elif r.cobertura and "parcial" in r.cobertura.lower():
                badge = " · cobertura parcial"
            rows.append(
                ft.Container(
                    bgcolor=ft.Colors.BLUE_GREY_50,
                    padding=10,
                    border_radius=8,
                    content=ft.Column(
                        spacing=2,
                        controls=[
                            ft.Text(
                                f"{r.producto_nombre} · lote {r.lote_id}",
                                weight=ft.FontWeight.BOLD,
                                size=14,
                            ),
                            ft.Text(
                                f"{r.ubicacion_etiqueta}: {r.saldo:g} {r.unidad}"
                                f"{badge}",
                                size=13,
                            ),
                            ft.Text(r.cobertura, size=11, color=ft.Colors.OUTLINE),
                        ],
                    ),
                )
            )
        lista = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=6, controls=rows)
    return ft.Column(
        expand=True,
        spacing=10,
        controls=[
            ft.Text("Stock por ubicación (solo lectura)", weight=ft.FontWeight.BOLD),
            ft.Row(
                controls=[
                    search,
                    ft.FilledTonalButton(
                        "Buscar",
                        on_click=lambda _e: on_busqueda(search.value or ""),
                    ),
                    filtro,
                ]
            ),
            lista,
        ],
    )


def _traslados_body(
    screen: InventarioScreenVM,
    *,
    on_producto: Callable[[str | None], None],
    on_lote: Callable[[str | None], None],
    on_origen: Callable[[str | None], None],
    on_destino: Callable[[str | None], None],
    on_cantidad: Callable[[str], None],
    on_preview: Callable[[], None],
    on_confirm: Callable[[], None],
    on_cancel: Callable[[], None],
) -> ft.Control:
    prod_dd = ft.Dropdown(
        label="Producto",
        value=screen.traslado_producto_id,
        options=[
            ft.DropdownOption(key=o.id, text=o.etiqueta) for o in screen.traslado_productos
        ],
        on_select=lambda e: on_producto(getattr(e.control, "value", None)),
        expand=True,
    )
    lote_dd = ft.Dropdown(
        label="Lote",
        value=screen.traslado_lote_id,
        options=[
            ft.DropdownOption(key=o.id, text=o.etiqueta) for o in screen.traslado_lotes
        ],
        on_select=lambda e: on_lote(getattr(e.control, "value", None)),
        expand=True,
        disabled=not screen.traslado_productos or not screen.traslado_producto_id,
    )
    origen_dd = ft.Dropdown(
        label="Origen",
        value=screen.traslado_origen_id,
        options=[
            ft.DropdownOption(key=o.id, text=o.etiqueta) for o in screen.traslado_origenes
        ],
        on_select=lambda e: on_origen(getattr(e.control, "value", None)),
        expand=True,
        disabled=not screen.traslado_lote_id,
    )
    destino_dd = ft.Dropdown(
        label="Destino",
        value=screen.traslado_destino_id,
        options=[
            ft.DropdownOption(key=o.id, text=o.etiqueta) for o in screen.traslado_destinos
        ],
        on_select=lambda e: on_destino(getattr(e.control, "value", None)),
        expand=True,
        disabled=not screen.traslado_origen_id,
    )
    qty = ft.TextField(
        label="Cantidad",
        value=screen.traslado_cantidad,
        width=140,
        on_blur=lambda e: on_cantidad(getattr(e.control, "value", "") or ""),
    )
    disp_txt = (
        f"Disponible en origen: {screen.traslado_disponible:g}"
        if screen.traslado_disponible is not None
        else "Disponible en origen: —"
    )
    preview_box: list[ft.Control] = []
    if screen.traslado_preview:
        p = screen.traslado_preview
        adv = [ft.Text(p.advertencia, color=ft.Colors.AMBER_900, size=12)] if p.advertencia else []
        preview_box = [
            ft.Container(
                bgcolor=ft.Colors.BLUE_50,
                padding=12,
                border_radius=8,
                content=ft.Column(
                    spacing=4,
                    controls=[
                        ft.Text("Resumen del traslado", weight=ft.FontWeight.BOLD),
                        ft.Text(
                            f"{p.producto_nombre} · lote {p.lote_id}: "
                            f"{p.cantidad:g} {p.unidad}"
                        ),
                        ft.Text(
                            f"{p.ubicacion_origen_etiqueta} → {p.ubicacion_destino_etiqueta}"
                        ),
                        ft.Text(
                            f"Disponible origen: {p.disponible_origen:g} {p.unidad}",
                            size=12,
                        ),
                        *adv,
                    ],
                ),
            ),
            ft.Row(
                controls=[
                    ft.FilledButton(
                        "Confirmar traslado",
                        disabled=screen.confirmando,
                        bgcolor=ft.Colors.ORANGE_800,
                        on_click=lambda _e: on_confirm(),
                    ),
                    ft.TextButton(
                        "Cancelar",
                        disabled=screen.confirmando,
                        on_click=lambda _e: on_cancel(),
                    ),
                ]
            ),
        ]
    recientes: list[ft.Control] = [
        ft.Text("Traslados recientes", weight=ft.FontWeight.BOLD, size=14)
    ]
    if not screen.traslados_recientes:
        recientes.append(
            ft.Text("Sin traslados registrados.", color=ft.Colors.OUTLINE, size=12)
        )
    else:
        for t in screen.traslados_recientes:
            recientes.append(
                ft.Text(
                    f"{t.fecha} · {t.traslado_id} · {t.producto_nombre} "
                    f"lote {t.lote_id}: {t.cantidad:g} {t.unidad} · "
                    f"{t.origen_etiqueta} → {t.destino_etiqueta}",
                    size=12,
                )
            )

    def _do_preview(_e) -> None:
        on_cantidad(qty.value or "")
        on_preview()

    empty_hint = ft.Container()
    if not screen.traslado_productos:
        empty_hint = ft.Text(
            "No hay lotes con saldo en ubicaciones de catálogo para trasladar.",
            color=ft.Colors.OUTLINE,
            italic=True,
        )

    return ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=10,
        controls=[
            ft.Text("Traslado entre ubicaciones", weight=ft.FontWeight.BOLD),
            empty_hint,
            prod_dd,
            lote_dd,
            ft.Row(controls=[origen_dd, destino_dd]),
            ft.Row(
                controls=[
                    qty,
                    ft.Text(disp_txt, size=13),
                    ft.FilledTonalButton(
                        "Previsualizar",
                        disabled=screen.confirmando,
                        on_click=_do_preview,
                    ),
                ]
            ),
            *preview_box,
            ft.Divider(),
            *recientes,
        ],
    )


def _efecto_txt(efecto: str) -> str:
    return {
        "sin_cambio": "Sin cambio",
        "entrada": "Entrada (ajuste)",
        "salida": "Salida (ajuste)",
    }.get(efecto, efecto)


def _recuentos_body(
    screen: InventarioScreenVM,
    *,
    on_ubicacion: Callable[[str | None], None],
    on_producto: Callable[[str | None], None],
    on_lote: Callable[[str | None], None],
    on_cantidad: Callable[[str], None],
    on_anadir: Callable[[], None],
    on_quitar: Callable[[str], None],
    on_preview: Callable[[], None],
    on_confirm: Callable[[], None],
    on_cancel: Callable[[], None],
    on_seleccionar_borrador: Callable[[str], None],
    on_descartar: Callable[[], None],
    on_abandonar: Callable[[], None],
) -> ft.Control:
    bloqueado = screen.confirmando or screen.recuento_requiere_confirmacion_borrador
    ubi_dd = ft.Dropdown(
        label="Ubicación",
        value=screen.recuento_ubicacion_id,
        options=[
            ft.DropdownOption(key=o.id, text=o.etiqueta)
            for o in screen.recuento_ubicaciones
        ],
        on_select=lambda e: on_ubicacion(getattr(e.control, "value", None)),
        expand=True,
        disabled=bloqueado,
    )
    prod_dd = ft.Dropdown(
        label="Producto",
        value=screen.recuento_producto_id,
        options=[
            ft.DropdownOption(key=o.id, text=o.etiqueta)
            for o in screen.recuento_productos
        ],
        on_select=lambda e: on_producto(getattr(e.control, "value", None)),
        expand=True,
        disabled=bloqueado or not screen.recuento_ubicacion_id,
    )
    lote_dd = ft.Dropdown(
        label="Lote",
        value=screen.recuento_lote_id,
        options=[
            ft.DropdownOption(key=o.id, text=o.etiqueta) for o in screen.recuento_lotes
        ],
        on_select=lambda e: on_lote(getattr(e.control, "value", None)),
        expand=True,
        disabled=bloqueado or not screen.recuento_producto_id,
    )
    qty = ft.TextField(
        label="Cantidad contada",
        value=screen.recuento_cantidad,
        width=160,
        disabled=bloqueado,
        on_blur=lambda e: on_cantidad(getattr(e.control, "value", "") or ""),
    )
    esp_txt = (
        f"Esperado: {screen.recuento_esperado:g} {screen.recuento_unidad}".strip()
        if screen.recuento_esperado is not None
        else "Esperado: —"
    )

    lineas_ctrls: list[ft.Control] = [
        ft.Text("Líneas del recuento", weight=ft.FontWeight.BOLD, size=14)
    ]
    if not screen.recuento_lineas:
        lineas_ctrls.append(
            ft.Text("Sin líneas.", color=ft.Colors.OUTLINE, size=12, italic=True)
        )
    else:
        for ln in screen.recuento_lineas:
            lineas_ctrls.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(
                            f"{ln.producto_nombre} · lote {ln.lote_id}: "
                            f"esp. {ln.cantidad_esperada:g} · cont. {ln.cantidad_contada:g} "
                            f"{ln.unidad} · Δ {ln.diferencia:+g} · {_efecto_txt(ln.efecto)}",
                            size=12,
                            expand=True,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            disabled=bloqueado,
                            on_click=lambda _e, lid=ln.lote_id: on_quitar(lid),
                        ),
                    ],
                )
            )

    aviso: list[ft.Control] = []
    if screen.recuento_aviso_borrador:
        aviso.append(
            ft.Container(
                bgcolor=ft.Colors.AMBER_50,
                padding=10,
                border_radius=8,
                content=ft.Text(screen.recuento_aviso_borrador, size=13),
            )
        )
    if screen.recuento_pendiente_id:
        aviso.append(
            ft.Text(
                f"Borrador activo: {screen.recuento_pendiente_id}",
                size=12,
                weight=ft.FontWeight.BOLD,
            )
        )

    preview_box: list[ft.Control] = []
    if screen.recuento_preview:
        p = screen.recuento_preview
        titulo = (
            "Preview en memoria (orientativo)"
            if p.en_memoria
            else "Preview autoritativo del borrador"
        )
        filas = [
            ft.Text(titulo, weight=ft.FontWeight.BOLD),
            ft.Text(f"Ubicación: {p.ubicacion_etiqueta}"),
        ]
        for ln in p.lineas:
            filas.append(
                ft.Text(
                    f"{ln.producto_nombre} · lote {ln.lote_id} · {ln.unidad}: "
                    f"esperado {ln.cantidad_esperada:g} · contado {ln.cantidad_contada:g} "
                    f"· Δ {ln.diferencia:+g} · {_efecto_txt(ln.efecto)}",
                    size=12,
                )
            )
        filas.append(ft.Text(p.mensaje, size=11, color=ft.Colors.ON_SURFACE_VARIANT))
        preview_box = [
            ft.Container(
                bgcolor=ft.Colors.BLUE_50,
                padding=12,
                border_radius=8,
                content=ft.Column(spacing=4, controls=filas),
            )
        ]

    acciones: list[ft.Control] = [
        ft.FilledTonalButton(
            "Previsualizar",
            disabled=screen.confirmando or screen.recuento_requiere_confirmacion_borrador,
            on_click=lambda _e: on_preview(),
        ),
        ft.FilledButton(
            "Confirmar",
            disabled=screen.confirmando
            or (
                screen.recuento_preview is None
                and not screen.recuento_requiere_confirmacion_borrador
            ),
            bgcolor=ft.Colors.ORANGE_800,
            on_click=lambda _e: on_confirm(),
        ),
        ft.TextButton(
            "Cancelar",
            disabled=screen.confirmando,
            on_click=lambda _e: on_cancel(),
        ),
    ]
    if screen.recuento_pendiente_id:
        acciones.extend(
            [
                ft.OutlinedButton(
                    "Descartar borrador",
                    disabled=screen.confirmando,
                    on_click=lambda _e: on_descartar(),
                ),
                ft.TextButton(
                    "Abandonar dejando pendiente",
                    disabled=screen.confirmando,
                    on_click=lambda _e: on_abandonar(),
                ),
            ]
        )

    pendientes: list[ft.Control] = [
        ft.Text("Pendientes (borradores)", weight=ft.FontWeight.BOLD, size=14)
    ]
    if not screen.recuentos_pendientes:
        pendientes.append(
            ft.Text("Sin borradores pendientes.", color=ft.Colors.OUTLINE, size=12)
        )
    else:
        for b in screen.recuentos_pendientes:
            pendientes.append(
                ft.Row(
                    controls=[
                        ft.Text(
                            f"{b.fecha} · {b.recuento_id} · {b.ubicacion_etiqueta} · {b.resumen}",
                            size=12,
                            expand=True,
                        ),
                        ft.TextButton(
                            "Cargar",
                            disabled=screen.confirmando,
                            on_click=lambda _e, rid=b.recuento_id: on_seleccionar_borrador(
                                rid
                            ),
                        ),
                    ]
                )
            )

    recientes: list[ft.Control] = [
        ft.Text("Recientes confirmados", weight=ft.FontWeight.BOLD, size=14)
    ]
    if not screen.recuentos_recientes:
        recientes.append(
            ft.Text("Sin recuentos confirmados.", color=ft.Colors.OUTLINE, size=12)
        )
    else:
        for r in screen.recuentos_recientes:
            recientes.append(
                ft.Text(
                    f"{r.fecha} · {r.recuento_id} · {r.ubicacion_etiqueta} · "
                    f"{r.resumen} · {r.estado}",
                    size=12,
                )
            )

    def _do_anadir(_e) -> None:
        on_cantidad(qty.value or "")
        on_anadir()

    return ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=10,
        controls=[
            ft.Text("Recuento físico por ubicación", weight=ft.FontWeight.BOLD),
            ft.Text(
                "Preview en memoria no crea borrador. Confirmar crea borrador y, "
                "si el esperado no cambió, confirma. No hay transacción conjunta "
                "crear+confirmar ni idempotencia entre procesos.",
                size=11,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            *aviso,
            ubi_dd,
            prod_dd,
            lote_dd,
            ft.Row(
                controls=[
                    qty,
                    ft.Text(esp_txt, size=13),
                    ft.FilledTonalButton(
                        "Añadir línea",
                        disabled=bloqueado,
                        on_click=_do_anadir,
                    ),
                ]
            ),
            *lineas_ctrls,
            ft.Row(wrap=True, controls=acciones),
            *preview_box,
            ft.Divider(),
            *pendientes,
            ft.Divider(),
            *recientes,
        ],
    )


def _ajustes_body(screen, on_preview, on_confirm) -> ft.Control:
    if not screen.lotes_ajuste:
        return ft.Text("No hay lotes ajustables.", color=ft.Colors.OUTLINE)
    lote_dd = ft.Dropdown(
        label="Lote",
        options=[ft.DropdownOption(key=l.lote_id, text=l.etiqueta) for l in screen.lotes_ajuste],
        expand=True,
    )
    qty = ft.TextField(label="Cantidad resultante", value="0", width=160)
    motivo = ft.Dropdown(
        label="Motivo",
        options=[ft.DropdownOption(key=m, text=m) for m in screen.motivos_ajuste],
        value=screen.motivos_ajuste[0] if screen.motivos_ajuste else None,
        expand=True,
    )

    def _prev(_e):
        if not lote_dd.value:
            return
        try:
            cant = float(qty.value or "0")
        except ValueError:
            return
        on_preview(lote_dd.value, cant, motivo.value or screen.motivos_ajuste[0])

    preview_box: list[ft.Control] = []
    if screen.ajuste_preview:
        p = screen.ajuste_preview
        preview_box = [
            ft.Container(
                bgcolor=ft.Colors.BLUE_50,
                padding=12,
                border_radius=8,
                content=ft.Column(
                    controls=[
                        ft.Text("Resumen", weight=ft.FontWeight.BOLD),
                        ft.Text(
                            f"{p.nombre}: {p.cantidad_antes:g} → {p.cantidad_despues:g} "
                            f"{p.unidad} (Δ {p.delta:g}) · {p.motivo}"
                        ),
                    ]
                ),
            ),
            ft.FilledButton(
                "Confirmar ajuste",
                disabled=screen.confirmando,
                bgcolor=ft.Colors.ORANGE_800,
                on_click=lambda _e: on_confirm(),
            ),
        ]
    return ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=10,
        controls=[
            lote_dd,
            ft.Row(controls=[qty, motivo]),
            ft.FilledTonalButton("Previsualizar", on_click=_prev),
            *preview_box,
        ],
    )
