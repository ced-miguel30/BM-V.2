"""Vistas Flet — Terminal Inventario (Royal Marina / Admin kit)."""

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
    _ = narrow
    header = ft.Container(
        bgcolor=ui_theme.NAVY,
        padding=ft.Padding.symmetric(horizontal=20, vertical=14),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
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

    nav = ft.Container(
        bgcolor=ui_theme.SURFACE,
        padding=ft.Padding.symmetric(
            horizontal=ui_theme.SPACE_LG,
            vertical=ui_theme.SPACE_SM,
        ),
        content=ft.Row(
            wrap=True,
            spacing=ui_theme.SPACE_SM,
            controls=[
                ft.FilledButton(
                    e.etiqueta,
                    style=ft.ButtonStyle(
                        padding=16,
                        bgcolor=ui_theme.TEAL if e.activo else ui_theme.SURFACE_CARD,
                        color=ui_theme.WHITE if e.activo else ui_theme.NAVY,
                        shape=ft.RoundedRectangleBorder(radius=ui_theme.RADIUS_SM),
                        side=(
                            None
                            if e.activo
                            else ft.BorderSide(1, ui_theme.BORDER)
                        ),
                    ),
                    on_click=lambda _e, eid=e.id: on_espacio(eid),
                )
                for e in screen.espacios
            ],
        ),
    )

    feedback = ft.Container()
    if screen.feedback:
        feedback = ft.Container(
            padding=ft.Padding.symmetric(
                horizontal=ui_theme.SPACE_LG,
                vertical=ui_theme.SPACE_SM,
            ),
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
        spacing=0,
        controls=[
            header,
            nav,
            feedback,
            ft.Container(
                content=body,
                expand=True,
                bgcolor=ui_theme.SURFACE,
                padding=ui_theme.SPACE_LG,
            ),
        ],
    )


def _alertas_body(screen: InventarioScreenVM, on_estado) -> ft.Control:
    if not screen.alertas:
        return ft.Column(
            expand=True,
            spacing=ui_theme.SPACE_MD,
            controls=[
                ui.page_header(
                    "Alertas operativas",
                    "Stock, caducidad y avisos pendientes de revisión",
                ),
                ui.card_surface(
                    ui.empty_state(
                        "No hay alertas activas",
                        "Cuando haya avisos de stock o caducidad aparecerán aquí.",
                    ),
                ),
            ],
        )

    cards: list[ft.Control] = []
    for a in screen.alertas:
        estado_l = (a.estado or "").lower()
        if "resuel" in estado_l:
            tone = "ok"
        elif "ignor" in estado_l:
            tone = "neutral"
        elif "revis" in estado_l:
            tone = "info"
        else:
            tone = "warn"
        sev = (a.severidad or "").lower()
        if sev in ("cero", "vencido", "stock_cero"):
            tone = "danger"
        elif sev in ("stock_bajo", "proximo"):
            tone = "warn"

        cards.append(
            ui.card_surface(
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(
                            a.titulo,
                            weight=ft.FontWeight.BOLD,
                            size=16,
                            color=ui_theme.DARK_TEXT,
                            expand=True,
                        ),
                        ui.status_chip(a.estado or "activa", tone=tone),
                    ],
                ),
                ft.Text(
                    f"{a.tipo}" + (f" · {a.severidad}" if a.severidad else ""),
                    size=12,
                    color=ui_theme.MID_GRAY,
                ),
                ft.Text(a.mensaje, size=13, color=ui_theme.DARK_TEXT),
                ft.Row(
                    spacing=ui_theme.SPACE_SM,
                    wrap=True,
                    controls=[
                        ui.secondary_button(
                            "Revisada",
                            lambda i=a.id: on_estado(i, EstadoAlerta.REVISADA.value),
                            icon=ft.Icons.VISIBILITY_OUTLINED,
                        ),
                        ft.TextButton(
                            "Resuelta",
                            style=ft.ButtonStyle(color=ui_theme.SUCCESS),
                            on_click=lambda _e, i=a.id: on_estado(
                                i, EstadoAlerta.RESUELTA.value
                            ),
                        ),
                        ft.TextButton(
                            "Ignorar",
                            style=ft.ButtonStyle(color=ui_theme.MID_GRAY),
                            on_click=lambda _e, i=a.id: on_estado(
                                i, EstadoAlerta.IGNORADA.value
                            ),
                        ),
                    ],
                ),
            )
        )

    return ft.Column(
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=ui_theme.SPACE_MD,
        controls=[
            ui.page_header(
                "Alertas operativas",
                "Stock, caducidad y avisos pendientes de revisión",
                actions=[
                    ui.status_chip(f"{len(screen.alertas)} activas", tone="warn"),
                ],
            ),
            *cards,
        ],
    )


