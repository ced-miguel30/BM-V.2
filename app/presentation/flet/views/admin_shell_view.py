"""Vista Administración operativa — responsables de merma."""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.presentation.flet.admin_viewmodels import AdminScreenVM, ResponsableMermaVM
from app.presentation.flet.views.menu_nav import (
    build_volver_al_menu_button,
    header_action_row,
)


def build_login_admin(
    *,
    on_login: Callable[[str, str], None],
    feedback_mensaje: str = "",
    on_volver_menu: Callable[[], None] | None = None,
) -> ft.Control:
    login_tf = ft.TextField(label="Identificador", autofocus=True, width=320)
    pass_tf = ft.TextField(
        label="Contraseña",
        password=True,
        can_reveal_password=True,
        width=320,
    )
    err = ft.Text(feedback_mensaje, color=ft.Colors.RED_700) if feedback_mensaje else ft.Container()

    def _submit(_e=None) -> None:
        on_login(login_tf.value or "", pass_tf.value or "")

    pass_tf.on_submit = _submit
    controls: list[ft.Control] = [
        ft.Text(
            "Administración operativa",
            size=32,
            weight=ft.FontWeight.BOLD,
        ),
        ft.Text(
            "Configuración mínima para las terminales (responsables de merma).",
            size=14,
            color=ft.Colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.CENTER,
        ),
        login_tf,
        pass_tf,
        ft.FilledButton(
            "Entrar",
            icon=ft.Icons.LOGIN,
            style=ft.ButtonStyle(padding=18),
            on_click=_submit,
        ),
        err,
    ]
    volver = build_volver_al_menu_button(on_volver_menu)
    if volver is not None:
        controls.append(volver)
    controls.append(
        ft.Text(
            "Sin costes, compras ni zona de peligro.",
            size=12,
            color=ft.Colors.OUTLINE,
        )
    )
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        padding=24,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=16,
            tight=True,
            controls=controls,
        ),
    )


def build_admin_shell(
    screen: AdminScreenVM,
    *,
    on_logout: Callable[[], None],
    on_filtro: Callable[[str], None],
    on_proponer_crear: Callable[[str], None],
    on_proponer_renombrar: Callable[[str, str], None],
    on_proponer_desactivar: Callable[[str], None],
    on_proponer_reactivar: Callable[[str], None],
    on_confirmar: Callable[[], None],
    on_cancelar: Callable[[], None],
    on_volver_menu: Callable[[], None] | None = None,
) -> ft.Control:
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
                            "Administración operativa",
                            color=ft.Colors.WHITE,
                            size=20,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            f"{screen.session.actor_label} · {screen.session.role}",
                            color=ft.Colors.LIGHT_BLUE_100,
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

    feedback = ft.Container()
    if screen.feedback:
        feedback = ft.Container(
            bgcolor=ft.Colors.GREEN_100 if screen.feedback.ok else ft.Colors.RED_100,
            padding=12,
            border_radius=8,
            content=ft.Text(screen.feedback.mensaje, size=14),
        )

    pending_box = ft.Container()
    if screen.pending:
        pending_box = ft.Container(
            bgcolor=ft.Colors.AMBER_50,
            padding=12,
            border_radius=8,
            border=ft.Border.all(1, ft.Colors.AMBER_700),
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Text("Resumen del cambio", weight=ft.FontWeight.BOLD),
                    ft.Text(screen.pending.resumen),
                    ft.Row(
                        controls=[
                            ft.FilledButton(
                                "Confirmar",
                                disabled=screen.mutando,
                                on_click=lambda _e: on_confirmar(),
                            ),
                            ft.TextButton(
                                "Cancelar",
                                disabled=screen.mutando,
                                on_click=lambda _e: on_cancelar(),
                            ),
                            ft.ProgressRing(width=20, height=20)
                            if screen.mutando
                            else ft.Container(),
                        ]
                    ),
                ],
            ),
        )

    crear_tf = ft.TextField(label="Nuevo responsable", expand=True)
    filtro_tf = ft.TextField(
        label="Buscar",
        value=screen.filtro,
        prefix_icon=ft.Icons.SEARCH,
        hint_text="Filtrar por nombre o id",
        on_submit=lambda e: on_filtro(e.control.value or ""),
        expand=True,
    )
    filtrar_btn = ft.OutlinedButton(
        "Filtrar",
        on_click=lambda _e: on_filtro(filtro_tf.value or ""),
    )

    lista: list[ft.Control] = []
    if not screen.responsables:
        lista.append(
            ft.Container(
                bgcolor=ft.Colors.SURFACE,
                padding=16,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                border_radius=8,
                content=ft.Text(
                    "No hay responsables con ese filtro."
                    if screen.filtro
                    else "No hay responsables. Cree el primero.",
                    color=ft.Colors.ON_SURFACE,
                    size=14,
                ),
            )
        )
    else:
        for r in screen.responsables:
            lista.append(
                _responsable_row(
                    r,
                    disabled=screen.mutando or screen.pending is not None,
                    on_renombrar=on_proponer_renombrar,
                    on_desactivar=on_proponer_desactivar,
                    on_reactivar=on_proponer_reactivar,
                )
            )

    motivos_info = ft.ExpansionTile(
        title=ft.Text("Motivos de merma (catálogo fijo)"),
        subtitle=ft.Text("No configurables — enum de dominio"),
        controls=[
            ft.Text(" · ".join(screen.motivos_fijos), size=12, color=ft.Colors.OUTLINE)
        ],
    )

    body = ft.Column(
        expand=True,
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Text("Responsables de merma", size=18, weight=ft.FontWeight.BOLD),
            ft.Row(
                controls=[
                    crear_tf,
                    ft.FilledButton(
                        "Añadir",
                        icon=ft.Icons.PERSON_ADD,
                        disabled=screen.mutando,
                        on_click=lambda _e: on_proponer_crear(crear_tf.value or ""),
                    ),
                ]
            ),
            ft.Row(controls=[filtro_tf, filtrar_btn]),
            pending_box,
            ft.Text(
                f"{len(screen.responsables)} en listado"
                + (f" (filtro: {screen.filtro})" if screen.filtro else ""),
                size=12,
                color=ft.Colors.OUTLINE,
            ),
            *lista,
            motivos_info,
        ],
    )

    return ft.Column(
        expand=True,
        spacing=12,
        controls=[
            header,
            feedback,
            ft.Container(content=body, expand=True, padding=16),
        ],
    )


