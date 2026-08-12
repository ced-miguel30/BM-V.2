"""Vista de registro de servicio (catálogo + cesta + confirmar)."""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.presentation.flet import theme as ui_theme
from app.presentation.flet import ui_components as ui
from app.presentation.flet.viewmodels import CatalogItemVM, TerminalScreenVM
from app.presentation.flet.views.menu_nav import header_action_row


def build_catalog_result_controls(
    screen: TerminalScreenVM,
    *,
    on_add_receta: Callable[[str], None],
    on_add_producto: Callable[..., None],
) -> list[ft.Control]:
    """Solo filas del catálogo (sin campo de búsqueda)."""
    if not screen.catalogo:
        vacio = (
            "Ningún resultado para la búsqueda."
            if (screen.busqueda or "").strip()
            else "No hay ítems para este servicio o filtro."
        )
        return [
            ui.empty_state(
                "Sin resultados",
                vacio + " Pruebe otra palabra (búsqueda parcial).",
            )
        ]
    return [
        _catalog_tile(item, on_add_receta, on_add_producto) for item in screen.catalogo
    ]


def build_registro_view(
    screen: TerminalScreenVM,
    *,
    on_select_servicio: Callable[[str], None],
    on_search: Callable[[str], None],
    on_add_receta: Callable[[str], None],
    on_add_producto: Callable[..., None],
    on_qty_receta: Callable[[str, float], None],
    on_qty_producto: Callable[[str, float], None],
    on_remove_receta: Callable[[str], None],
    on_remove_producto: Callable[[str], None],
    on_clear: Callable[[], None],
    on_confirm: Callable[[], None],
    on_huespedes: Callable[[int], None],
    on_logout: Callable[[], None],
    on_volver_menu: Callable[[], None] | None = None,
    on_iniciar_anulacion: Callable[[str], None] | None = None,
    on_set_motivo_anulacion: Callable[[str], None] | None = None,
    on_cancelar_anulacion: Callable[[], None] | None = None,
    on_confirmar_anulacion: Callable[[], None] | None = None,
    on_catalogo_tipo: Callable[[str], None] | None = None,
    narrow: bool = False,
    search_field: ft.TextField | None = None,
    catalog_results: ft.Column | None = None,
) -> tuple[ft.Control, ft.TextField, ft.Column]:
    """Construye la vista y expone controles estables de búsqueda/catálogo."""
    on_iniciar_anulacion = on_iniciar_anulacion or (lambda _rid: None)
    on_set_motivo_anulacion = on_set_motivo_anulacion or (lambda _m: None)
    on_cancelar_anulacion = on_cancelar_anulacion or (lambda: None)
    on_confirmar_anulacion = on_confirmar_anulacion or (lambda: None)
    on_catalogo_tipo = on_catalogo_tipo or (lambda _t: None)
    activo = next((s for s in screen.servicios if s.activo), None)
    etiqueta_activo = activo.etiqueta if activo else "—"
    n_cesta = 0 if screen.cesta is None or screen.cesta.vacia else len(screen.cesta.lineas)

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
                            ui_theme.APP_NAME,
                            color=ui_theme.GOLD_SOFT,
                            size=12,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Text(
                            "Terminal Restaurante",
                            color=ui_theme.WHITE,
                            size=20,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            f"{ui_theme.HOTEL_DEFAULT} · Servicio: {etiqueta_activo}",
                            color="#B8C4D6",
                            size=13,
                        ),
                    ],
                ),
                ft.Row(
                    spacing=ui_theme.SPACE_SM,
                    controls=[
                        ui.status_chip(etiqueta_activo, tone="info"),
                        ui.status_chip(f"{n_cesta} en cesta", tone="neutral"),
                        header_action_row(
                            on_logout=on_logout,
                            on_volver_menu=on_volver_menu,
                            light=True,
                        ),
                    ],
                ),
            ],
        ),
    )

    selector = ui.card_surface(
        ft.Row(
            wrap=True,
            spacing=ui_theme.SPACE_SM,
            controls=[
                ft.FilledButton(
                    s.etiqueta,
                    style=ft.ButtonStyle(
                        padding=ft.Padding.symmetric(horizontal=18, vertical=12),
                        bgcolor=ui_theme.TEAL if s.activo else ui_theme.LIGHT_GRAY,
                        color=ui_theme.WHITE if s.activo else ui_theme.NAVY,
                        shape=ft.RoundedRectangleBorder(radius=ui_theme.RADIUS_SM),
                    ),
                    on_click=lambda _e, sid=s.id: on_select_servicio(sid),
                )
                for s in screen.servicios
            ],
        ),
        title="Servicio",
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

    if search_field is None:
        search_field = ft.TextField(
            label="Buscar receta o producto",
            hint_text="Búsqueda parcial…",
            value=screen.busqueda,
            prefix_icon=ft.Icons.SEARCH,
            on_change=lambda e: on_search(e.control.value or ""),
            expand=True,
        )
    else:
        search_field.on_change = lambda e: on_search(e.control.value or "")

    tipo_activo = getattr(screen, "catalogo_tipo", None) or "recetas"
    tipo_chips = ft.Row(
        wrap=True,
        spacing=8,
        controls=[
            (
                ft.FilledButton(
                    lab,
                    style=ft.ButtonStyle(
                        padding=ft.Padding.symmetric(horizontal=16, vertical=12),
                    ),
                    on_click=lambda _e, t=tid: on_catalogo_tipo(t),
                )
                if tipo_activo == tid
                else ft.OutlinedButton(
                    lab,
                    style=ft.ButtonStyle(
                        padding=ft.Padding.symmetric(horizontal=16, vertical=12),
                    ),
                    on_click=lambda _e, t=tid: on_catalogo_tipo(t),
                )
            )
            for tid, lab in (
                ("recetas", "Recetas"),
                ("productos", "Extras / productos"),
                ("bebidas", "Bebidas"),
                ("todas", "Todas"),
            )
        ],
    )

    huespedes_row: list[ft.Control] = []
    if screen.requiere_huespedes:
        huespedes_row = [
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                bgcolor=ui_theme.INFO_BG,
                border_radius=ui_theme.RADIUS_SM,
                content=ft.Row(
                    spacing=ui_theme.SPACE_SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("Huéspedes", size=13, color=ui_theme.INFO, weight=ft.FontWeight.W_600),
                        ft.IconButton(
                            icon=ft.Icons.REMOVE,
                            icon_color=ui_theme.NAVY,
                            on_click=lambda _e: on_huespedes(max(1, screen.num_huespedes - 1)),
                        ),
                        ft.Text(
                            str(screen.num_huespedes),
                            size=20,
                            weight=ft.FontWeight.BOLD,
                            color=ui_theme.NAVY,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ADD,
                            icon_color=ui_theme.NAVY,
                            on_click=lambda _e: on_huespedes(screen.num_huespedes + 1),
                        ),
                    ],
                ),
            )
        ]

    result_controls = build_catalog_result_controls(
        screen, on_add_receta=on_add_receta, on_add_producto=on_add_producto
    )
    if catalog_results is None:
        catalog_results = ft.Column(
            spacing=ui_theme.SPACE_SM,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            controls=result_controls,
        )
    else:
        catalog_results.controls = result_controls

    catalog_col = ft.Column(
        spacing=ui_theme.SPACE_SM,
        expand=True,
        controls=[
            ui.section_header(
                "Catálogo",
                f"{len(screen.catalogo)} ítems · Recetas del Excel · Productos/extras por cantidad",
            ),
            tipo_chips,
            search_field,
            *huespedes_row,
            ft.Container(content=catalog_results, expand=True),
        ],
    )

    basket_inner: list[ft.Control] = []
    if screen.cesta is None or screen.cesta.vacia:
        basket_inner.append(
            ui.empty_state("Cesta vacía", "Añada recetas o productos del catálogo.")
        )
    else:
        for lin in screen.cesta.lineas:
            if lin.kind == "receta":
                basket_inner.append(
                    _basket_row(
                        lin.nombre,
                        f"{lin.cantidad:g} {lin.unidad}",
                        on_minus=lambda _e, gid=lin.line_id: on_qty_receta(gid, -1),
                        on_plus=lambda _e, gid=lin.line_id: on_qty_receta(gid, 1),
                        on_remove=lambda _e, gid=lin.line_id: on_remove_receta(gid),
                    )
                )
            else:
                basket_inner.append(
                    _basket_row(
                        lin.nombre,
                        f"{lin.cantidad:g} {lin.unidad}",
                        on_minus=lambda _e, lid=lin.line_id: on_qty_producto(lid, -1),
                        on_plus=lambda _e, lid=lin.line_id: on_qty_producto(lid, 1),
                        on_remove=lambda _e, lid=lin.line_id: on_remove_producto(lid),
                    )
                )
        extras = getattr(screen.cesta, "extras_sugeridos", ()) or ()
        if extras:
            basket_inner.append(
                ft.Text(
                    "Extras de la receta",
                    size=12,
                    weight=ft.FontWeight.W_600,
                    color=ui_theme.MID_GRAY,
                )
            )
            for ex in extras:
                label = f"+ {ex.nombre} ({ex.cantidad:g} {ex.unidad})".strip()
                basket_inner.append(
                    ft.OutlinedButton(
                        label,
                        on_click=lambda _e, pid=ex.producto_id, c=ex.cantidad: on_add_producto(
                            pid, c
                        ),
                    )
                )
        basket_inner.append(
            ft.TextButton(
                "Vaciar cesta",
                style=ft.ButtonStyle(color=ui_theme.DANGER),
                on_click=lambda _e: on_clear(),
            )
        )

    basket_inner.append(
        ui.primary_button(
            "Confirmar registro",
            on_confirm,
            icon=ft.Icons.CHECK_CIRCLE,
            disabled=screen.confirmando
            or screen.anulando
            or screen.cesta is None
            or screen.cesta.vacia,
        )
    )
    if screen.confirmando or screen.anulando:
        basket_inner.append(ft.ProgressRing(width=24, height=24, color=ui_theme.NAVY))

    basket_col = ft.Container(
        width=None if narrow else 360,
        content=ui.card_surface(
            *basket_inner,
            title=f"Cesta ({n_cesta})",
        ),
    )

    historial_box = _historial_section(
        screen,
        on_iniciar_anulacion=on_iniciar_anulacion,
        on_set_motivo_anulacion=on_set_motivo_anulacion,
        on_cancelar_anulacion=on_cancelar_anulacion,
        on_confirmar_anulacion=on_confirmar_anulacion,
    )

    # Área catálogo+cesta con altura usable y scroll interno del listado.
    if narrow:
        body = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=ui_theme.SPACE_MD,
            controls=[catalog_col, basket_col, historial_box],
        )
    else:
        body = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=ui_theme.SPACE_MD,
            controls=[
                ft.Container(
                    height=520,
                    content=ft.Row(
                        expand=True,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        spacing=ui_theme.SPACE_MD,
                        controls=[
                            ft.Container(content=catalog_col, expand=True),
                            basket_col,
                        ],
                    ),
                ),
                historial_box,
            ],
        )

    root = ft.Column(
        expand=True,
        spacing=0,
        controls=[
            header,
            feedback,
            ft.Container(
                expand=True,
                bgcolor=ui_theme.SURFACE,
                padding=ui_theme.SPACE_LG,
                content=ft.Column(
                    expand=True,
                    spacing=ui_theme.SPACE_MD,
                    controls=[selector, body],
                ),
            ),
        ],
    )
    return root, search_field, catalog_results