def _responsable_dropdown(
    screen: InventarioScreenVM,
    on_seleccionar: Callable[[str | None], None],
) -> ft.Control:
    if not screen.responsables_merma:
        return ui.alert_banner(
            "No hay responsables activos. Configúrelos en Administración.",
            severity="error",
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
    controls: list[ft.Control] = [
        ui.page_header(
            "Caducidad",
            "Lotes vencidos o próximos · envío a merma con responsable",
            actions=[
                ui.status_chip(
                    f"{len(screen.lotes_caducidad)} lotes",
                    tone="warn" if screen.lotes_caducidad else "neutral",
                ),
            ],
        ),
        ui.card_surface(
            _responsable_dropdown(screen, on_seleccionar_responsable),
            ui_theme.text_help(
                "El responsable debe elegirse antes de enviar a merma."
            ),
            title="Responsable de merma",
        ),
    ]

    if not screen.lotes_caducidad:
        controls.append(
            ui.card_surface(
                ui.empty_state(
                    "Sin lotes en vigilancia",
                    "No hay lotes próximos a caducar ni vencidos.",
                ),
            )
        )
        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=ui_theme.SPACE_MD,
            controls=controls,
        )

    lotes: list[ft.Control] = []
    for l in screen.lotes_caducidad:
        vencido = l.estado == "vencido"
        lotes.append(
            ft.Container(
                bgcolor=ui_theme.DANGER_BG if vencido else ui_theme.WARNING_BG,
                padding=ui_theme.SPACE_MD,
                border_radius=ui_theme.RADIUS_MD,
                border=ft.Border.all(
                    1, ui_theme.DANGER if vencido else ui_theme.WARNING
                ),
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            expand=True,
                            spacing=ui_theme.SPACE_XS,
                            tight=True,
                            controls=[
                                ui.status_chip(
                                    "VENCIDO" if vencido else "PRÓXIMO",
                                    tone="danger" if vencido else "warn",
                                ),
                                ft.Text(
                                    l.nombre_producto,
                                    size=16,
                                    weight=ft.FontWeight.BOLD,
                                    color=ui_theme.DARK_TEXT,
                                ),
                                ft.Text(
                                    f"Lote {l.lote_id} · {l.cantidad_restante:g} {l.unidad} · "
                                    f"caduca {l.fecha_expiracion} ({l.dias_restantes} d)",
                                    size=12,
                                    color=ui_theme.MID_GRAY,
                                ),
                            ],
                        ),
                        ui.primary_button(
                            "A merma",
                            lambda lid=l.lote_id, c=l.cantidad_restante: on_enviar(
                                lid, c
                            ),
                            icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                        ),
                    ],
                ),
            )
        )

    controls.append(ui.card_surface(*lotes, title="Lotes en vigilancia"))
    return ft.Column(
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=ui_theme.SPACE_MD,
        controls=controls,
    )


