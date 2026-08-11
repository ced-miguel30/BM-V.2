"""Vista de registro de servicio (catálogo + cesta + confirmar)."""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.presentation.flet.viewmodels import CatalogItemVM, TerminalScreenVM
from app.presentation.flet.views.menu_nav import header_action_row


def build_catalog_result_controls(
    screen: TerminalScreenVM,
    *,
    on_add_receta: Callable[[str], None],
    on_add_producto: Callable[[str], None],
) -> list[ft.Control]:
    """Solo filas del catálogo (sin campo de búsqueda)."""
    if not screen.catalogo:
        vacio = (
            "Ningún resultado para la búsqueda."
            if (screen.busqueda or "").strip()
            else "No hay ítems para este servicio o filtro."
        )
        return [ft.Text(vacio, color=ft.Colors.OUTLINE, italic=True)]
    return [
        _catalog_tile(item, on_add_receta, on_add_producto) for item in screen.catalogo
    ]


def build_registro_view(
    screen: TerminalScreenVM,
    *,
    on_select_servicio: Callable[[str], None],
    on_search: Callable[[str], None],
    on_add_receta: Callable[[str], None],
    on_add_producto: Callable[[str], None],
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
    narrow: bool = False,
    search_field: ft.TextField | None = None,
    catalog_results: ft.Column | None = None,
) -> tuple[ft.Control, ft.TextField, ft.Column]:
    """Construye la vista y expone controles estables de búsqueda/catálogo.

    Devuelve ``(root, search_field, catalog_results)`` para actualizar solo
    el listado sin reconstruir el TextField (conserva foco y cursor).
    """
    on_iniciar_anulacion = on_iniciar_anulacion or (lambda _rid: None)
    on_set_motivo_anulacion = on_set_motivo_anulacion or (lambda _m: None)
    on_cancelar_anulacion = on_cancelar_anulacion or (lambda: None)
    on_confirmar_anulacion = on_confirmar_anulacion or (lambda: None)
    activo = next((s for s in screen.servicios if s.activo), None)
    etiqueta_activo = activo.etiqueta if activo else "—"

    header = ft.Container(
        bgcolor=ft.Colors.BLUE_GREY_900,
        padding=ft.Padding.symmetric(horizontal=16, vertical=12),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Column(
                    spacing=2,
                    controls=[
                        ft.Text(
                            "Terminal Restaurante",
                            color=ft.Colors.WHITE,
                            size=20,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            f"Servicio activo: {etiqueta_activo}",
                            color=ft.Colors.LIGHT_BLUE_100,
                            size=14,
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

    selector = ft.Row(
        wrap=True,
        spacing=8,
        controls=[
            ft.FilledButton(
                s.etiqueta,
                style=ft.ButtonStyle(
                    padding=18,
                    bgcolor=ft.Colors.TEAL_700 if s.activo else None,
                ),
                on_click=lambda _e, sid=s.id: on_select_servicio(sid),
            )
            for s in screen.servicios
        ],
    )

    feedback = ft.Container()
    if screen.feedback:
        feedback = ft.Container(
            bgcolor=ft.Colors.GREEN_100 if screen.feedback.ok else ft.Colors.RED_100,
            padding=12,
            border_radius=8,
            content=ft.Text(screen.feedback.mensaje, size=14),
        )

    if search_field is None:
        search_field = ft.TextField(
            label="Buscar receta o producto",
            value=screen.busqueda,
            prefix_icon=ft.Icons.SEARCH,
            on_change=lambda e: on_search(e.control.value or ""),
            expand=True,
        )
    else:
        search_field.on_change = lambda e: on_search(e.control.value or "")

    huespedes_row: list[ft.Control] = []
    if screen.requiere_huespedes:
        huespedes_row = [
            ft.Row(
                controls=[
                    ft.Text("Huéspedes:", size=14),
                    ft.IconButton(
                        icon=ft.Icons.REMOVE,
                        on_click=lambda _e: on_huespedes(max(1, screen.num_huespedes - 1)),
                    ),
                    ft.Text(str(screen.num_huespedes), size=18, weight=ft.FontWeight.BOLD),
                    ft.IconButton(
                        icon=ft.Icons.ADD,
                        on_click=lambda _e: on_huespedes(screen.num_huespedes + 1),
                    ),
                ]
            )
        ]

    result_controls = build_catalog_result_controls(
        screen, on_add_receta=on_add_receta, on_add_producto=on_add_producto
    )
    if catalog_results is None:
        catalog_results = ft.Column(
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            controls=result_controls,
        )
    else:
        catalog_results.controls = result_controls

    catalog_col = ft.Column(
        spacing=8,
        expand=True,
        controls=[search_field, *huespedes_row, catalog_results],
    )

    basket_controls: list[ft.Control] = [
        ft.Text("Cesta", size=18, weight=ft.FontWeight.BOLD),
    ]
    if screen.cesta is None or screen.cesta.vacia:
        basket_controls.append(
            ft.Text("Cesta vacía. Añada recetas o productos.", color=ft.Colors.OUTLINE)
        )
    else:
        for lin in screen.cesta.lineas:
            if lin.kind == "receta":
                basket_controls.append(
                    _basket_row(
                        lin.nombre,
                        f"{lin.cantidad:g} {lin.unidad}",
                        on_minus=lambda _e, gid=lin.line_id: on_qty_receta(gid, -1),
                        on_plus=lambda _e, gid=lin.line_id: on_qty_receta(gid, 1),
                        on_remove=lambda _e, gid=lin.line_id: on_remove_receta(gid),
                    )
                )
            else:
                basket_controls.append(
                    _basket_row(
                        lin.nombre,
                        f"{lin.cantidad:g} {lin.unidad}",
                        on_minus=lambda _e, lid=lin.line_id: on_qty_producto(lid, -1),
                        on_plus=lambda _e, lid=lin.line_id: on_qty_producto(lid, 1),
                        on_remove=lambda _e, lid=lin.line_id: on_remove_producto(lid),
                    )
                )
        basket_controls.append(
            ft.TextButton("Vaciar cesta", on_click=lambda _e: on_clear())
        )

    confirm_btn = ft.FilledButton(
        "Confirmar registro",
        icon=ft.Icons.CHECK_CIRCLE,
        disabled=screen.confirmando
        or screen.anulando
        or screen.cesta is None
        or screen.cesta.vacia,
        style=ft.ButtonStyle(
            padding=20,
            bgcolor=ft.Colors.ORANGE_800,
        ),
        on_click=lambda _e: on_confirm(),
    )
    basket_controls.append(confirm_btn)
    if screen.confirmando or screen.anulando:
        basket_controls.append(ft.ProgressRing(width=24, height=24))

    basket_col = ft.Container(
        width=None if narrow else 340,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        padding=12,
        border_radius=8,
        content=ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, controls=basket_controls),
    )

    historial_box = _historial_section(
        screen,
        on_iniciar_anulacion=on_iniciar_anulacion,
        on_set_motivo_anulacion=on_set_motivo_anulacion,
        on_cancelar_anulacion=on_cancelar_anulacion,
        on_confirmar_anulacion=on_confirmar_anulacion,
    )

    if narrow:
        body = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Container(content=catalog_col, expand=True),
                ft.Divider(),
                basket_col,
                ft.Divider(),
                historial_box,
            ],
        )
    else:
        body = ft.Column(
            expand=True,
            controls=[
                ft.Row(
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Container(content=catalog_col, expand=True),
                        basket_col,
                    ],
                ),
                ft.Divider(),
                historial_box,
            ],
        )

    root = ft.Column(
        expand=True,
        spacing=12,
        controls=[header, selector, feedback, ft.Container(content=body, expand=True)],
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
    controls: list[ft.Control] = [
        ft.Text("Historial reciente", size=18, weight=ft.FontWeight.BOLD),
        ft.Text(
            "Solo datos operativos. Sin economía ni valoración.",
            size=11,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
    ]
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
                bgcolor=ft.Colors.AMBER_50,
                padding=12,
                border_radius=8,
                content=ft.Column(
                    spacing=8,
                    controls=[
                        ft.Text(
                            "Confirmar anulación",
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(p.etiqueta_corta, size=13),
                        ft.Text(p.resumen, size=12),
                        motivo_tf,
                        ft.Row(
                            controls=[
                                ft.FilledButton(
                                    "Confirmar anulación",
                                    disabled=bloqueado,
                                    bgcolor=ft.Colors.RED_700,
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
            ft.Text(
                "Sin registros recientes en este servicio.",
                color=ft.Colors.OUTLINE,
                italic=True,
                size=12,
            )
        )
    else:
        for item in screen.historial:
            fila: list[ft.Control] = [
                ft.Column(
                    spacing=2,
                    expand=True,
                    controls=[
                        ft.Text(item.etiqueta_corta, weight=ft.FontWeight.W_500, size=13),
                        ft.Text(item.resumen, size=12),
                        ft.Text(
                            _estado_label(item.estado)
                            + (
                                f" — {item.motivo_bloqueo}"
                                if item.estado == "no_anulable" and item.motivo_bloqueo
                                else ""
                            ),
                            size=11,
                            color=(
                                ft.Colors.GREEN_800
                                if item.estado == "activo"
                                else (
                                    ft.Colors.OUTLINE
                                    if item.estado == "anulado"
                                    else ft.Colors.AMBER_900
                                )
                            ),
                        ),
                    ],
                ),
            ]
            if item.puede_anular and item.estado == "activo":
                fila.append(
                    ft.TextButton(
                        "Anular",
                        disabled=bloqueado or screen.anulacion_pendiente is not None,
                        on_click=lambda _e, rid=item.registro_id: on_iniciar_anulacion(
                            rid
                        ),
                    )
                )
            controls.append(
                ft.Container(
                    padding=8,
                    border=ft.Border(
                        bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)
                    ),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=fila,
                    ),
                )
            )
    return ft.Column(spacing=8, controls=controls)


def _catalog_tile(
    item: CatalogItemVM,
    on_add_receta: Callable[[str], None],
    on_add_producto: Callable[[str], None],
) -> ft.Control:
    is_receta = item.tipo == "receta"
    badge = "RECETA" if is_receta else "PRODUCTO DIRECTO"
    color = ft.Colors.INDIGO_100 if is_receta else ft.Colors.AMBER_100
    detail = item.categoria if is_receta else (
        f"{item.stock_disponible:g} {item.unidad}".strip()
        if item.stock_disponible is not None
        else item.unidad
    )
    return ft.Container(
        bgcolor=color,
        padding=12,
        border_radius=10,
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Column(
                    spacing=2,
                    expand=True,
                    controls=[
                        ft.Text(badge, size=11, weight=ft.FontWeight.W_600),
                        ft.Text(item.nombre, size=16, weight=ft.FontWeight.BOLD),
                        ft.Text(detail or "", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                    ],
                ),
                ft.FilledTonalButton(
                    "Añadir",
                    height=48,
                    on_click=(
                        (lambda _e, rid=item.id: on_add_receta(rid))
                        if is_receta
                        else (lambda _e, pid=item.id: on_add_producto(pid))
                    ),
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
        padding=8,
        border=ft.Border(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        content=ft.Column(
            spacing=4,
            controls=[
                ft.Text(nombre, weight=ft.FontWeight.W_500),
                ft.Row(
                    controls=[
                        ft.IconButton(icon=ft.Icons.REMOVE_CIRCLE_OUTLINE, on_click=on_minus),
                        ft.Text(qty_label, size=14),
                        ft.IconButton(icon=ft.Icons.ADD_CIRCLE_OUTLINE, on_click=on_plus),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            icon_color=ft.Colors.RED_400,
                            on_click=on_remove,
                        ),
                    ]
                ),
            ],
        ),
    )
