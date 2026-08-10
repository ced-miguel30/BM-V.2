"""Vista de registro de servicio (catálogo + cesta + confirmar)."""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.presentation.flet.viewmodels import CatalogItemVM, TerminalScreenVM


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
    narrow: bool = False,
) -> ft.Control:
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
                ft.TextButton(
                    "Cerrar sesión",
                    icon=ft.Icons.LOGOUT,
                    style=ft.ButtonStyle(color=ft.Colors.WHITE),
                    on_click=lambda _e: on_logout(),
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

    search = ft.TextField(
        label="Buscar receta o producto",
        value=screen.busqueda,
        prefix_icon=ft.Icons.SEARCH,
        on_change=lambda e: on_search(e.control.value or ""),
        expand=True,
    )

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

    catalog_controls: list[ft.Control] = []
    if not screen.catalogo:
        catalog_controls.append(
            ft.Text(
                "No hay ítems para este servicio o filtro.",
                color=ft.Colors.OUTLINE,
                italic=True,
            )
        )
    else:
        for item in screen.catalogo:
            catalog_controls.append(_catalog_tile(item, on_add_receta, on_add_producto))

    catalog_col = ft.Column(
        spacing=8,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        controls=[search, *huespedes_row, *catalog_controls],
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
        or screen.cesta is None
        or screen.cesta.vacia,
        style=ft.ButtonStyle(
            padding=20,
            bgcolor=ft.Colors.ORANGE_800,
        ),
        on_click=lambda _e: on_confirm(),
    )
    basket_controls.append(confirm_btn)
    if screen.confirmando:
        basket_controls.append(ft.ProgressRing(width=24, height=24))

    basket_col = ft.Container(
        width=None if narrow else 340,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        padding=12,
        border_radius=8,
        content=ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, controls=basket_controls),
    )

    if narrow:
        body = ft.Column(
            expand=True,
            controls=[
                ft.Container(content=catalog_col, expand=True),
                ft.Divider(),
                basket_col,
            ],
        )
    else:
        body = ft.Row(
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Container(content=catalog_col, expand=True),
                basket_col,
            ],
        )

    return ft.Column(
        expand=True,
        spacing=12,
        controls=[header, selector, feedback, ft.Container(content=body, expand=True)],
    )


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