def _merma_body(
    screen,
    on_anadir,
    on_seleccionar_responsable,
    on_vaciar,
    on_confirmar,
) -> ft.Control:
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

    def _add() -> None:
        if not lote_dd.value:
            return
        try:
            cant = float(qty.value or "0")
        except ValueError:
            return
        on_anadir(lote_dd.value, cant, motivo.value or screen.motivos_merma[0])

    if screen.cesta_merma_vacia:
        cesta_content: list[ft.Control] = [
            ui.empty_state(
                "Cesta vacía",
                "Añada líneas desde Caducidad o con el selector de lote.",
            ),
        ]
    else:
        cesta_content = [
            ft.Container(
                bgcolor=ui_theme.LIGHT_GRAY,
                padding=ui_theme.SPACE_MD,
                border_radius=ui_theme.RADIUS_SM,
                border=ft.Border.all(1, ui_theme.BORDER),
                content=ft.Column(
                    spacing=2,
                    tight=True,
                    controls=[
                        ft.Text(
                            ln.nombre,
                            size=14,
                            weight=ft.FontWeight.W_600,
                            color=ui_theme.DARK_TEXT,
                        ),
                        ft.Text(
                            f"{ln.cantidad:g} {ln.unidad} · {ln.motivo} · "
                            f"{ln.servicio} · resp. {ln.responsable or '—'}",
                            size=12,
                            color=ui_theme.MID_GRAY,
                        ),
                    ],
                ),
            )
            for ln in screen.cesta_merma
        ]
        cesta_content.append(
            ft.Row(
                controls=[
                    ui.secondary_button(
                        "Vaciar",
                        on_vaciar,
                        icon=ft.Icons.CLEAR_ALL,
                    ),
                ]
            )
        )

    return ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=ui_theme.SPACE_MD,
        controls=[
            ui.page_header(
                "Registro de merma",
                "Cesta operativa · confirmación con responsable",
                actions=[
                    ui.status_chip(
                        "Vacía" if screen.cesta_merma_vacia else f"{len(screen.cesta_merma)} líneas",
                        tone="neutral" if screen.cesta_merma_vacia else "info",
                    ),
                ],
            ),
            ui.card_surface(
                ui_theme.text_help(
                    "Añada líneas desde Caducidad o use el selector de lote abajo."
                ),
                _responsable_dropdown(screen, on_seleccionar_responsable),
                ft.Row(controls=[lote_dd]),
                ft.Row(
                    controls=[
                        qty,
                        motivo,
                        ui.secondary_button(
                            "Añadir",
                            _add,
                            icon=ft.Icons.ADD,
                        ),
                    ]
                ),
                title="Añadir línea",
            ),
            ui.card_surface(
                *cesta_content,
                ui.primary_button(
                    "Confirmar merma",
                    on_confirmar,
                    icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                    disabled=screen.confirmando or screen.cesta_merma_vacia,
                ),
                title="Cesta merma",
            ),
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
        lista: ft.Control = ui.card_surface(
            ui.empty_state(
                "Sin saldos por ubicación",
                "Pruebe otra búsqueda o quite el filtro de ubicación.",
            ),
        )
    else:
        rows: list[ft.Control] = []
        for r in screen.stock_filas:
            badge = ""
            tone = "neutral"
            if r.es_historico_sin_ubicacion:
                badge = "Histórico sin ubicación"
                tone = "warn"
            elif r.cobertura and "parcial" in r.cobertura.lower():
                badge = "Cobertura parcial"
                tone = "info"
            rows.append(
                ft.Container(
                    bgcolor=ui_theme.LIGHT_GRAY,
                    padding=ui_theme.SPACE_MD,
                    border_radius=ui_theme.RADIUS_MD,
                    border=ft.Border.all(1, ui_theme.BORDER),
                    content=ft.Column(
                        spacing=ui_theme.SPACE_XS,
                        tight=True,
                        controls=[
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text(
                                        f"{r.producto_nombre} · lote {r.lote_id}",
                                        weight=ft.FontWeight.BOLD,
                                        size=14,
                                        color=ui_theme.DARK_TEXT,
                                        expand=True,
                                    ),
                                    *([ui.status_chip(badge, tone=tone)] if badge else []),
                                ],
                            ),
                            ft.Text(
                                f"{r.ubicacion_etiqueta}: {r.saldo:g} {r.unidad}",
                                size=13,
                                color=ui_theme.DARK_TEXT,
                            ),
                            ft.Text(r.cobertura, size=11, color=ui_theme.MID_GRAY),
                        ],
                    ),
                )
            )
        lista = ui.card_surface(
            ft.Column(
                scroll=ft.ScrollMode.AUTO,
                expand=True,
                spacing=ui_theme.SPACE_SM,
                controls=rows,
            ),
            title=f"Saldos ({len(screen.stock_filas)})",
        )

    return ft.Column(
        expand=True,
        spacing=ui_theme.SPACE_MD,
        controls=[
            ui.page_header(
                "Stock por ubicación",
                "Consulta de saldos · búsqueda parcial",
                actions=[
                    ui.status_chip(
                        f"{len(screen.stock_filas)} resultados",
                        tone="info" if screen.stock_filas else "neutral",
                    ),
                ],
            ),
            ui.card_surface(
                ft.Row(
                    controls=[
                        search,
                        ui.secondary_button(
                            "Buscar",
                            lambda: on_busqueda(search.value or ""),
                            icon=ft.Icons.SEARCH,
                        ),
                        filtro,
                    ]
                ),
                title="Filtros",
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

    preview_controls: list[ft.Control] = []
    if screen.traslado_preview:
        p = screen.traslado_preview
        preview_inner: list[ft.Control] = [
            ft.Text(
                f"{p.producto_nombre} · lote {p.lote_id}: {p.cantidad:g} {p.unidad}",
                size=14,
                color=ui_theme.DARK_TEXT,
            ),
            ft.Text(
                f"{p.ubicacion_origen_etiqueta} → {p.ubicacion_destino_etiqueta}",
                size=13,
                color=ui_theme.DARK_TEXT,
            ),
            ft.Text(
                f"Disponible origen: {p.disponible_origen:g} {p.unidad}",
                size=12,
                color=ui_theme.MID_GRAY,
            ),
        ]
        if p.advertencia:
            preview_inner.append(
                ui.alert_banner(p.advertencia, severity="warning")
            )
        preview_controls = [
            ui.card_surface(
                *preview_inner,
                ft.Row(
                    spacing=ui_theme.SPACE_SM,
                    controls=[
                        ui.primary_button(
                            "Confirmar traslado",
                            on_confirm,
                            icon=ft.Icons.CHECK,
                            disabled=screen.confirmando,
                        ),
                        ui.secondary_button(
                            "Cancelar",
                            on_cancel,
                            disabled=screen.confirmando,
                        ),
                    ],
                ),
                title="Resumen del traslado",
            ),
        ]

    if not screen.traslados_recientes:
        recientes_body: list[ft.Control] = [
            ui.empty_state(
                "Sin traslados registrados",
                "Los movimientos confirmados aparecerán aquí.",
            ),
        ]
    else:
        recientes_body = [
            ft.Text(
                f"{t.fecha} · {t.traslado_id} · {t.producto_nombre} "
                f"lote {t.lote_id}: {t.cantidad:g} {t.unidad} · "
                f"{t.origen_etiqueta} → {t.destino_etiqueta}",
                size=12,
                color=ui_theme.DARK_TEXT,
            )
            for t in screen.traslados_recientes
        ]

    def _do_preview() -> None:
        on_cantidad(qty.value or "")
        on_preview()

    form_extras: list[ft.Control] = []
    if not screen.traslado_productos:
        form_extras.append(
            ui.empty_state(
                "Nada que trasladar",
                "No hay lotes con saldo en ubicaciones de catálogo.",
            )
        )

    return ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=ui_theme.SPACE_MD,
        controls=[
            ui.page_header(
                "Traslado entre ubicaciones",
                "Mover stock de origen a destino con previsualización",
            ),
            ui.card_surface(
                *form_extras,
                prod_dd,
                lote_dd,
                ft.Row(controls=[origen_dd, destino_dd]),
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        qty,
                        ft.Text(disp_txt, size=13, color=ui_theme.MID_GRAY, expand=True),
                        ui.secondary_button(
                            "Previsualizar",
                            _do_preview,
                            icon=ft.Icons.PREVIEW_OUTLINED,
                            disabled=screen.confirmando,
                        ),
                    ],
                ),
                title="Datos del traslado",
            ),
            *preview_controls,
            ui.card_surface(*recientes_body, title="Traslados recientes"),
        ],
    )


