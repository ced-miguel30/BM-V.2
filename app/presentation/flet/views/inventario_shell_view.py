"""Vistas Flet — Terminal Inventario."""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.core.models import EstadoAlerta
from app.presentation.flet.inventory_viewmodels import InventarioScreenVM


def build_login_inventario(*, on_enter: Callable[[], None]) -> ft.Control:
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        padding=24,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20,
            tight=True,
            controls=[
                ft.Text("Terminal Inventario", size=36, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Alertas, caducidad, merma y ajustes operativos.",
                    size=16,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.FilledButton(
                    "Entrar al terminal",
                    icon=ft.Icons.INVENTORY_2,
                    style=ft.ButtonStyle(padding=20),
                    on_click=lambda _e: on_enter(),
                ),
                ft.Text(
                    "Sin costes, compras ni administración.",
                    size=12,
                    color=ft.Colors.OUTLINE,
                ),
            ],
        ),
    )


def build_inventario_shell(
    screen: InventarioScreenVM,
    *,
    on_espacio: Callable[[str], None],
    on_logout: Callable[[], None],
    on_alerta_estado: Callable[[str, str], None],
    on_caducidad_a_merma: Callable[[str, float], None],
    on_anadir_merma: Callable[[str, float, str], None],
    on_vaciar_merma: Callable[[], None],
    on_confirmar_merma: Callable[[], None],
    on_preview_ajuste: Callable[[str, float, str], None],
    on_confirmar_ajuste: Callable[[], None],
    narrow: bool = False,
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
                            "Terminal Inventario",
                            color=ft.Colors.WHITE,
                            size=20,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            f"Identidad: {screen.session.actor_label}",
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

    nav = ft.Row(
        wrap=True,
        spacing=8,
        controls=[
            ft.FilledButton(
                e.etiqueta,
                style=ft.ButtonStyle(
                    padding=16,
                    bgcolor=ft.Colors.TEAL_700 if e.activo else None,
                ),
                on_click=lambda _e, eid=e.id: on_espacio(eid),
            )
            for e in screen.espacios
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

    body: ft.Control
    if screen.espacio_activo == "alertas":
        body = _alertas_body(screen, on_alerta_estado)
    elif screen.espacio_activo == "caducidad":
        body = _caducidad_body(screen, on_caducidad_a_merma)
    elif screen.espacio_activo == "merma":
        body = _merma_body(
            screen, on_anadir_merma, on_vaciar_merma, on_confirmar_merma
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


def _caducidad_body(screen: InventarioScreenVM, on_enviar) -> ft.Control:
    if not screen.lotes_caducidad:
        return ft.Text(
            "No hay lotes próximos a caducar ni vencidos.",
            italic=True,
            color=ft.Colors.OUTLINE,
        )
    rows: list[ft.Control] = []
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


def _merma_body(screen, on_anadir, on_vaciar, on_confirmar) -> ft.Control:
    lotes = screen.lotes_ajuste  # reutilizar listado operativo de lotes con stock vía ajustes
    # Preferir lotes de merma: si vacíos en este espacio, mostrar cesta + mensaje
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
                    f"{ln.nombre}: {ln.cantidad:g} {ln.unidad} · {ln.motivo} · {ln.servicio}",
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
            ft.Row(controls=[lote_dd]),
            ft.Row(controls=[qty, motivo, ft.FilledTonalButton("Añadir", on_click=_add)]),
            ft.Divider(),
            *cesta_rows,
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
