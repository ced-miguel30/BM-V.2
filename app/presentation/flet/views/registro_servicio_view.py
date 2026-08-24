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
    # Dos columnas en pantallas anchas: evita filas ultra-anchas y «enanas».
    tiles = [
        ft.Container(
            col={"xs": 12, "md": 12, "lg": 6, "xl": 6},
            padding=ft.Padding.only(right=8, bottom=10),
            content=_catalog_tile(item, on_add_receta, on_add_producto),
        )
        for item in screen.catalogo
    ]
    return [ft.ResponsiveRow(columns=12, spacing=0, run_spacing=0, controls=tiles)]


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
    on_confirmar_revision_historial: Callable[[str], None] | None = None,
    on_catalogo_tipo: Callable[[str], None] | None = None,
    on_upload_documento: Callable[[], None] | None = None,
    on_cerrar_importacion_tpv: Callable[[], None] | None = None,
    narrow: bool = False,
    search_field: ft.TextField | None = None,
    catalog_results: ft.Column | None = None,
) -> tuple[ft.Control, ft.TextField, ft.Column]:
    """Construye la vista y expone controles estables de búsqueda/catálogo."""
    on_iniciar_anulacion = on_iniciar_anulacion or (lambda _rid: None)
    on_set_motivo_anulacion = on_set_motivo_anulacion or (lambda _m: None)
    on_cancelar_anulacion = on_cancelar_anulacion or (lambda: None)
    on_confirmar_anulacion = on_confirmar_anulacion or (lambda: None)
    on_confirmar_revision_historial = on_confirmar_revision_historial or (lambda _rid: None)
    on_catalogo_tipo = on_catalogo_tipo or (lambda _t: None)
    on_upload_documento = on_upload_documento or (lambda: None)
    on_cerrar_importacion_tpv = on_cerrar_importacion_tpv or (lambda: None)
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

    importacion_panel = _importacion_tpv_panel(
        screen,
        on_cerrar=on_cerrar_importacion_tpv,
        on_iniciar_anulacion=on_iniciar_anulacion,
    )

    if search_field is None:
        search_field = ft.TextField(
            label="Buscar receta o producto",
            hint_text="Escriba parte del nombre…",
            value=screen.busqueda,
            prefix_icon=ft.Icons.SEARCH,
            text_size=16,
            height=52,
            # Sin expand vertical: en Column robaba todo el hueco entre buscador y lista.
            on_change=lambda e: on_search(e.control.value or ""),
        )
    else:
        search_field.on_change = lambda e: on_search(e.control.value or "")
        search_field.text_size = 16
        search_field.expand = False
        search_field.height = 52

    tipo_activo = getattr(screen, "catalogo_tipo", None) or "recetas"
    tipo_chips = ft.Row(
        wrap=True,
        spacing=10,
        controls=[
            (
                ft.FilledButton(
                    lab,
                    height=44,
                    style=ft.ButtonStyle(
                        padding=ft.Padding.symmetric(horizontal=20, vertical=12),
                        text_style=ft.TextStyle(size=15, weight=ft.FontWeight.W_600),
                    ),
                    on_click=lambda _e, t=tid: on_catalogo_tipo(t),
                )
                if tipo_activo == tid
                else ft.OutlinedButton(
                    lab,
                    height=44,
                    style=ft.ButtonStyle(
                        padding=ft.Padding.symmetric(horizontal=20, vertical=12),
                        text_style=ft.TextStyle(size=15),
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
                padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                bgcolor=ui_theme.INFO_BG,
                border_radius=ui_theme.RADIUS_SM,
                content=ft.Row(
                    spacing=ui_theme.SPACE_SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            "Huéspedes",
                            size=16,
                            color=ui_theme.INFO,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.REMOVE,
                            icon_size=28,
                            icon_color=ui_theme.NAVY,
                            on_click=lambda _e: on_huespedes(
                                max(1, screen.num_huespedes - 1)
                            ),
                        ),
                        ft.Text(
                            str(screen.num_huespedes),
                            size=28,
                            weight=ft.FontWeight.BOLD,
                            color=ui_theme.NAVY,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ADD,
                            icon_size=28,
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
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            controls=result_controls,
        )
    else:
        catalog_results.controls = result_controls
        catalog_results.spacing = 0

    catalog_panel = ft.Container(
        expand=True,
        bgcolor=ui_theme.SURFACE_CARD,
        border=ft.Border.all(1, ui_theme.BORDER),
        border_radius=ui_theme.RADIUS_MD,
        padding=16,
        content=ft.Column(
            expand=True,
            spacing=12,
            controls=[
                ft.Text(
                    f"Catálogo · {len(screen.catalogo)} ítems",
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=ui_theme.NAVY,
                ),
                ft.Text(
                    (
                        "Extras habituales de desayuno · una porción al añadir · ajuste en cesta"
                        if (screen.servicio_activo == "desayuno" and tipo_activo == "productos")
                        else (
                            "Cafés, tés y Cola Cao · leche vegetal = Espresso + ración de leche"
                            if (
                                screen.servicio_activo == "desayuno"
                                and tipo_activo == "bebidas"
                            )
                            else "Recetas del Excel · extras/productos por cantidad · pulse Añadir"
                        )
                    ),
                    size=14,
                    color=ui_theme.MID_GRAY,
                ),
                tipo_chips,
                *huespedes_row,
                search_field,
                ft.Container(
                    expand=True,
                    bgcolor=ui_theme.SURFACE,
                    border_radius=ui_theme.RADIUS_SM,
                    padding=10,
                    content=catalog_results,
                ),
            ],
        ),
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
                    "Extras sugeridos",
                    size=14,
                    weight=ft.FontWeight.W_600,
                    color=ui_theme.MID_GRAY,
                )
            )
            for ex in extras:
                label = f"+ {ex.nombre} ({ex.cantidad:g} {ex.unidad})".strip()
                basket_inner.append(
                    ft.OutlinedButton(
                        label,
                        height=40,
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
        ft.FilledButton(
            "Confirmar registro",
            icon=ft.Icons.CHECK_CIRCLE,
            height=52,
            disabled=screen.confirmando
            or screen.anulando
            or screen.cesta is None
            or screen.cesta.vacia,
            style=ft.ButtonStyle(
                bgcolor=ui_theme.NAVY,
                color=ui_theme.WHITE,
                text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_600),
                shape=ft.RoundedRectangleBorder(radius=ui_theme.RADIUS_SM),
            ),
            on_click=lambda _e: on_confirm(),
        )
    )
    if screen.confirmando or screen.anulando:
        basket_inner.append(ft.ProgressRing(width=28, height=28, color=ui_theme.NAVY))

    basket_col = ft.Container(
        width=None if narrow else 380,
        expand=narrow,
        content=ft.Container(
            bgcolor=ui_theme.SURFACE_CARD,
            border=ft.Border.all(1, ui_theme.BORDER),
            border_radius=ui_theme.RADIUS_MD,
            padding=16,
            content=ft.Column(
                expand=True,
                spacing=10,
                scroll=ft.ScrollMode.AUTO if not narrow else None,
                controls=[
                    ft.Text(
                        f"Cesta ({n_cesta})",
                        size=20,
                        weight=ft.FontWeight.BOLD,
                        color=ui_theme.NAVY,
                    ),
                    *basket_inner,
                ],
            ),
        ),
    )

    historial_box = _historial_section(
        screen,
        on_iniciar_anulacion=on_iniciar_anulacion,
        on_set_motivo_anulacion=on_set_motivo_anulacion,
        on_cancelar_anulacion=on_cancelar_anulacion,
        on_confirmar_anulacion=on_confirmar_anulacion,
        on_confirmar_revision_historial=on_confirmar_revision_historial,
        items_extra=screen.importacion_tpv.historial if screen.importacion_tpv else (),
    )

    # Catálogo ocupa casi toda la altura; historial colapsado abajo.
    if narrow:
        body = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=ui_theme.SPACE_MD,
            controls=[catalog_panel, basket_col, historial_box],
        )
    else:
        body = ft.Column(
            expand=True,
            spacing=ui_theme.SPACE_MD,
            controls=[
                ft.Row(
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                    spacing=ui_theme.SPACE_MD,
                    controls=[
                        ft.Container(content=catalog_panel, expand=True),
                        basket_col,
                    ],
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
            importacion_panel,
            ft.Container(
                expand=True,
                bgcolor=ui_theme.SURFACE,
                padding=ft.Padding.symmetric(horizontal=16, vertical=12),
                content=ft.Column(
                    expand=True,
                    spacing=10,
                    controls=[
                        ft.Container(
                            content=ft.Row(
                                wrap=True,
                                spacing=8,
                                controls=[
                                    ft.FilledButton(
                                        s.etiqueta,
                                        height=42,
                                        style=ft.ButtonStyle(
                                            padding=ft.Padding.symmetric(
                                                horizontal=18, vertical=10
                                            ),
                                            bgcolor=(
                                                ui_theme.TEAL
                                                if s.activo
                                                else ui_theme.LIGHT_GRAY
                                            ),
                                            color=(
                                                ui_theme.WHITE
                                                if s.activo
                                                else ui_theme.NAVY
                                            ),
                                            text_style=ft.TextStyle(
                                                size=15, weight=ft.FontWeight.W_600
                                            ),
                                            shape=ft.RoundedRectangleBorder(
                                                radius=ui_theme.RADIUS_SM
                                            ),
                                        ),
                                        on_click=lambda _e, sid=s.id: on_select_servicio(
                                            sid
                                        ),
                                    )
                                    for s in screen.servicios
                                ]
                                + [
                                    ft.OutlinedButton(
                                        "Subir documento TPV",
                                        icon=ft.Icons.UPLOAD_FILE,
                                        height=42,
                                        disabled=screen.confirmando or screen.anulando,
                                        style=ft.ButtonStyle(
                                            padding=ft.Padding.symmetric(
                                                horizontal=14, vertical=10
                                            ),
                                            shape=ft.RoundedRectangleBorder(
                                                radius=ui_theme.RADIUS_SM
                                            ),
                                        ),
                                        on_click=lambda _e: on_upload_documento(),
                                    )
                                ],
                            ),
                        ),
                        body,
                    ],
                ),
            ),
        ],
    )
    return root, search_field, catalog_results


def _importacion_tpv_panel(
    screen: TerminalScreenVM,
    *,
    on_cerrar: Callable[[], None],
    on_iniciar_anulacion: Callable[[str], None],
) -> ft.Control:
    panel = screen.importacion_tpv
    if panel is None:
        return ft.Container()

    bloqueado = screen.confirmando or screen.anulando
    lineas = [ft.Text(ln, size=13, color=ui_theme.DARK_TEXT) for ln in panel.lineas]
    advertencias = [
        ft.Text(f"⚠ {adv}", size=12, color=ui_theme.WARNING) for adv in panel.advertencias
    ]
    historial_controls: list[ft.Control] = []
    if panel.historial:
        historial_controls.append(
            ft.Text(
                "Registros creados — anule los incorrectos y vuelva a subir o registre manualmente:",
                size=12,
                color=ui_theme.MID_GRAY,
            )
        )
        for item in panel.historial:
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
                        ),
                        ft.Text(item.resumen, size=12, color=ui_theme.MID_GRAY),
                    ],
                )
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
            historial_controls.append(
                ft.Container(
                    padding=ft.Padding.symmetric(vertical=6),
                    border=ft.Border(bottom=ft.BorderSide(1, ui_theme.BORDER)),
                    content=ft.Row(controls=fila),
                )
            )

    bgcolor = ui_theme.SUCCESS_BG if panel.ok else ui_theme.WARNING_BG
    border = ui_theme.SUCCESS if panel.ok else ui_theme.WARNING
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=16, vertical=10),
        bgcolor=ui_theme.SURFACE,
        content=ft.Container(
            bgcolor=bgcolor,
            padding=16,
            border_radius=ui_theme.RADIUS_MD,
            border=ft.Border.all(1, border),
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(
                                panel.titulo,
                                size=17,
                                weight=ft.FontWeight.BOLD,
                                color=ui_theme.NAVY,
                            ),
                            ft.TextButton("Cerrar", on_click=lambda _e: on_cerrar()),
                        ],
                    ),
                    *lineas,
                    *advertencias,
                    *historial_controls,
                    ft.Text(
                        "También puede revisar el historial del servicio (Comida / Bebidas) abajo.",
                        size=12,
                        color=ui_theme.MID_GRAY,
                    ),
                ],
            ),
        ),
    )