def _responsable_row(
    r: ResponsableMermaVM,
    *,
    disabled: bool,
    on_renombrar: Callable[[str, str], None],
    on_desactivar: Callable[[str], None],
    on_reactivar: Callable[[str], None],
) -> ft.Control:
    rename_tf = ft.TextField(
        label="Nuevo nombre",
        value=r.nombre,
        width=240,
        disabled=disabled,
    )
    estado = "Activo" if r.activo else "Inactivo"
    chip_bg = ft.Colors.TEAL_700 if r.activo else ft.Colors.BLUE_GREY_600
    row_bg = ft.Colors.WHITE if r.activo else ft.Colors.BLUE_GREY_50
    acciones: list[ft.Control] = [
        ft.OutlinedButton(
            "Renombrar",
            disabled=disabled,
            on_click=lambda _e, rid=r.id, tf=rename_tf: on_renombrar(
                rid, tf.value or ""
            ),
        ),
    ]
    if r.activo:
        acciones.append(
            ft.TextButton(
                "Desactivar",
                disabled=disabled,
                style=ft.ButtonStyle(color=ft.Colors.RED_700),
                on_click=lambda _e, rid=r.id: on_desactivar(rid),
            )
        )
    else:
        acciones.append(
            ft.TextButton(
                "Reactivar",
                disabled=disabled,
                on_click=lambda _e, rid=r.id: on_reactivar(rid),
            )
        )
    return ft.Container(
        bgcolor=row_bg,
        padding=14,
        border_radius=8,
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_300),
        content=ft.Column(
            spacing=8,
            tight=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(r.nombre, size=16, weight=ft.FontWeight.BOLD),
                        ft.Container(
                            bgcolor=chip_bg,
                            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                            border_radius=12,
                            content=ft.Text(
                                estado, color=ft.Colors.WHITE, size=12, weight=ft.FontWeight.W_600
                            ),
                        ),
                    ],
                ),
                ft.Text(f"Id: {r.id}", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                rename_tf,
                ft.Row(controls=acciones),
            ],
        ),
    )