def _efecto_txt(efecto: str) -> str:
    return {
        "sin_cambio": "Sin cambio",
        "entrada": "Entrada (ajuste)",
        "salida": "Salida (ajuste)",
    }.get(efecto, efecto)


def _efecto_tone(efecto: str) -> str:
    return {
        "sin_cambio": "neutral",
        "entrada": "ok",
        "salida": "warn",
    }.get(efecto, "info")


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

    if not screen.recuento_lineas:
        lineas_body: list[ft.Control] = [
            ui.empty_state(
                "Sin líneas",
                "Añada productos contados en la ubicación seleccionada.",
            ),
        ]
    else:
        lineas_body = []
        for ln in screen.recuento_lineas:
            lineas_body.append(
                ft.Container(
                    bgcolor=ui_theme.LIGHT_GRAY,
                    padding=ui_theme.SPACE_MD,
                    border_radius=ui_theme.RADIUS_SM,
                    border=ft.Border.all(1, ui_theme.BORDER),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Column(
                                expand=True,
                                spacing=2,
                                tight=True,
                                controls=[
                                    ft.Text(
                                        f"{ln.producto_nombre} · lote {ln.lote_id}",
                                        size=13,
                                        weight=ft.FontWeight.W_600,
                                        color=ui_theme.DARK_TEXT,
                                    ),
                                    ft.Text(
                                        f"esp. {ln.cantidad_esperada:g} · cont. "
                                        f"{ln.cantidad_contada:g} {ln.unidad} · "
                                        f"Δ {ln.diferencia:+g}",
                                        size=12,
                                        color=ui_theme.MID_GRAY,
                                    ),
                                ],
                            ),
                            ui.status_chip(
                                _efecto_txt(ln.efecto),
                                tone=_efecto_tone(ln.efecto),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_color=ui_theme.DANGER,
                                disabled=bloqueado,
                                on_click=lambda _e, lid=ln.lote_id: on_quitar(lid),
                            ),
                        ],
                    ),
                )
            )

    aviso: list[ft.Control] = []
    if screen.recuento_aviso_borrador:
        aviso.append(
            ui.alert_banner(screen.recuento_aviso_borrador, severity="warning")
        )
    if screen.recuento_pendiente_id:
        aviso.append(
            ft.Text(
                f"Borrador activo: {screen.recuento_pendiente_id}",
                size=12,
                weight=ft.FontWeight.BOLD,
                color=ui_theme.NAVY,
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
        filas: list[ft.Control] = [
            ft.Text(f"Ubicación: {p.ubicacion_etiqueta}", color=ui_theme.DARK_TEXT),
        ]
        for ln in p.lineas:
            filas.append(
                ft.Text(
                    f"{ln.producto_nombre} · lote {ln.lote_id} · {ln.unidad}: "
                    f"esperado {ln.cantidad_esperada:g} · contado {ln.cantidad_contada:g} "
                    f"· Δ {ln.diferencia:+g} · {_efecto_txt(ln.efecto)}",
                    size=12,
                    color=ui_theme.DARK_TEXT,
                )
            )
        filas.append(ui_theme.text_help(p.mensaje))
        preview_box = [ui.card_surface(*filas, title=titulo)]

    acciones: list[ft.Control] = [
        ui.secondary_button(
            "Previsualizar",
            on_preview,
            icon=ft.Icons.PREVIEW_OUTLINED,
            disabled=screen.confirmando or screen.recuento_requiere_confirmacion_borrador,
        ),
        ui.primary_button(
            "Confirmar",
            on_confirm,
            icon=ft.Icons.CHECK,
            disabled=screen.confirmando
            or (
                screen.recuento_preview is None
                and not screen.recuento_requiere_confirmacion_borrador
            ),
        ),
        ui.secondary_button(
            "Cancelar",
            on_cancel,
            disabled=screen.confirmando,
        ),
    ]
    if screen.recuento_pendiente_id:
        acciones.extend(
            [
                ft.OutlinedButton(
                    "Descartar borrador",
                    disabled=screen.confirmando,
                    style=ft.ButtonStyle(
                        color=ui_theme.DANGER,
                        shape=ft.RoundedRectangleBorder(radius=ui_theme.RADIUS_SM),
                    ),
                    on_click=lambda _e: on_descartar(),
                ),
                ft.TextButton(
                    "Abandonar dejando pendiente",
                    disabled=screen.confirmando,
                    style=ft.ButtonStyle(color=ui_theme.MID_GRAY),
                    on_click=lambda _e: on_abandonar(),
                ),
            ]
        )

    if not screen.recuentos_pendientes:
        pendientes_body: list[ft.Control] = [
            ui.empty_state(
                "Sin borradores pendientes",
                "Los recuentos guardados como borrador se listan aquí.",
            ),
        ]
    else:
        pendientes_body = []
        for b in screen.recuentos_pendientes:
            pendientes_body.append(
                ft.Row(
                    controls=[
                        ft.Text(
                            f"{b.fecha} · {b.recuento_id} · {b.ubicacion_etiqueta} · {b.resumen}",
                            size=12,
                            color=ui_theme.DARK_TEXT,
                            expand=True,
                        ),
                        ui.secondary_button(
                            "Cargar",
                            lambda rid=b.recuento_id: on_seleccionar_borrador(rid),
                            disabled=screen.confirmando,
                        ),
                    ]
                )
            )

    if not screen.recuentos_recientes:
        recientes_body: list[ft.Control] = [
            ui.empty_state(
                "Sin recuentos confirmados",
                "El historial reciente aparecerá tras confirmar.",
            ),
        ]
    else:
        recientes_body = [
            ft.Text(
                f"{r.fecha} · {r.recuento_id} · {r.ubicacion_etiqueta} · "
                f"{r.resumen} · {r.estado}",
                size=12,
                color=ui_theme.DARK_TEXT,
            )
            for r in screen.recuentos_recientes
        ]

    def _do_anadir() -> None:
        on_cantidad(qty.value or "")
        on_anadir()

    return ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=ui_theme.SPACE_MD,
        controls=[
            ui.page_header(
                "Recuento físico por ubicación",
                "Cuente, previsualice y confirme · borradores pendientes",
            ),
            ui.alert_banner(
                "Preview en memoria no crea borrador. Confirmar crea borrador y, "
                "si el esperado no cambió, confirma. No hay transacción conjunta "
                "crear+confirmar ni idempotencia entre procesos.",
                severity="info",
            ),
            *aviso,
            ui.card_surface(
                ubi_dd,
                prod_dd,
                lote_dd,
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        qty,
                        ft.Text(esp_txt, size=13, color=ui_theme.MID_GRAY, expand=True),
                        ui.secondary_button(
                            "Añadir línea",
                            _do_anadir,
                            icon=ft.Icons.ADD,
                            disabled=bloqueado,
                        ),
                    ],
                ),
                title="Captura de líneas",
            ),
            ui.card_surface(*lineas_body, title="Líneas del recuento"),
            ui.card_surface(
                ft.Row(wrap=True, spacing=ui_theme.SPACE_SM, controls=acciones),
                title="Acciones",
            ),
            *preview_box,
            ui.card_surface(*pendientes_body, title="Pendientes (borradores)"),
            ui.card_surface(*recientes_body, title="Recientes confirmados"),
        ],
    )