def _estado_label(estado: str) -> str:
    return {
        "activo": "Activo",
        "anulado": "Anulado",
        "no_anulable": "No anulable",
        "confirmado": "Confirmado",
    }.get(estado, estado)


def _historial_section(
    screen: TerminalScreenVM,
    *,
    on_iniciar_anulacion: Callable[[str], None],
    on_set_motivo_anulacion: Callable[[str], None],
    on_cancelar_anulacion: Callable[[], None],
    on_confirmar_anulacion: Callable[[], None],
    on_confirmar_revision_historial: Callable[[str], None],
    items_extra: tuple = (),
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

    historial_items = list(items_extra) + [
        item
        for item in screen.historial
        if not items_extra
        or item.registro_id not in {x.registro_id for x in items_extra}
    ]

    if not historial_items:
        controls.append(
            ui.empty_state(
                "Sin registros recientes",
                "Los registros de este servicio aparecerán aquí.",
            )
        )
    else:
        for item in historial_items:
            tone = (
                "ok"
                if item.estado == "activo"
                else (
                    "neutral"
                    if item.estado in ("anulado", "confirmado")
                    else "warn"
                )
            )
            tile = ft.Container(
                border=ft.Border(bottom=ft.BorderSide(1, ui_theme.BORDER)),
                content=ft.ExpansionTile(
                    title=ft.Text(
                        item.etiqueta_corta,
                        weight=ft.FontWeight.W_600,
                        size=13,
                        color=ui_theme.DARK_TEXT,
                    ),
                    subtitle=ft.Text(item.resumen, size=12, color=ui_theme.MID_GRAY),
                    trailing=ui.status_chip(
                        _estado_label(item.estado)
                        + (
                            f" — {item.motivo_bloqueo}"
                            if item.estado == "no_anulable" and item.motivo_bloqueo
                            else ""
                        ),
                        tone=tone,
                    ),
                    tile_padding=ft.Padding.symmetric(horizontal=8, vertical=8),
                    controls=[
                        ft.Container(
                            padding=ft.Padding.only(left=8, right=8, bottom=8),
                            content=ft.Column(
                                spacing=8,
                                controls=[
                                    ft.Container(
                                        height=220,
                                        bgcolor=ui_theme.WHITE,
                                        border_radius=ui_theme.RADIUS_SM,
                                        content=ft.Column(
                                            spacing=8,
                                            scroll=ft.ScrollMode.AUTO,
                                            controls=[
                                                *[
                                                    ft.Text(
                                                        linea,
                                                        size=12,
                                                        color=ui_theme.DARK_TEXT,
                                                    )
                                                    for linea in item.detalle_lineas
                                                ],
                                                *(
                                                    [
                                                        ft.Text(
                                                            f"Observaciones: {item.observaciones}",
                                                            size=12,
                                                            color=ui_theme.MID_GRAY,
                                                        )
                                                    ]
                                                    if item.observaciones
                                                    else []
                                                ),
                                            ],
                                        ),
                                    ),
                                    ft.Row(
                                        wrap=True,
                                        controls=[
                                            *(
                                                [
                                                    ft.FilledButton(
                                                        "Confirmar revisión",
                                                        disabled=(
                                                            bloqueado
                                                            or screen.anulacion_pendiente is not None
                                                        ),
                                                        style=ft.ButtonStyle(
                                                            bgcolor=ui_theme.SUCCESS,
                                                            color=ui_theme.WHITE,
                                                        ),
                                                        on_click=lambda _e, rid=item.registro_id: on_confirmar_revision_historial(
                                                            rid
                                                        ),
                                                    )
                                                ]
                                                if item.puede_confirmar_revision
                                                else []
                                            ),
                                            *(
                                                [
                                                    ft.TextButton(
                                                        "Anular",
                                                        disabled=(
                                                            bloqueado
                                                            or screen.anulacion_pendiente is not None
                                                        ),
                                                        style=ft.ButtonStyle(color=ui_theme.DANGER),
                                                        on_click=lambda _e, rid=item.registro_id: on_iniciar_anulacion(
                                                            rid
                                                        ),
                                                    )
                                                ]
                                                if item.puede_anular and item.estado == "activo"
                                                else []
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        )
                    ],
                    expanded=False,
                    maintain_state=True,
                ),
            )
            controls.append(tile)

    return ft.ExpansionTile(
        title=ft.Text(
            f"Historial reciente ({len(historial_items)})",
            size=16,
            weight=ft.FontWeight.W_600,
        ),
        subtitle=ft.Text(
            "Revise o anule registros del servicio activo",
            size=13,
            color=ui_theme.MID_GRAY,
        ),
        expanded=bool(screen.historial_expandido or screen.anulacion_pendiente),
        dense=False,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=8, right=8, bottom=12),
                height=320,
                content=ft.Column(
                    spacing=4,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                    controls=controls,
                ),
            )
        ],
    )


def _catalog_tile(
    item: CatalogItemVM,
    on_add_receta: Callable[[str], None],
    on_add_producto: Callable[..., None],
) -> ft.Control:
    is_receta = item.tipo == "receta"
    if is_receta and (item.categoria or "").lower() == "bebidas":
        badge = "Bebida"
        tone = "ok"
        icon = ft.Icons.LOCAL_CAFE
        hint = "1 ración al añadir · descuenta café/leche de la receta"
    elif is_receta:
        badge = "Receta"
        tone = "info"
        icon = ft.Icons.RESTAURANT_MENU
        hint = "1 ración al añadir · ajuste en cesta"
    elif item.es_bebida:
        badge = "Bebida"
        tone = "ok"
        icon = ft.Icons.LOCAL_BAR
        hint = (
            f"Stock {item.stock_disponible:g} {item.unidad}".strip()
            if item.stock_disponible is not None
            else (item.unidad or "Unidad")
        )
    else:
        badge = "Extra"
        tone = "neutral"
        icon = ft.Icons.ADD_SHOPPING_CART
        if item.hint_extra:
            hint = item.hint_extra
            if item.stock_disponible is not None:
                hint = f"{hint} · stock {item.stock_disponible:g} {item.unidad}".strip()
        else:
            hint = (
                f"Stock {item.stock_disponible:g} {item.unidad}".strip()
                if item.stock_disponible is not None
                else (item.unidad or "Por cantidad")
            )
    if is_receta and item.categoria:
        hint = f"{item.categoria} · {hint}"

    def _on_add(_e, it: CatalogItemVM = item) -> None:
        if it.tipo == "receta":
            on_add_receta(it.id)
            return
        qty = float(it.cantidad_default) if it.cantidad_default is not None else 1.0
        on_add_producto(it.id, qty)

    return ft.Container(
        bgcolor=ui_theme.WHITE,
        padding=ft.Padding.symmetric(horizontal=16, vertical=16),
        border_radius=ui_theme.RADIUS_MD,
        border=ft.Border.all(1, ui_theme.BORDER_STRONG),
        shadow=ft.BoxShadow(
            blur_radius=10,
            color="#0B1F3A12",
            offset=ft.Offset(0, 2),
        ),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=14,
            controls=[
                ft.Container(
                    width=52,
                    height=52,
                    bgcolor=ui_theme.NAVY,
                    border_radius=ui_theme.RADIUS_SM,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(icon, color=ui_theme.WHITE, size=28),
                ),
                ft.Column(
                    spacing=4,
                    expand=True,
                    tight=True,
                    controls=[
                        ft.Container(
                            bgcolor={
                                "info": ui_theme.INFO_BG,
                                "ok": ui_theme.SUCCESS_BG,
                                "neutral": ui_theme.LIGHT_GRAY,
                            }.get(tone, ui_theme.LIGHT_GRAY),
                            padding=ft.Padding.symmetric(horizontal=12, vertical=5),
                            border_radius=20,
                            content=ft.Text(
                                badge,
                                size=13,
                                weight=ft.FontWeight.W_600,
                                color={
                                    "info": ui_theme.INFO,
                                    "ok": ui_theme.SUCCESS,
                                    "neutral": ui_theme.DARK_TEXT,
                                }.get(tone, ui_theme.DARK_TEXT),
                            ),
                        ),
                        ft.Text(
                            item.nombre,
                            size=20,
                            weight=ft.FontWeight.BOLD,
                            color=ui_theme.DARK_TEXT,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(hint, size=15, color=ui_theme.MID_GRAY),
                    ],
                ),
                ft.FilledButton(
                    "Añadir",
                    icon=ft.Icons.ADD,
                    height=48,
                    style=ft.ButtonStyle(
                        bgcolor=ui_theme.TEAL,
                        color=ui_theme.WHITE,
                        text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_600),
                        padding=ft.Padding.symmetric(horizontal=18, vertical=12),
                        shape=ft.RoundedRectangleBorder(radius=ui_theme.RADIUS_SM),
                    ),
                    on_click=_on_add,
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
        padding=ft.Padding.symmetric(vertical=8),
        border=ft.Border(bottom=ft.BorderSide(1, ui_theme.BORDER)),
        content=ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Text(
                    nombre,
                    weight=ft.FontWeight.W_600,
                    size=16,
                    color=ui_theme.DARK_TEXT,
                ),
                ft.Row(
                    spacing=4,
                    controls=[
                        ft.IconButton(
                            icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                            icon_size=28,
                            icon_color=ui_theme.NAVY,
                            on_click=on_minus,
                        ),
                        ft.Text(
                            qty_label,
                            size=16,
                            weight=ft.FontWeight.W_600,
                            color=ui_theme.DARK_TEXT,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                            icon_size=28,
                            icon_color=ui_theme.NAVY,
                            on_click=on_plus,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            icon_size=26,
                            icon_color=ui_theme.DANGER,
                            on_click=on_remove,
                        ),
                    ],
                ),
            ],
        ),
    )