def _estado_label(estado: str) -> str:
    return {
        "activo": "Activo",
        "anulado": "Anulado",
        "no_anulable": "No anulable",
    }.get(estado, estado)


def _historial_section(
    screen: TerminalScreenVM,
    *,
    on_iniciar_anulacion: Callable[[str], None],
    on_set_motivo_anulacion: Callable[[str], None],
    on_cancelar_anulacion: Callable[[], None],
    on_confirmar_anulacion: Callable[[], None],
) -> ft.Control:
    bloqueado = screen.confirmando or screen.anulando
    controls: list[ft.Control] = []

    if screen.anulacion_pendiente:
        p = screen.anulacion_pendiente
        motivo_tf = ft.TextField(
            label="Motivo de anulación (obligatorio)",
            value=p.motivo,
            expand=True,
            disabled=bloqueado,
            on_blur=lambda e: on_set_motivo_anulacion(
                getattr(e.control, "value", "") or ""
            ),
        )
        controls.append(
            ft.Container(
                bgcolor=ui_theme.WARNING_BG,
                padding=ui_theme.SPACE_MD,
                border_radius=ui_theme.RADIUS_MD,
                border=ft.Border.all(1, ui_theme.WARNING),
                content=ft.Column(
                    spacing=ui_theme.SPACE_SM,
                    controls=[
                        ft.Text(
                            "Confirmar anulación",
                            weight=ft.FontWeight.BOLD,
                            color=ui_theme.WARNING,
                        ),
                        ft.Text(p.etiqueta_corta, size=13, color=ui_theme.DARK_TEXT),
                        ft.Text(p.resumen, size=12, color=ui_theme.MID_GRAY),
                        motivo_tf,
                        ft.Row(
                            controls=[
                                ft.FilledButton(
                                    "Confirmar anulación",
                                    disabled=bloqueado,
                                    style=ft.ButtonStyle(
                                        bgcolor=ui_theme.DANGER,
                                        color=ui_theme.WHITE,
                                    ),
                                    on_click=lambda _e: (
                                        on_set_motivo_anulacion(motivo_tf.value or ""),
                                        on_confirmar_anulacion(),
                                    )[-1],
                                ),
                                ft.TextButton(
                                    "Cancelar",
                                    disabled=bloqueado,
                                    on_click=lambda _e: on_cancelar_anulacion(),
                                ),
                            ]
                        ),
                    ],
                ),
            )
        )

    if not screen.historial:
        controls.append(
            ui.empty_state(
                "Sin registros recientes",
                "Los registros de este servicio aparecerán aquí.",
            )
        )
    else:
        for item in screen.historial:
            tone = (
                "ok"
                if item.estado == "activo"
                else ("neutral" if item.estado == "anulado" else "warn")
            )
            fila: list[ft.Control] = [
                ft.Column(
                    spacing=2,
                    expand=True,
                    tight=True,
                    controls=[
                        ft.Text(
                            item.etiqueta_corta,
                            weight=ft.FontWeight.W_600,
                            size=13,
                            color=ui_theme.DARK_TEXT,
                        ),
                        ft.Text(item.resumen, size=12, color=ui_theme.MID_GRAY),
                        ui.status_chip(
                            _estado_label(item.estado)
                            + (
                                f" — {item.motivo_bloqueo}"
                                if item.estado == "no_anulable" and item.motivo_bloqueo
                                else ""
                            ),
                            tone=tone,
                        ),
                    ],
                ),
            ]
            if item.puede_anular and item.estado == "activo":
                fila.append(
                    ft.TextButton(
                        "Anular",
                        disabled=bloqueado or screen.anulacion_pendiente is not None,
                        style=ft.ButtonStyle(color=ui_theme.DANGER),
                        on_click=lambda _e, rid=item.registro_id: on_iniciar_anulacion(
                            rid
                        ),
                    )
                )
            controls.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=8),
                    border=ft.Border(bottom=ft.BorderSide(1, ui_theme.BORDER)),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=fila,
                    ),
                )
            )

    return ui.card_surface(
        *controls,
        title="Historial reciente",
    )