def _ajustes_body(screen, on_preview, on_confirm) -> ft.Control:
    if not screen.lotes_ajuste:
        return ft.Column(
            expand=True,
            spacing=ui_theme.SPACE_MD,
            controls=[
                ui.page_header(
                    "Ajuste de inventario",
                    "Corrección de cantidad resultante por lote",
                ),
                ui.card_surface(
                    ui.empty_state(
                        "No hay lotes ajustables",
                        "Cuando existan lotes con saldo podrán ajustarse aquí.",
                    ),
                ),
            ],
        )

    lote_dd = ft.Dropdown(
        label="Lote",
        options=[
            ft.DropdownOption(key=l.lote_id, text=l.etiqueta) for l in screen.lotes_ajuste
        ],
        expand=True,
    )
    qty = ft.TextField(label="Cantidad resultante", value="0", width=160)
    motivo = ft.Dropdown(
        label="Motivo",
        options=[ft.DropdownOption(key=m, text=m) for m in screen.motivos_ajuste],
        value=screen.motivos_ajuste[0] if screen.motivos_ajuste else None,
        expand=True,
    )

    def _prev() -> None:
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
            ui.card_surface(
                ft.Text(
                    f"{p.nombre}: {p.cantidad_antes:g} → {p.cantidad_despues:g} "
                    f"{p.unidad} (Δ {p.delta:g}) · {p.motivo}",
                    size=14,
                    color=ui_theme.DARK_TEXT,
                ),
                ui.primary_button(
                    "Confirmar ajuste",
                    on_confirm,
                    icon=ft.Icons.CHECK,
                    disabled=screen.confirmando,
                ),
                title="Resumen",
            ),
        ]

    return ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=ui_theme.SPACE_MD,
        controls=[
            ui.page_header(
                "Ajuste de inventario",
                "Corrección de cantidad resultante por lote",
            ),
            ui.card_surface(
                lote_dd,
                ft.Row(controls=[qty, motivo]),
                ui.secondary_button(
                    "Previsualizar",
                    _prev,
                    icon=ft.Icons.PREVIEW_OUTLINED,
                ),
                title="Datos del ajuste",
            ),
            *preview_box,
        ],
    )