def _catalog_tile(
    item: CatalogItemVM,
    on_add_receta: Callable[[str], None],
    on_add_producto: Callable[..., None],
) -> ft.Control:
    is_receta = item.tipo == "receta"
    if is_receta:
        badge = "Receta"
        tone = "info"
    elif item.es_bebida:
        badge = "Bebida"
        tone = "ok"
    else:
        badge = "Producto / extra"
        tone = "neutral"
    detail = item.categoria if is_receta else (
        f"Stock {item.stock_disponible:g} {item.unidad}".strip()
        if item.stock_disponible is not None
        else (item.unidad or "")
    )
    return ft.Container(
        bgcolor=ui_theme.SURFACE_CARD,
        padding=ft.Padding.symmetric(horizontal=16, vertical=14),
        border_radius=ui_theme.RADIUS_MD,
        border=ft.Border.all(1, ui_theme.BORDER),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
            controls=[
                ft.Column(
                    spacing=4,
                    expand=True,
                    tight=True,
                    controls=[
                        ui.status_chip(badge, tone=tone),
                        ft.Text(
                            item.nombre,
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=ui_theme.DARK_TEXT,
                        ),
                        ft.Text(
                            detail or ("1 ración al añadir" if is_receta else ""),
                            size=14,
                            color=ui_theme.MID_GRAY,
                        ),
                    ],
                ),
                ui.primary_button(
                    "Añadir",
                    (
                        (lambda rid=item.id: on_add_receta(rid))
                        if is_receta
                        else (lambda pid=item.id: on_add_producto(pid))
                    ),
                    icon=ft.Icons.ADD,
                ),
            ],
        ),
    )


def _basket_row(
    nombre: str,
    qty_label: str,
    *,
    on_minus,
    on_plus,
    on_remove,
) -> ft.Control:
    return ft.Container(
        padding=ft.Padding.symmetric(vertical=6),
        border=ft.Border(bottom=ft.BorderSide(1, ui_theme.BORDER)),
        content=ft.Column(
            spacing=2,
            tight=True,
            controls=[
                ft.Text(
                    nombre,
                    weight=ft.FontWeight.W_600,
                    size=13,
                    color=ui_theme.DARK_TEXT,
                ),
                ft.Row(
                    spacing=2,
                    controls=[
                        ft.IconButton(
                            icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                            icon_color=ui_theme.NAVY,
                            on_click=on_minus,
                        ),
                        ft.Text(qty_label, size=13, color=ui_theme.DARK_TEXT),
                        ft.IconButton(
                            icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                            icon_color=ui_theme.NAVY,
                            on_click=on_plus,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            icon_color=ui_theme.DANGER,
                            on_click=on_remove,
                        ),
                    ],
                ),
            ],
        ),
    )
