"""Vista Administración operativa — maestros, responsables, backup."""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.presentation.flet.admin_viewmodels import (
    ADMIN_NAV_GROUPS,
    ADMIN_SECCION_LABEL,
    MATCH_ESTADO_ETIQUETA,
    AdminScreenVM,
    BackupItemVM,
    CatalogoItemVM,
    CompraLineaVM,
    ProductoAdminVM,
    ProveedorAdminVM,
    RecetaAdminVM,
    ResponsableMermaVM,
    UsuarioAdminVM,
    secciones_visibles_admin,
)
from app.presentation.flet.analisis_viewmodels import (
    ANALISIS_HUB_LABEL,
    ANALISIS_HUBS,
    COSTES_PESTANAS,
    CONSUMO_PESTANAS,
    CONSUMO_TIPOS,
    MERMA_PESTANAS,
    AnalisisPanelVM,
)
from app.presentation.flet.charts import (
    build_barras_agrupadas,
    build_barras_horizontales,
    build_donut,
    build_lineas_series,
)
from app.presentation.flet import theme as ui_theme
from app.presentation.flet import ui_components as ui

_SECCION_ICONS: dict[str, tuple] = {
    "inicio": (ft.Icons.HOME_OUTLINED, ft.Icons.HOME),
    "analisis": (ft.Icons.ANALYTICS_OUTLINED, ft.Icons.ANALYTICS),
    "productos": (ft.Icons.INVENTORY_2_OUTLINED, ft.Icons.INVENTORY_2),
    "recetas": (ft.Icons.MENU_BOOK_OUTLINED, ft.Icons.MENU_BOOK),
    "usuarios": (ft.Icons.PEOPLE_OUTLINE, ft.Icons.PEOPLE),
    "responsables": (ft.Icons.PERSON_OUTLINE, ft.Icons.PERSON),
    "catalogos": (ft.Icons.LIST_ALT_OUTLINED, ft.Icons.LIST_ALT),
    "proveedores": (ft.Icons.STORE_OUTLINED, ft.Icons.STORE),
    "compras": (ft.Icons.SHOPPING_CART_OUTLINED, ft.Icons.SHOPPING_CART),
    "documentos": (ft.Icons.DESCRIPTION_OUTLINED, ft.Icons.DESCRIPTION),
    "inventario_inicial": (ft.Icons.ADD_BOX_OUTLINED, ft.Icons.ADD_BOX),
    "actividad": (ft.Icons.HISTORY, ft.Icons.HISTORY),
    "backup": (ft.Icons.BACKUP_OUTLINED, ft.Icons.BACKUP),
    "configuracion": (ft.Icons.SETTINGS_OUTLINED, ft.Icons.SETTINGS),
    "servidor": (ft.Icons.STORAGE_OUTLINED, ft.Icons.STORAGE),
    "zona_peligro": (ft.Icons.WARNING_AMBER_OUTLINED, ft.Icons.WARNING_AMBER),
}
from app.presentation.flet.views.menu_nav import (
    build_volver_al_menu_button,
    header_action_row,
)


def build_bootstrap_admin(
    *,
    on_bootstrap: Callable[[str, str, str, str], None],
    feedback_mensaje: str = "",
    on_volver_menu: Callable[[], None] | None = None,
) -> ft.Control:
    nombre_tf = ft.TextField(label="Nombre visible", autofocus=True, width=360)
    login_tf = ft.TextField(label="Identificador de acceso", width=360)
    pass_tf = ft.TextField(
        label="Contraseña",
        password=True,
        can_reveal_password=True,
        width=360,
    )
    pass2_tf = ft.TextField(
        label="Repetir contraseña",
        password=True,
        can_reveal_password=True,
        width=360,
    )

    def _submit(_e=None) -> None:
        on_bootstrap(
            nombre_tf.value or "",
            login_tf.value or "",
            pass_tf.value or "",
            pass2_tf.value or "",
        )

    pass2_tf.on_submit = _submit
    extras: list[ft.Control] = []
    if feedback_mensaje:
        extras.append(ui.alert_banner(feedback_mensaje, severity="error"))
    extras.extend(
        [
            ui.alert_banner(
                "No hay usuario Dirección con credenciales. "
                "Cree el acceso administrativo inicial.",
                severity="warning",
            ),
            nombre_tf,
            login_tf,
            pass_tf,
            pass2_tf,
            ui.primary_button(
                "Crear acceso Dirección",
                _submit,
                icon=ft.Icons.PERSON_ADD,
            ),
        ]
    )
    volver = build_volver_al_menu_button(on_volver_menu)
    if volver is not None:
        extras.append(volver)
    return ui.branded_page(
        ui.auth_card(
            *extras,
            titulo="Configuración inicial",
            subtitulo="Acceso privilegiado para operación del hotel",
        )
    )


def build_login_admin(
    *,
    on_login: Callable[[str, str], None],
    feedback_mensaje: str = "",
    on_volver_menu: Callable[[], None] | None = None,
) -> ft.Control:
    login_tf = ft.TextField(label="Identificador", autofocus=True, width=360)
    pass_tf = ft.TextField(
        label="Contraseña",
        password=True,
        can_reveal_password=True,
        width=360,
    )

    def _submit(_e=None) -> None:
        on_login(login_tf.value or "", pass_tf.value or "")

    pass_tf.on_submit = _submit
    extras: list[ft.Control] = []
    if feedback_mensaje:
        extras.append(ui.alert_banner(feedback_mensaje, severity="error"))
    extras.extend(
        [
            login_tf,
            pass_tf,
            ui.primary_button("Entrar", _submit, icon=ft.Icons.LOGIN),
        ]
    )
    volver = build_volver_al_menu_button(on_volver_menu)
    if volver is not None:
        extras.append(volver)
    extras.append(
        ft.Text(
            "Maestros, compras, documentos, análisis y backup",
            size=11,
            color=ui_theme.MID_GRAY,
            text_align=ft.TextAlign.CENTER,
        )
    )
    return ui.branded_page(
        ui.auth_card(
            *extras,
            titulo="Administración",
            subtitulo="Consola operativa del establecimiento",
        )
    )


def build_admin_shell(
    screen: AdminScreenVM,
    *,
    on_logout: Callable[[], None],
    on_seccion: Callable[[str], None],
    on_filtro: Callable[[str], None],
    # responsables
    on_proponer_crear: Callable[[str], None],
    on_proponer_renombrar: Callable[[str, str], None],
    on_proponer_desactivar: Callable[[str], None],
    on_proponer_reactivar: Callable[[str], None],
    # productos
    on_crear_producto: Callable[..., None],
    on_desactivar_producto: Callable[[str], None],
    on_reactivar_producto: Callable[[str], None],
    # recetas
    on_crear_receta: Callable[..., None],
    on_editar_receta: Callable[..., None],
    on_iniciar_edicion_receta: Callable[[str], None],
    on_cancelar_edicion_receta: Callable[[], None],
    on_eliminar_receta: Callable[[str], None],
    on_desactivar_receta: Callable[[str], None],
    on_reactivar_receta: Callable[[str], None],
    # usuarios
    on_crear_usuario: Callable[..., None],
    on_editar_usuario: Callable[[str, str], None],
    on_cambiar_rol: Callable[[str, str], None],
    on_desactivar_usuario: Callable[[str], None],
    on_reactivar_usuario: Callable[[str], None],
    on_restablecer_password: Callable[[str, str], None],
    # inventario / backup / config
    on_registrar_lote: Callable[..., None],
    on_crear_proveedor: Callable[..., None],
    on_editar_proveedor: Callable[..., None],
    on_desactivar_proveedor: Callable[[str], None],
    on_reactivar_proveedor: Callable[[str], None],
    on_set_compra_cabecera: Callable[..., None],
    on_añadir_linea_compra: Callable[..., None],
    on_añadir_linea_compra_busqueda: Callable[..., None] | None = None,
    on_update_linea_compra: Callable[..., None] | None = None,
    on_quitar_linea_compra: Callable[[int], None],
    on_guardar_borrador_compra: Callable[[], None],
    on_confirmar_compra: Callable[[], None],
    on_limpiar_borrador_compra: Callable[[], None],
    on_set_compra_prod_busqueda: Callable[[str], None] | None = None,
    on_seleccionar_sugerencia_compra: Callable[[str], None] | None = None,
    on_cargar_borrador_compra: Callable[[str], None] | None = None,
    on_anular_borrador_compra: Callable[[str], None] | None = None,
    on_generar_backup: Callable[[], None],
    on_inspeccionar_backup: Callable[[str], None],
    on_proponer_restaurar: Callable[[str, str], None],
    on_guardar_hotel: Callable[[str, str], None],
    on_refresh_datos: Callable[[], None],
    on_guardar_shared_root: Callable[[str], None],
    on_crear_departamento: Callable[[str], None],
    on_crear_categoria: Callable[[str], None],
    on_crear_ubicacion: Callable[[str, str], None],
    on_ejecutar_destructiva: Callable[[str, str, bool], None],
    on_exportar_documentos: Callable[[], None],
    on_set_compra_albaran: Callable[[str], None] | None = None,
    on_importar_noray: Callable[[], None] | None = None,
    on_set_compra_linea_ubicacion: Callable[[int, str], None] | None = None,
    on_set_compra_linea_producto: Callable[[int, str], None] | None = None,
    on_verificar_linea_compra: Callable[[int], None] | None = None,
    on_crear_producto_linea_noray: Callable[[int], None] | None = None,
    on_proponer_anular_documento: Callable[[str, str], None] | None = None,
    on_proponer_rectificativa_economica: Callable[[str, str], None] | None = None,
    on_proponer_rectificativa_stock: Callable[[str, str], None] | None = None,
    on_adjuntar_archivo: Callable[[str, str], None] | None = None,
    on_abrir_adjunto: Callable[[str], None] | None = None,
    # análisis
    on_analisis_hub: Callable[[str], None] | None = None,
    on_analisis_pestana: Callable[[str], None] | None = None,
    on_analisis_subtab: Callable[[str], None] | None = None,
    on_analisis_periodo: Callable[[str, str], None] | None = None,
    on_analisis_busqueda: Callable[[str], None] | None = None,
    on_analisis_tipo: Callable[[str], None] | None = None,
    on_analisis_comparacion: Callable[[str, str, str, str], None] | None = None,
    on_analisis_export: Callable[[], None] | None = None,
    on_importar_productos: Callable[[], None] | None = None,
    on_productos_page: Callable[[int], None] | None = None,
    on_confirmar: Callable[[], None] = None,  # type: ignore[assignment]
    on_cancelar: Callable[[], None] = None,  # type: ignore[assignment]
    on_volver_menu: Callable[[], None] | None = None,
) -> ft.Control:
    hotel = screen.hotel_nombre or ui_theme.HOTEL_DEFAULT
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
                            "Administración operativa",
                            color=ui_theme.WHITE,
                            size=20,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            f"{hotel} · {screen.session.actor_label} · {screen.session.role}",
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

    feedback = ft.Container()
    if screen.feedback:
        feedback = ft.Container(
            padding=ft.Padding.symmetric(horizontal=20, vertical=8),
            bgcolor=ui_theme.SURFACE,
            content=ui.alert_banner(
                screen.feedback.mensaje,
                severity="success" if screen.feedback.ok else "error",
            ),
        )

    pending_box = _pending_box(screen, on_confirmar=on_confirmar, on_cancelar=on_cancelar)

    visibles = secciones_visibles_admin(
        puede_zona_peligro=screen.puede_zona_peligro,
        puede_ver_analisis=screen.puede_ver_analisis,
    )
    sidebar = _build_sidebar(
        screen,
        visibles=visibles,
        on_seccion=on_seccion,
    )

    panel = _panel_for_seccion(
        screen,
        on_filtro=on_filtro,
        on_seccion=on_seccion,
        on_proponer_crear=on_proponer_crear,
        on_proponer_renombrar=on_proponer_renombrar,
        on_proponer_desactivar=on_proponer_desactivar,
        on_proponer_reactivar=on_proponer_reactivar,
        on_crear_producto=on_crear_producto,
        on_desactivar_producto=on_desactivar_producto,
        on_reactivar_producto=on_reactivar_producto,
        on_importar_productos=on_importar_productos,
        on_productos_page=on_productos_page,
        on_crear_receta=on_crear_receta,
        on_editar_receta=on_editar_receta,
        on_iniciar_edicion_receta=on_iniciar_edicion_receta,
        on_cancelar_edicion_receta=on_cancelar_edicion_receta,
        on_eliminar_receta=on_eliminar_receta,
        on_desactivar_receta=on_desactivar_receta,
        on_reactivar_receta=on_reactivar_receta,
        on_crear_usuario=on_crear_usuario,
        on_editar_usuario=on_editar_usuario,
        on_cambiar_rol=on_cambiar_rol,
        on_desactivar_usuario=on_desactivar_usuario,
        on_reactivar_usuario=on_reactivar_usuario,
        on_restablecer_password=on_restablecer_password,
        on_registrar_lote=on_registrar_lote,
        on_crear_proveedor=on_crear_proveedor,
        on_editar_proveedor=on_editar_proveedor,
        on_desactivar_proveedor=on_desactivar_proveedor,
        on_reactivar_proveedor=on_reactivar_proveedor,
        on_set_compra_cabecera=on_set_compra_cabecera,
        on_añadir_linea_compra=on_añadir_linea_compra,
        on_añadir_linea_compra_busqueda=on_añadir_linea_compra_busqueda,
        on_update_linea_compra=on_update_linea_compra,
        on_quitar_linea_compra=on_quitar_linea_compra,
        on_guardar_borrador_compra=on_guardar_borrador_compra,
        on_confirmar_compra=on_confirmar_compra,
        on_limpiar_borrador_compra=on_limpiar_borrador_compra,
        on_set_compra_prod_busqueda=on_set_compra_prod_busqueda,
        on_seleccionar_sugerencia_compra=on_seleccionar_sugerencia_compra,
        on_cargar_borrador_compra=on_cargar_borrador_compra,
        on_anular_borrador_compra=on_anular_borrador_compra,
        on_set_compra_albaran=on_set_compra_albaran,
        on_importar_noray=on_importar_noray,
        on_set_compra_linea_ubicacion=on_set_compra_linea_ubicacion,
        on_set_compra_linea_producto=on_set_compra_linea_producto,
        on_verificar_linea_compra=on_verificar_linea_compra,
        on_crear_producto_linea_noray=on_crear_producto_linea_noray,
        on_generar_backup=on_generar_backup,
        on_inspeccionar_backup=on_inspeccionar_backup,
        on_proponer_restaurar=on_proponer_restaurar,
        on_guardar_hotel=on_guardar_hotel,
        on_refresh_datos=on_refresh_datos,
        on_guardar_shared_root=on_guardar_shared_root,
        on_crear_departamento=on_crear_departamento,
        on_crear_categoria=on_crear_categoria,
        on_crear_ubicacion=on_crear_ubicacion,
        on_ejecutar_destructiva=on_ejecutar_destructiva,
        on_exportar_documentos=on_exportar_documentos,
        on_proponer_anular_documento=on_proponer_anular_documento,
        on_proponer_rectificativa_economica=on_proponer_rectificativa_economica,
        on_proponer_rectificativa_stock=on_proponer_rectificativa_stock,
        on_adjuntar_archivo=on_adjuntar_archivo,
        on_abrir_adjunto=on_abrir_adjunto,
        on_analisis_hub=on_analisis_hub,
        on_analisis_pestana=on_analisis_pestana,
        on_analisis_subtab=on_analisis_subtab,
        on_analisis_periodo=on_analisis_periodo,
        on_analisis_busqueda=on_analisis_busqueda,
        on_analisis_tipo=on_analisis_tipo,
        on_analisis_comparacion=on_analisis_comparacion,
        on_analisis_export=on_analisis_export,
    )

    body = ft.Row(
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        spacing=0,
        controls=[
            sidebar,
            ft.Container(
                expand=True,
                bgcolor=ui_theme.SURFACE,
                padding=ft.Padding.symmetric(horizontal=20, vertical=16),
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                content=ft.Column(
                    expand=True,
                    spacing=12,
                    scroll=ft.ScrollMode.AUTO,
                    controls=[
                        pending_box,
                        panel,
                        ft.Container(height=24),
                    ],
                ),
            ),
        ],
    )

    return ft.Column(
        expand=True,
        spacing=0,
        controls=[
            header,
            feedback,
            ft.Container(expand=True, content=body),
        ],
    )


def _build_sidebar(
    screen: AdminScreenVM,
    *,
    visibles: tuple[str, ...],
    on_seccion: Callable[[str], None],
) -> ft.Control:
    visible_set = set(visibles)
    items: list[ft.Control] = [
        ft.Container(
            padding=ft.Padding.only(left=14, right=14, top=16, bottom=10),
            content=ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    ft.Text(
                        ui_theme.APP_NAME,
                        size=11,
                        weight=ft.FontWeight.W_600,
                        color=ui_theme.GOLD_SOFT,
                    ),
                    ft.Text(
                        screen.hotel_nombre or ui_theme.HOTEL_DEFAULT,
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color=ui_theme.WHITE,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        f"{screen.session.actor_label or 'Usuario'} · {screen.session.role}",
                        size=11,
                        color="#A8B3C4",
                    ),
                ],
            ),
        ),
        ft.Divider(height=1, color="#2A3F5F"),
    ]
    for group_label, secs in ADMIN_NAV_GROUPS:
        group_secs = [s for s in secs if s in visible_set]
        if not group_secs:
            continue
        items.append(
            ft.Container(
                padding=ft.Padding.only(left=12, right=12, top=10, bottom=4),
                content=ft.Text(
                    group_label.upper(),
                    size=10,
                    weight=ft.FontWeight.W_600,
                    color="#8B95A5",
                ),
            )
        )
        for s in group_secs:
            selected = screen.seccion == s
            icons = _SECCION_ICONS.get(s, (ft.Icons.CIRCLE_OUTLINED, ft.Icons.CIRCLE))
            items.append(
                ft.Container(
                    margin=ft.Margin.symmetric(horizontal=8, vertical=1),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                    border_radius=ui_theme.RADIUS_SM,
                    bgcolor=ui_theme.TEAL if selected else None,
                    ink=True,
                    on_click=lambda _e, sec=s: on_seccion(sec),
                    content=ft.Row(
                        spacing=10,
                        controls=[
                            ft.Icon(
                                icons[1] if selected else icons[0],
                                size=ui_theme.ICON_SM,
                                color=ui_theme.WHITE if selected else "#C5CCD6",
                            ),
                            ft.Text(
                                ADMIN_SECCION_LABEL.get(s, s),
                                size=13,
                                weight=ft.FontWeight.W_600 if selected else None,
                                color=ui_theme.WHITE if selected else "#E2E6EC",
                                expand=True,
                            ),
                        ],
                    ),
                )
            )

    return ft.Container(
        width=ui_theme.SIDEBAR_WIDTH,
        bgcolor=ui_theme.NAVY,
        border=ft.Border(right=ft.BorderSide(1, ui_theme.NAVY_LIGHT)),
        content=ft.Column(
            expand=True,
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            controls=items,
        ),
    )


def _pending_box(
    screen: AdminScreenVM,
    *,
    on_confirmar: Callable[[], None],
    on_cancelar: Callable[[], None],
) -> ft.Control:
    if not screen.pending:
        return ft.Container()
    return ft.Container(
        bgcolor=ui_theme.WARNING_BG,
        padding=ui_theme.SPACE_MD,
        border_radius=ui_theme.RADIUS_MD,
        border=ft.Border.all(1, ui_theme.WARNING),
        content=ft.Column(
            spacing=ui_theme.SPACE_SM,
            controls=[
                ft.Text(
                    "Resumen del cambio",
                    weight=ft.FontWeight.BOLD,
                    color=ui_theme.WARNING,
                ),
                ft.Text(screen.pending.resumen, size=13, color=ui_theme.DARK_TEXT),
                ft.Row(
                    controls=[
                        ui.primary_button(
                            "Confirmar",
                            on_confirmar,
                            disabled=screen.mutando,
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


def _panel_for_seccion(screen: AdminScreenVM, **cbs) -> ft.Control:
    sec = screen.seccion
    if sec == "analisis":
        return _panel_analisis(screen, **cbs)
    if sec == "productos":
        return _panel_productos(screen, **cbs)
    if sec == "recetas":
        return _panel_recetas(screen, **cbs)
    if sec == "usuarios":
        return _panel_usuarios(screen, **cbs)
    if sec == "responsables":
        return _panel_responsables(screen, **cbs)
    if sec == "catalogos":
        return _panel_catalogos(screen, **cbs)
    if sec == "proveedores":
        return _panel_proveedores(screen, **cbs)
    if sec == "compras":
        return _panel_compras(screen, **cbs)
    if sec == "documentos":
        return _panel_documentos(screen, **cbs)
    if sec == "inventario_inicial":
        return _panel_inventario(screen, **cbs)
    if sec == "actividad":
        return _panel_actividad(screen)
    if sec == "backup":
        return _panel_backup(screen, **cbs)
    if sec == "configuracion":
        return _panel_config(screen, **cbs)
    if sec == "servidor":
        return _panel_servidor(screen, **cbs)
    if sec == "zona_peligro":
        return _panel_zona_peligro(screen, **cbs)
    return _panel_inicio(screen, **cbs)


def _chip_row(
    labels: tuple[str, ...] | list[str],
    selected: str,
    on_select: Callable[[str], None] | None,
) -> ft.Control:
    return ft.Row(
        spacing=6,
        wrap=True,
        controls=[
            ft.FilledButton(
                lab,
                on_click=(lambda _e, v=lab: on_select(v) if on_select else None),
            )
            if lab == selected
            else ft.OutlinedButton(
                lab,
                on_click=(lambda _e, v=lab: on_select(v) if on_select else None),
            )
            for lab in labels
        ],
    )


def _panel_analisis(screen: AdminScreenVM, **cbs) -> ft.Control:
    panel: AnalisisPanelVM | None = screen.analisis
    if panel is None or not panel.puede_consultar:
        return ft.Column(
            spacing=ui_theme.SPACE_MD,
            controls=[
                ui.page_header("Análisis", "Costes, consumo y merma"),
                ui.alert_banner(
                    (panel.aviso if panel else None)
                    or "Sin permiso para consultar costes.",
                    severity="error",
                ),
            ],
        )

    return _panel_analisis_body(screen, panel, **cbs)


def _panel_analisis_body(
    screen: AdminScreenVM, panel: AnalisisPanelVM, **cbs
) -> ft.Control:
    hub_id = panel.hub
    hub_labels = [ANALISIS_HUB_LABEL[h] for h in ANALISIS_HUBS]
    pestanas = {
        "costes": COSTES_PESTANAS,
        "consumo": CONSUMO_PESTANAS,
        "merma": MERMA_PESTANAS,
    }.get(hub_id, COSTES_PESTANAS)

    # Labels cortos + hint: evita solape del floating label con el borde de la card.
    desde_tf = ft.TextField(
        label="Desde",
        hint_text="AAAA-MM-DD",
        value=panel.desde,
        expand=True,
        dense=True,
    )
    hasta_tf = ft.TextField(
        label="Hasta",
        hint_text="AAAA-MM-DD",
        value=panel.hasta,
        expand=True,
        dense=True,
    )

    controls: list[ft.Control] = [
        ui.page_header(
            "Análisis",
            "Costes, consumo y merma · gráficos nativos (sin BI)",
            actions=[
                ui.status_chip(ANALISIS_HUB_LABEL.get(hub_id, hub_id), tone="info"),
                ui.status_chip(panel.pestana, tone="neutral"),
            ],
        ),
        ui.card_surface(
            ft.Column(
                spacing=ui_theme.SPACE_MD,
                tight=True,
                controls=[
                    _chip_row(
                        hub_labels,
                        ANALISIS_HUB_LABEL.get(hub_id, "Costes"),
                        lambda lab: (cbs.get("on_analisis_hub") or (lambda _x: None))(
                            next(h for h, l in ANALISIS_HUB_LABEL.items() if l == lab)
                        ),
                    ),
                    ft.Container(
                        padding=ft.Padding.only(top=6),
                        content=ft.Row(
                            spacing=ui_theme.SPACE_MD,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                desde_tf,
                                hasta_tf,
                                ui.primary_button(
                                    "Aplicar periodo",
                                    lambda: (
                                        cbs.get("on_analisis_periodo")
                                        or (lambda a, b: None)
                                    )(
                                        desde_tf.value or "",
                                        hasta_tf.value or "",
                                    ),
                                    icon=ft.Icons.DATE_RANGE,
                                ),
                            ],
                        ),
                    ),
                ],
            ),
            title="Periodo y hub",
            padding=ui_theme.SPACE_LG,
        ),
    ]

    if panel.aviso:
        controls.append(ui.alert_banner(panel.aviso, severity="warning"))

    filters: list[ft.Control] = [
        _chip_row(
            list(pestanas),
            panel.pestana,
            cbs.get("on_analisis_pestana"),
        )
    ]

    if hub_id == "consumo":
        busq = ft.TextField(
            label="Buscador",
            value=panel.busqueda,
            expand=True,
            on_submit=lambda e: (cbs.get("on_analisis_busqueda") or (lambda _t: None))(
                e.control.value or ""
            ),
        )
        tipo_dd = ft.Dropdown(
            label="Tipo",
            width=180,
            value=panel.tipo_filtro,
            options=[ft.DropdownOption(key=t, text=t) for t in CONSUMO_TIPOS],
            on_select=lambda e: (cbs.get("on_analisis_tipo") or (lambda _t: None))(
                getattr(e.control, "value", None) or "Todos"
            ),
        )
        filters.append(
            ft.Row(
                controls=[
                    busq,
                    ui.secondary_button(
                        "Filtrar",
                        lambda: (cbs.get("on_analisis_busqueda") or (lambda _t: None))(
                            busq.value or ""
                        ),
                        icon=ft.Icons.SEARCH,
                    ),
                    tipo_dd,
                ]
            )
        )

    subtabs: list[str] = []
    if hub_id == "costes" and panel.pestana == "Desayuno":
        subtabs = ["Recetas", "Extras", "Bebidas en desayuno"]
    elif hub_id == "costes" and panel.pestana in ("Comida", "Cena"):
        subtabs = ["Recetas", "Productos y extras", "Bebidas"]
    elif hub_id == "costes" and panel.pestana == "Bebidas":
        subtabs = ["Todas", "Desayuno", "Comida", "Cena", "Registro independiente"]
    elif hub_id == "consumo" and panel.pestana == "Desayuno":
        subtabs = ["Recetas", "Extras", "Bebidas en desayuno"]
    elif hub_id == "consumo" and panel.pestana in ("Comida", "Cena"):
        subtabs = ["Recetas", "Productos y extras", "Bebidas"]
    elif hub_id == "consumo" and panel.pestana == "Bebidas":
        subtabs = ["Todas", "Desayuno", "Comida", "Cena", "Registro independiente"]
    if subtabs:
        filters.append(
            _chip_row(
                subtabs,
                panel.subtab if panel.subtab in subtabs else subtabs[0],
                cbs.get("on_analisis_subtab"),
            )
        )

    controls.append(ui.card_surface(*filters, title="Vista"))

    if panel.metrics:
        metric_cards: list[ft.Control] = []
        for m in panel.metrics:
            accent = {
                "ok": ui_theme.SUCCESS,
                "warn": ui_theme.WARNING,
                "danger": ui_theme.DANGER,
                "neutral": ui_theme.NAVY,
            }.get(m.tone or "neutral", ui_theme.NAVY)
            detalle = m.detalle or ""
            if m.delta_pct is not None:
                chip = ui.status_chip(
                    f"{m.delta_pct:+.1f}%",
                    tone={
                        "ok": "ok",
                        "warn": "warn",
                        "danger": "danger",
                        "neutral": "neutral",
                    }.get(m.tone or "neutral", "neutral"),
                )
                metric_cards.append(
                    ft.Column(
                        spacing=4,
                        tight=True,
                        controls=[
                            ui.metric_card(m.etiqueta, m.valor, detalle, accent=accent),
                            chip,
                        ],
                    )
                )
            else:
                metric_cards.append(
                    ui.metric_card(m.etiqueta, m.valor, detalle, accent=accent)
                )
        controls.append(
            ft.Row(spacing=ui_theme.SPACE_SM, wrap=True, controls=metric_cards)
        )

    if panel.alertas:
        for al in panel.alertas:
            sev_map = {"info": "info", "warning": "warning", "danger": "error"}
            sev = sev_map.get(al.severity, "warning")
            controls.append(
                ui.alert_banner(f"{al.titulo}: {al.mensaje}", severity=sev)
            )

    chart_blocks: list[ft.Control] = []
    donut_row: list[ft.Control] = []
    for titulo, items in panel.chart_donuts:
        donut_row.append(
            ft.Container(
                content=build_donut(items, titulo=titulo),
                width=340,
                padding=ft.Padding.only(right=12, bottom=8),
            )
        )
    if donut_row:
        chart_blocks.append(
            ft.Row(
                wrap=True,
                spacing=8,
                run_spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=donut_row,
            )
        )

    for titulo, items in panel.chart_barras:
        chart_blocks.append(build_barras_horizontales(items, titulo=titulo))
    for ch in panel.chart_lineas:
        chart_blocks.append(build_lineas_series(ch))
    if chart_blocks:
        controls.append(ui.card_surface(*chart_blocks, title="Composición y evolución"))

    if panel.pareto:
        pareto_rows: list[ft.Control] = [
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                bgcolor=ui_theme.LIGHT_GRAY,
                content=ft.Row(
                    controls=[
                        ft.Text("Producto", size=11, weight=ft.FontWeight.W_600, expand=True),
                        ft.Text("Coste", size=11, weight=ft.FontWeight.W_600, width=90),
                        ft.Text("%", size=11, weight=ft.FontWeight.W_600, width=50),
                        ft.Text("Acum.", size=11, weight=ft.FontWeight.W_600, width=60),
                    ]
                ),
            )
        ]
        for pr in panel.pareto:
            bar_w = max(4.0, 180.0 * min(pr.pct_acum, 100.0) / 100.0)
            pareto_rows.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                    border=ft.Border(bottom=ft.BorderSide(1, ui_theme.BORDER)),
                    content=ft.Column(
                        spacing=4,
                        tight=True,
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(
                                        pr.nombre,
                                        size=13,
                                        weight=ft.FontWeight.W_600,
                                        expand=True,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    ft.Text(pr.coste_fmt, size=12, width=90),
                                    ft.Text(f"{pr.pct:.1f}", size=12, width=50),
                                    ft.Text(f"{pr.pct_acum:.1f}%", size=12, width=60),
                                ]
                            ),
                            ft.Container(
                                width=bar_w,
                                height=8,
                                bgcolor=ui_theme.TEAL,
                                border_radius=3,
                            ),
                        ],
                    ),
                )
            )
        controls.append(
            ui.card_surface(*pareto_rows, title="Pareto — drivers de coste (~80%)")
        )

    if (
        not panel.rankings
        and not panel.metrics
        and not chart_blocks
        and not panel.pareto
        and not panel.alertas
    ):
        controls.append(
            ui.empty_state(
                "Sin datos en el periodo",
                "Ajuste fechas o cambie de pestaña para ver métricas y rankings.",
            )
        )

    for block in panel.rankings:
        if not block.filas:
            ranking_body: list[ft.Control] = [
                ui.empty_state("Sin filas", "No hay elementos en este ranking.")
            ]
        else:
            ranking_body = []
            for row in block.filas:
                detalle_parts = [row.coste_fmt]
                if row.cantidad_fmt:
                    detalle_parts.append(row.cantidad_fmt)
                if row.usos != "":
                    detalle_parts.append(f"usos {row.usos}")
                if row.tipo:
                    detalle_parts.append(row.tipo)
                ranking_body.append(
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                        border=ft.Border(
                            bottom=ft.BorderSide(1, ui_theme.BORDER)
                        ),
                        content=ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Text(
                                    row.nombre,
                                    size=13,
                                    weight=ft.FontWeight.W_600,
                                    color=ui_theme.DARK_TEXT,
                                    expand=True,
                                ),
                                ft.Text(
                                    " · ".join(detalle_parts),
                                    size=12,
                                    color=ui_theme.MID_GRAY,
                                ),
                            ],
                        ),
                    )
                )
        controls.append(ui.card_surface(*ranking_body, title=block.titulo))

    if hub_id == "costes" and panel.pestana == "Resumen":
        a_d = ft.TextField(label="A desde", value=panel.cmp_a_desde, width=130)
        a_h = ft.TextField(label="A hasta", value=panel.cmp_a_hasta, width=130)
        b_d = ft.TextField(label="B desde", value=panel.cmp_b_desde, width=130)
        b_h = ft.TextField(label="B hasta", value=panel.cmp_b_hasta, width=130)
        cmp_controls: list[ft.Control] = [
            ft.Row(
                wrap=True,
                spacing=ui_theme.SPACE_SM,
                controls=[
                    a_d,
                    a_h,
                    b_d,
                    b_h,
                    ui.primary_button(
                        "Comparar",
                        lambda: (
                            cbs.get("on_analisis_comparacion") or (lambda *a: None)
                        )(
                            a_d.value or "",
                            a_h.value or "",
                            b_d.value or "",
                            b_h.value or "",
                        ),
                        icon=ft.Icons.COMPARE_ARROWS,
                    ),
                    ui.secondary_button(
                        "Exportar Excel",
                        lambda: (cbs.get("on_analisis_export") or (lambda: None))(),
                        icon=ft.Icons.DOWNLOAD,
                    ),
                ],
            )
        ]
        if panel.cmp_metrics:
            cmp_controls.append(
                ft.Row(
                    wrap=True,
                    spacing=ui_theme.SPACE_SM,
                    controls=[
                        ui.metric_card(m.etiqueta, m.valor, m.detalle, width=160)
                        for m in panel.cmp_metrics
                    ],
                )
            )
        if panel.cmp_barras:
            cmp_controls.append(
                build_barras_agrupadas(panel.cmp_barras, titulo="Comparación A/B")
            )
        if panel.export_mensaje:
            cmp_controls.append(
                ui.alert_banner(panel.export_mensaje, severity="success")
            )
        controls.append(
            ui.card_surface(*cmp_controls, title="Comparación Periodo A / B")
        )

    # Spacer inferior: el último bloque no queda pegado al borde / clip.
    controls.append(ft.Container(height=32))
    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        tight=True,
        controls=controls,
    )


def _panel_inicio(screen: AdminScreenVM, **cbs) -> ft.Control:
    on_refresh = cbs.get("on_refresh_datos")
    on_seccion = cbs.get("on_seccion")
    dash = screen.dashboard

    def _go(sec: str) -> None:
        if on_seccion:
            on_seccion(sec)

    hotel = screen.hotel_nombre or ui_theme.HOTEL_DEFAULT
    periodo = dash.periodo_label if dash else (screen.periodo or "—")
    saludo = dash.saludo if dash else f"Buenas, {screen.session.actor_label or 'Usuario'}"

    controls: list[ft.Control] = [
        ui.page_header(
            hotel,
            f"{saludo} · {periodo}",
            actions=[
                ui.status_chip(f"Rev. {screen.revision}", tone="neutral"),
                ui.primary_button(
                    "Actualizar",
                    lambda: on_refresh() if on_refresh else None,
                    icon=ft.Icons.REFRESH,
                    disabled=screen.mutando or on_refresh is None,
                ),
            ],
        ),
        ui.card_surface(
            ft.Row(
                wrap=True,
                spacing=ui_theme.SPACE_SM,
                controls=[
                    ui.status_chip(
                        f"Datos: {screen.data_path_label or '—'}",
                        tone="info",
                    ),
                    ui.status_chip(
                        f"Shared: {screen.shared_root_label or '—'}",
                        tone="neutral",
                    ),
                    ui.status_chip(f"{screen.productos_total} productos", tone="neutral"),
                    ui.status_chip(f"{len(screen.recetas)} recetas", tone="neutral"),
                ],
            ),
            title="Instancia",
        ),
    ]

    if screen.dashboard_error:
        controls.append(ui.alert_banner(screen.dashboard_error, severity="warning"))
    if dash and dash.aviso:
        controls.append(ui.alert_banner(dash.aviso, severity="info"))

    alertas = list(dash.alertas) if dash and dash.alertas else []
    if alertas:
        for a in alertas[:3]:
            controls.append(
                ft.Container(
                    ink=bool(a.destino),
                    on_click=(lambda _e, d=a.destino: _go(d) if d else None),
                    content=ui.alert_banner(
                        f"{a.titulo} — {a.detalle}",
                        severity=a.severidad,
                    ),
                )
            )
        if len(alertas) > 3:
            controls.append(
                ui_theme.text_help(f"+{len(alertas) - 3} alertas más en Análisis / Inventario")
            )
    else:
        falta = "falta" in (screen.alerta_registro or "").casefold()
        controls.append(
            ui.alert_banner(
                screen.alerta_registro or "Sin alertas operativas.",
                severity="warning" if falta else "success",
            )
        )

    controls.append(ui.section_header("Pulso operativo", "Conteos del periodo"))
    controls.append(
        ft.Row(
            spacing=ui_theme.SPACE_MD,
            wrap=True,
            controls=[
                ui.metric_card(
                    "Consumos",
                    str(screen.consumo_count),
                    "Abrir análisis",
                    accent=ui_theme.NAVY,
                    on_click=lambda: _go("analisis"),
                ),
                ui.metric_card(
                    "Mermas",
                    str(screen.merma_count),
                    "Abrir análisis",
                    accent=ui_theme.DANGER,
                    on_click=lambda: _go("analisis"),
                ),
                ui.metric_card(
                    "Stock bajo",
                    str(screen.stock_bajo),
                    "Ver productos",
                    accent=ui_theme.WARNING,
                    on_click=lambda: _go("productos"),
                ),
                ui.metric_card(
                    "Caducidades",
                    str(screen.caducidades),
                    "Inventario inicial",
                    accent=ui_theme.DANGER,
                    on_click=lambda: _go("inventario_inicial"),
                ),
            ],
        )
    )

    if dash and dash.puede_ver_economia and dash.metrics:
        controls.append(
            ui.section_header("Resumen económico", "Costes del periodo (permiso CONSULTAR_COSTES)")
        )
        controls.append(
            ft.Row(
                spacing=ui_theme.SPACE_MD,
                wrap=True,
                controls=[
                    ui.metric_card(m.etiqueta, m.valor, m.detalle, accent=ui_theme.NAVY)
                    for m in dash.metrics
                ],
            )
        )

    if dash and dash.por_servicio:
        controls.append(ui.section_header("Coste por servicio"))
        controls.append(
            ft.Row(
                spacing=ui_theme.SPACE_MD,
                wrap=True,
                controls=[
                    ui.metric_card(
                        m.etiqueta,
                        m.valor,
                        m.detalle,
                        accent=ui_theme.TEAL,
                        width=170,
                    )
                    for m in dash.por_servicio
                ],
            )
        )

    charts: list[ft.Control] = []
    if dash and dash.chart_naturaleza:
        charts.append(
            build_barras_horizontales(dash.chart_naturaleza, titulo="Naturaleza del coste")
        )
    if dash and dash.chart_evolucion:
        charts.append(build_lineas_series(dash.chart_evolucion))
    if charts:
        controls.append(ui.card_surface(*charts, title="Evolución"))

    if dash and dash.rankings:
        controls.append(ui.section_header("Rankings", "Top del periodo"))
        rank_cols: list[ft.Control] = []
        for block in dash.rankings:
            filas: list[ft.Control] = [
                ft.Text(block.titulo, size=13, weight=ft.FontWeight.W_600),
            ]
            if not block.filas:
                filas.append(ui_theme.text_help("Sin filas."))
            else:
                for row in block.filas[:6]:
                    line = row.nombre
                    if row.coste_fmt:
                        line += f" · {row.coste_fmt}"
                    if row.cantidad_fmt:
                        line += f" · {row.cantidad_fmt}"
                    filas.append(ft.Text(line, size=12, color=ui_theme.DARK_TEXT))
            rank_cols.append(
                ft.Container(
                    width=260,
                    padding=ui_theme.SPACE_MD,
                    bgcolor=ui_theme.SURFACE_CARD,
                    border_radius=ui_theme.RADIUS_MD,
                    border=ft.Border.all(1, ui_theme.BORDER),
                    content=ft.Column(spacing=4, tight=True, controls=filas),
                )
            )
        controls.append(ft.Row(spacing=ui_theme.SPACE_MD, wrap=True, controls=rank_cols))

    if screen.stock_bajo_nombres:
        controls.append(
            ui.card_surface(
                *[
                    ft.Text(f"· {n}", size=12, color=ui_theme.DARK_TEXT)
                    for n in screen.stock_bajo_nombres
                ],
                title="Stock bajo (top 5)",
            )
        )

    # Actividad reciente (ya en VM)
    act_rows: list[ft.Control] = []
    for a in screen.actividades[:5]:
        act_rows.append(
            ft.Container(
                padding=ft.Padding.symmetric(vertical=6),
                border=ft.Border(bottom=ft.BorderSide(1, ui_theme.BORDER)),
                content=ft.Row(
                    controls=[
                        ft.Column(
                            spacing=1,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(
                                    a.accion,
                                    size=12,
                                    weight=ft.FontWeight.W_600,
                                    color=ui_theme.DARK_TEXT,
                                ),
                                ft.Text(
                                    a.detalle or "—",
                                    size=11,
                                    color=ui_theme.MID_GRAY,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                        ),
                        ft.Text(a.fecha, size=11, color=ui_theme.MID_GRAY, width=140),
                    ]
                ),
            )
        )
    if not act_rows:
        act_rows = [ui_theme.text_help("Sin actividad reciente.")]
    controls.append(
        ui.card_surface(
            *act_rows,
            ui.secondary_button(
                "Ver actividad completa",
                lambda: _go("actividad"),
                icon=ft.Icons.HISTORY,
            ),
            title="Últimos movimientos",
        )
    )

    controls.append(
        ft.Row(
            spacing=ui_theme.SPACE_SM,
            wrap=True,
            controls=[
                ui.secondary_button("Productos", lambda: _go("productos"), icon=ft.Icons.INVENTORY_2),
                ui.secondary_button("Compras", lambda: _go("compras"), icon=ft.Icons.SHOPPING_CART),
                ui.secondary_button("Análisis", lambda: _go("analisis"), icon=ft.Icons.ANALYTICS),
                ui.secondary_button(
                    "Inventario", lambda: _go("inventario_inicial"), icon=ft.Icons.ADD_BOX
                ),
                ui.secondary_button("Recetas", lambda: _go("recetas"), icon=ft.Icons.MENU_BOOK),
                ui.secondary_button("Documentos", lambda: _go("documentos"), icon=ft.Icons.DESCRIPTION),
            ],
        )
    )
    return ft.Column(spacing=ui_theme.SPACE_MD, controls=controls)


def _filtro_row(screen: AdminScreenVM, on_filtro: Callable[[str], None]) -> ft.Control:
    filtro_tf = ft.TextField(
        label="Buscar",
        value=screen.filtro,
        prefix_icon=ft.Icons.SEARCH,
        on_submit=lambda e: on_filtro(e.control.value or ""),
        expand=True,
    )
    return ft.Row(
        controls=[
            filtro_tf,
            ft.OutlinedButton("Filtrar", on_click=lambda _e: on_filtro(filtro_tf.value or "")),
        ]
    )


def _panel_productos(screen: AdminScreenVM, **cbs) -> ft.Control:
    on_filtro = cbs["on_filtro"]
    on_crear = cbs["on_crear_producto"]
    on_des = cbs["on_desactivar_producto"]
    on_rea = cbs["on_reactivar_producto"]
    on_import = cbs.get("on_importar_productos")
    on_page = cbs.get("on_productos_page")
    nombre = ft.TextField(label="Nombre", dense=True, expand=True)
    codigo = ft.TextField(label="Código", dense=True, width=120)
    unidad = ft.Dropdown(
        label="Unidad",
        width=110,
        dense=True,
        options=[ft.dropdown.Option(u) for u in screen.unidades],
        value=screen.unidades[0] if screen.unidades else None,
    )
    stock = ft.TextField(label="Stock mín.", dense=True, width=100, value="0")
    tipo = ft.Dropdown(
        label="Tipo",
        width=140,
        dense=True,
        options=[ft.dropdown.Option(t) for t in screen.tipos_articulo],
        value="consumible" if "consumible" in screen.tipos_articulo else None,
    )
    es_bebida = ft.Checkbox(label="Bebida", value=False)
    servicios = ft.TextField(
        label="Servicios (coma)",
        hint_text="desayuno,comida,cena,bebidas",
        dense=True,
        expand=True,
    )

    def _crear(_e=None) -> None:
        try:
            sm = float((stock.value or "0").replace(",", "."))
        except ValueError:
            sm = None
        serv = [s.strip() for s in (servicios.value or "").split(",") if s.strip()]
        on_crear(
            nombre.value or "",
            unidad.value or "",
            sm,
            codigo.value or "",
            tipo.value or "",
            bool(es_bebida.value),
            serv,
        )

    alta = ft.ExpansionTile(
        title=ft.Text("Nuevo producto", weight=ft.FontWeight.W_600),
        subtitle=ft.Text("Alta manual o importación Excel PRECIO", size=12),
        expanded=False,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=8, right=8, bottom=12),
                content=ft.Column(
                    spacing=ui_theme.SPACE_SM,
                    controls=[
                        ui.section_header("Identificación"),
                        ft.Row(controls=[nombre, codigo]),
                        ui.section_header("Clasificación e inventario"),
                        ft.Row(controls=[unidad, stock, tipo, es_bebida]),
                        ft.Row(
                            controls=[
                                servicios,
                                ui.primary_button(
                                    "Crear producto",
                                    lambda: _crear(),
                                    icon=ft.Icons.ADD,
                                    disabled=screen.mutando,
                                ),
                            ]
                        ),
                        ft.Divider(height=1, color=ui_theme.BORDER),
                        ft.Row(
                            wrap=True,
                            controls=[
                                ui_theme.text_help(
                                    "Importar Productos PRECIO.xlsx (unidad + coste aproximado)."
                                ),
                                ui.secondary_button(
                                    "Importar Excel",
                                    lambda: on_import() if on_import else None,
                                    icon=ft.Icons.UPLOAD_FILE,
                                    disabled=screen.mutando or on_import is None,
                                ),
                            ],
                        ),
                    ],
                ),
            )
        ],
    )

    total = screen.productos_total
    page = screen.productos_page
    size = screen.productos_page_size or 40
    start = page * size + 1 if total else 0
    end = min(total, (page + 1) * size)
    max_page = max(0, (total - 1) // size) if total else 0

    lista = [
        _producto_row(p, screen.mutando or screen.pending is not None, on_des, on_rea)
        for p in screen.productos
    ]
    if not lista:
        lista = [ui.empty_state("Sin productos", "Cree uno o importe el Excel PRECIO.")]

    # Cabecera de tabla
    header = ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        bgcolor=ui_theme.LIGHT_GRAY,
        content=ft.Row(
            controls=[
                ft.Text("Producto", size=11, weight=ft.FontWeight.W_600, expand=True),
                ft.Text("Unidad", size=11, weight=ft.FontWeight.W_600, width=70),
                ft.Text("Mín.", size=11, weight=ft.FontWeight.W_600, width=60),
                ft.Text("Estado", size=11, weight=ft.FontWeight.W_600, width=80),
                ft.Text("Acciones", size=11, weight=ft.FontWeight.W_600, width=100),
            ]
        ),
    )

    pager = ft.Row(
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        controls=[
            ui.status_chip(f"{start}–{end} de {total}", tone="info"),
            ft.Row(
                spacing=4,
                controls=[
                    ft.IconButton(
                        icon=ft.Icons.CHEVRON_LEFT,
                        disabled=page <= 0 or on_page is None,
                        on_click=lambda _e: on_page(page - 1) if on_page else None,
                    ),
                    ft.Text(f"{page + 1} / {max_page + 1}", size=12),
                    ft.IconButton(
                        icon=ft.Icons.CHEVRON_RIGHT,
                        disabled=page >= max_page or on_page is None,
                        on_click=lambda _e: on_page(page + 1) if on_page else None,
                    ),
                ],
            ),
        ],
    )

    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        controls=[
            ui.page_header(
                "Productos",
                "Catálogo operativo · búsqueda, paginación e importación",
            ),
            alta,
            _filtro_row(screen, on_filtro),
            pager,
            ft.Container(
                bgcolor=ui_theme.SURFACE_CARD,
                border_radius=ui_theme.RADIUS_MD,
                border=ft.Border.all(1, ui_theme.BORDER),
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                content=ft.Column(spacing=0, controls=[header, *lista]),
            ),
        ],
    )


def _producto_row(
    p: ProductoAdminVM,
    disabled: bool,
    on_des: Callable[[str], None],
    on_rea: Callable[[str], None],
) -> ft.Control:
    acciones = []
    if p.activo:
        acciones.append(
            ft.TextButton(
                "Desactivar",
                disabled=disabled,
                style=ft.ButtonStyle(color=ui_theme.DANGER),
                on_click=lambda _e, pid=p.id: on_des(pid),
            )
        )
    else:
        acciones.append(
            ft.TextButton(
                "Reactivar",
                disabled=disabled,
                on_click=lambda _e, pid=p.id: on_rea(pid),
            )
        )
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border=ft.Border(bottom=ft.BorderSide(1, ui_theme.BORDER)),
        bgcolor=None if p.activo else ui_theme.LIGHT_GRAY,
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    spacing=2,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Text(
                            p.nombre,
                            weight=ft.FontWeight.W_600,
                            size=13,
                            color=ui_theme.DARK_TEXT,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            f"{p.codigo or 'sin código'} · {p.tipo_articulo or '—'}"
                            + (" · bebida" if p.es_bebida else ""),
                            size=11,
                            color=ui_theme.MID_GRAY,
                        ),
                    ],
                ),
                ft.Text(p.unidad, size=12, width=70, color=ui_theme.DARK_TEXT),
                ft.Text(f"{p.stock_minimo:g}", size=12, width=60, color=ui_theme.DARK_TEXT),
                ft.Container(
                    width=80,
                    content=ui.status_chip(
                        "Activo" if p.activo else "Inactivo",
                        tone="ok" if p.activo else "neutral",
                    ),
                ),
                ft.Container(width=100, content=ft.Row(spacing=0, tight=True, controls=acciones)),
            ],
        ),
    )


def _panel_recetas(screen: AdminScreenVM, **cbs) -> ft.Control:
    on_filtro = cbs["on_filtro"]
    on_crear = cbs["on_crear_receta"]
    on_guardar = cbs["on_editar_receta"]
    on_iniciar = cbs["on_iniciar_edicion_receta"]
    on_cancelar = cbs["on_cancelar_edicion_receta"]
    on_elim = cbs["on_eliminar_receta"]
    edit_id = (screen.receta_edit_id or "").strip()
    editando = next((r for r in screen.recetas if r.id == edit_id), None)

    nombre = ft.TextField(
        label="Nombre receta",
        expand=True,
        value=editando.nombre if editando else "",
    )
    categoria = ft.Dropdown(
        label="Categoría",
        width=160,
        options=[ft.dropdown.Option(c) for c in screen.categorias_receta],
        value=(
            editando.categoria
            if editando
            else (screen.categorias_receta[0] if screen.categorias_receta else None)
        ),
    )
    porciones = ft.TextField(
        label="Porciones",
        width=110,
        value=(
            f"{editando.porciones_estandar:g}"
            if editando and editando.porciones_estandar is not None
            else "1"
        ),
    )
    prod_opts = [
        ft.dropdown.Option(key=p.id, text=p.nombre)
        for p in screen.productos
        if p.activo
    ]
    ing_prod = ft.Dropdown(label="Producto", options=prod_opts, expand=True)
    ing_cant = ft.TextField(label="Cantidad", width=110, value="1")
    extra_prod = ft.Dropdown(label="Extra (producto)", options=prod_opts, expand=True)
    extra_cant = ft.TextField(label="Cant. extra", width=110, value="1")
    servicios = ft.TextField(
        label="Servicios (coma)",
        hint_text="Vacío = mismo que la categoría (desayuno/comida/…)",
        expand=True,
        value=", ".join(editando.servicios) if editando else "",
    )
    pendientes: list[tuple[str, str, float]] = []
    extras_pend: list[tuple[str, str, float]] = []
    if editando:
        for ln in editando.ingredientes:
            pendientes.append((ln.producto_id, ln.producto_nombre, ln.cantidad))
        for ln in editando.extras:
            extras_pend.append((ln.producto_id, ln.producto_nombre, ln.cantidad))
    ings_col = ft.Column(spacing=4, tight=True)
    extras_col = ft.Column(spacing=4, tight=True)
    ings_hint = ft.Text(
        "Añada uno o más ingredientes.",
        size=12,
        color=ui_theme.MID_GRAY,
        italic=True,
    )
    extras_hint = ft.Text(
        "Opcional: extras ofrecidos en terminal (huevo, cherry…).",
        size=12,
        color=ui_theme.MID_GRAY,
        italic=True,
    )

    def _paint_ings() -> None:
        if not pendientes:
            ings_col.controls = [ings_hint]
        else:
            rows: list[ft.Control] = []
            for i, (pid, pnombre, cant) in enumerate(pendientes):
                rows.append(
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                        bgcolor=ui_theme.LIGHT_GRAY,
                        border_radius=ui_theme.RADIUS_SM,
                        content=ft.Row(
                            controls=[
                                ft.Text(f"{pnombre} · {cant:g}", expand=True, size=12),
                                ft.IconButton(
                                    icon=ft.Icons.CLOSE,
                                    icon_size=16,
                                    tooltip="Quitar",
                                    on_click=lambda _e, idx=i: _quitar(idx),
                                ),
                            ]
                        ),
                    )
                )
            ings_col.controls = rows
        try:
            ings_col.update()
        except Exception:  # noqa: BLE001 — aún no montado
            pass

    def _paint_extras() -> None:
        if not extras_pend:
            extras_col.controls = [extras_hint]
        else:
            rows: list[ft.Control] = []
            for i, (pid, pnombre, cant) in enumerate(extras_pend):
                rows.append(
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                        bgcolor=ui_theme.LIGHT_GRAY,
                        border_radius=ui_theme.RADIUS_SM,
                        content=ft.Row(
                            controls=[
                                ft.Text(
                                    f"Extra {pnombre} · {cant:g}",
                                    expand=True,
                                    size=12,
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.CLOSE,
                                    icon_size=16,
                                    tooltip="Quitar",
                                    on_click=lambda _e, idx=i: _quitar_extra(idx),
                                ),
                            ]
                        ),
                    )
                )
            extras_col.controls = rows
        try:
            extras_col.update()
        except Exception:  # noqa: BLE001
            pass

    def _quitar(idx: int) -> None:
        if 0 <= idx < len(pendientes):
            pendientes.pop(idx)
            _paint_ings()

    def _quitar_extra(idx: int) -> None:
        if 0 <= idx < len(extras_pend):
            extras_pend.pop(idx)
            _paint_extras()

    def _add_ing(_e=None) -> None:
        pid = ing_prod.value or ""
        try:
            cant = float((ing_cant.value or "0").replace(",", "."))
        except ValueError:
            cant = 0.0
        if not pid or cant <= 0:
            return
        label = next((p.nombre for p in screen.productos if p.id == pid), pid)
        for i, (opid, _, _) in enumerate(pendientes):
            if opid == pid:
                pendientes[i] = (pid, label, cant)
                _paint_ings()
                return
        pendientes.append((pid, label, cant))
        _paint_ings()

    def _add_extra(_e=None) -> None:
        pid = extra_prod.value or ""
        try:
            cant = float((extra_cant.value or "0").replace(",", "."))
        except ValueError:
            cant = 0.0
        if not pid or cant <= 0:
            return
        label = next((p.nombre for p in screen.productos if p.id == pid), pid)
        for i, (opid, _, _) in enumerate(extras_pend):
            if opid == pid:
                extras_pend[i] = (pid, label, cant)
                _paint_extras()
                return
        extras_pend.append((pid, label, cant))
        _paint_extras()

    def _payload() -> tuple[str, list[tuple[str, float]], str, float | None, list[str], list[tuple[str, float]]]:
        try:
            porc = float((porciones.value or "1").replace(",", "."))
        except ValueError:
            porc = None
        ings = [(pid, cant) for pid, _, cant in pendientes]
        if not ings:
            try:
                cant = float((ing_cant.value or "0").replace(",", "."))
            except ValueError:
                cant = 0.0
            pid = ing_prod.value or ""
            if pid and cant > 0:
                ings = [(pid, cant)]
        serv = [s.strip() for s in (servicios.value or "").split(",") if s.strip()]
        extras = [(pid, cant) for pid, _, cant in extras_pend]
        return nombre.value or "", ings, categoria.value or "", porc, serv, extras

    def _crear(_e=None) -> None:
        n, ings, cat, porc, serv, extras = _payload()
        on_crear(n, ings, cat, porc, serv, extras)

    def _guardar(_e=None) -> None:
        if not editando:
            return
        n, ings, cat, porc, serv, extras = _payload()
        on_guardar(editando.id, n, ings, cat, porc, serv, extras)

    _paint_ings()
    _paint_extras()

    form_controls: list[ft.Control] = [
        ft.Row(controls=[nombre, categoria, porciones]),
        servicios,
        ui.section_header("Ingredientes"),
        ft.Row(
            controls=[
                ing_prod,
                ing_cant,
                ui.secondary_button(
                    "Añadir",
                    lambda: _add_ing(),
                    icon=ft.Icons.ADD,
                    disabled=screen.mutando,
                ),
            ]
        ),
        ings_col,
        ui.section_header("Extras ofrecidos"),
        ft.Row(
            controls=[
                extra_prod,
                extra_cant,
                ui.secondary_button(
                    "Añadir extra",
                    lambda: _add_extra(),
                    icon=ft.Icons.ADD,
                    disabled=screen.mutando,
                ),
            ]
        ),
        extras_col,
    ]
    if editando:
        form_controls.append(
            ft.Row(
                controls=[
                    ui.primary_button(
                        "Guardar cambios",
                        lambda: _guardar(),
                        icon=ft.Icons.SAVE,
                        disabled=screen.mutando,
                    ),
                    ui.secondary_button(
                        "Cancelar",
                        lambda: on_cancelar(),
                        disabled=screen.mutando,
                    ),
                ]
            )
        )
        form_title = f"Editar: {editando.nombre}"
        form_sub = "Modifique ingredientes, extras o servicios y guarde"
    else:
        form_controls.append(
            ui.primary_button(
                "Crear receta",
                lambda: _crear(),
                icon=ft.Icons.RESTAURANT_MENU,
                disabled=screen.mutando,
            )
        )
        form_title = "Nueva receta"
        form_sub = "Ingredientes · extras · categoría = servicio por defecto"

    form_tile = ft.ExpansionTile(
        title=ft.Text(form_title, weight=ft.FontWeight.W_600),
        subtitle=ft.Text(form_sub, size=12),
        expanded=bool(editando),
        controls=[
            ft.Container(
                padding=8,
                content=ft.Column(spacing=ui_theme.SPACE_SM, controls=form_controls),
            )
        ],
    )

    lista = [
        _receta_row(
            r,
            screen.mutando or screen.pending is not None,
            on_iniciar,
            on_elim,
            editando_id=edit_id,
        )
        for r in screen.recetas
    ]

    return ft.Column(
        expand=True,
        spacing=ui_theme.SPACE_MD,
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ui.page_header(
                "Recetas",
                f"{len(screen.recetas)} recetas · editar · eliminar · valoración teórica",
            ),
            form_tile,
            _filtro_row(screen, on_filtro),
            (
                ft.Column(spacing=ui_theme.SPACE_SM, controls=lista)
                if lista
                else ui.empty_state("Sin recetas", "Cree la primera receta del servicio.")
            ),
        ],
    )


def _receta_row(
    r: RecetaAdminVM,
    disabled: bool,
    on_editar: Callable[[str], None],
    on_eliminar: Callable[[str], None],
    *,
    editando_id: str = "",
) -> ft.Control:
    acciones = [
        ft.TextButton(
            "Editando…" if r.id == editando_id else "Editar",
            disabled=disabled or r.id == editando_id,
            on_click=lambda _e, rid=r.id: on_editar(rid),
        ),
        ft.TextButton(
            "Eliminar",
            disabled=disabled,
            style=ft.ButtonStyle(color=ui_theme.DANGER),
            on_click=lambda _e, rid=r.id: on_eliminar(rid),
        ),
    ]
    meta = (
        f"{r.categoria} · {r.n_ingredientes} ing. · "
        f"porciones {r.porciones_estandar if r.porciones_estandar is not None else '—'}"
    )
    if getattr(r, "n_extras", 0):
        meta += f" · {r.n_extras} extras"
        if getattr(r, "extras_resumen", ""):
            meta += f" ({r.extras_resumen})"
    if r.servicios:
        meta += f" · {', '.join(r.servicios)}"
    valor_lines: list[ft.Control] = []
    if r.teorico_fmt:
        detalle = f"Total {r.teorico_fmt}"
        if r.por_racion_fmt:
            detalle += f" · ración {r.por_racion_fmt}"
        if not r.teorico_completo:
            detalle += " · incompleto"
        valor_lines.append(
            ft.Text(detalle, size=12, color=ui_theme.TEAL, weight=ft.FontWeight.W_500)
        )
    return ft.Container(
        bgcolor=ui_theme.SURFACE_CARD if r.activo else ui_theme.LIGHT_GRAY,
        padding=ui_theme.SPACE_MD,
        border_radius=ui_theme.RADIUS_MD,
        border=ft.Border.all(
            2 if r.id == editando_id else 1,
            ui_theme.TEAL if r.id == editando_id else ui_theme.BORDER,
        ),
        content=ft.Column(
            spacing=6,
            tight=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(
                            r.nombre,
                            weight=ft.FontWeight.BOLD,
                            size=14,
                            color=ui_theme.DARK_TEXT,
                            expand=True,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ui.status_chip(
                            "Activa" if r.activo else "Inactiva",
                            tone="ok" if r.activo else "neutral",
                        ),
                    ],
                ),
                ft.Text(meta, size=12, color=ui_theme.MID_GRAY),
                *valor_lines,
                ft.Row(controls=acciones),
            ],
        ),
    )


def _panel_usuarios(screen: AdminScreenVM, **cbs) -> ft.Control:
    if not screen.puede_gestionar_usuarios:
        return ft.Column(
            spacing=ui_theme.SPACE_MD,
            controls=[
                ui.page_header("Usuarios", "Gestión de acceso"),
                ui.alert_banner(
                    "Sin permiso GESTIONAR_USUARIOS.",
                    severity="error",
                ),
            ],
        )

    on_filtro = cbs["on_filtro"]
    on_crear = cbs["on_crear_usuario"]
    on_editar = cbs["on_editar_usuario"]
    on_rol = cbs["on_cambiar_rol"]
    on_des = cbs["on_desactivar_usuario"]
    on_rea = cbs["on_reactivar_usuario"]
    on_pwd = cbs["on_restablecer_password"]

    nombre = ft.TextField(label="Nombre", expand=True)
    login = ft.TextField(label="Login", width=140)
    password = ft.TextField(label="Contraseña", password=True, width=160)
    rol = ft.Dropdown(
        label="Rol",
        width=180,
        options=[ft.dropdown.Option(r) for r in screen.roles_asignables],
        value=screen.roles_asignables[1] if len(screen.roles_asignables) > 1 else None,
    )

    def _crear(_e=None) -> None:
        on_crear(nombre.value or "", rol.value or "", login.value or "", password.value or "")

    lista: list[ft.Control] = [
        _usuario_row(
            u,
            screen,
            on_editar=on_editar,
            on_rol=on_rol,
            on_des=on_des,
            on_rea=on_rea,
            on_pwd=on_pwd,
        )
        for u in screen.usuarios
    ]
    if not lista:
        lista = [
            ui.empty_state(
                "Sin usuarios",
                "Cree el primero o ajuste el filtro.",
            )
        ]

    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        controls=[
            ui.page_header(
                "Usuarios",
                "Alta, roles y estado de acceso",
                actions=[
                    ui.status_chip(f"{len(screen.usuarios)} en listado", tone="info"),
                ],
            ),
            ui.card_surface(
                ft.Row(controls=[nombre, login, password, rol]),
                ui.primary_button(
                    "Crear usuario",
                    lambda: _crear(),
                    icon=ft.Icons.PERSON_ADD,
                    disabled=screen.mutando,
                ),
                title="Nuevo usuario",
            ),
            _filtro_row(screen, on_filtro),
            ui.card_surface(*lista, title="Listado"),
        ],
    )


def _usuario_row(
    u: UsuarioAdminVM,
    screen: AdminScreenVM,
    *,
    on_editar: Callable[[str, str], None],
    on_rol: Callable[[str, str], None],
    on_des: Callable[[str], None],
    on_rea: Callable[[str], None],
    on_pwd: Callable[[str, str], None],
) -> ft.Control:
    disabled = screen.mutando or screen.pending is not None
    rename = ft.TextField(label="Nombre", value=u.nombre, width=200, disabled=disabled)
    rol_dd = ft.Dropdown(
        label="Rol",
        width=160,
        options=[ft.dropdown.Option(r) for r in screen.roles_asignables],
        value=u.rol if u.rol in screen.roles_asignables else None,
        disabled=disabled,
    )
    pwd = ft.TextField(label="Nueva contraseña", password=True, width=160, disabled=disabled)
    acciones: list[ft.Control] = [
        ui.secondary_button(
            "Renombrar",
            lambda uid=u.id, tf=rename: on_editar(uid, tf.value or ""),
            disabled=disabled,
        ),
        ui.secondary_button(
            "Rol",
            lambda uid=u.id, dd=rol_dd: on_rol(uid, dd.value or ""),
            disabled=disabled,
        ),
        ui.secondary_button(
            "Password",
            lambda uid=u.id, tf=pwd: on_pwd(uid, tf.value or ""),
            disabled=disabled,
        ),
    ]
    if u.activo:
        acciones.append(
            ft.TextButton(
                "Desactivar",
                disabled=disabled,
                style=ft.ButtonStyle(color=ui_theme.DANGER),
                on_click=lambda _e, uid=u.id: on_des(uid),
            )
        )
    else:
        acciones.append(
            ft.TextButton(
                "Reactivar",
                disabled=disabled,
                on_click=lambda _e, uid=u.id: on_rea(uid),
            )
        )
    return ft.Container(
        bgcolor=ui_theme.SURFACE_CARD if u.activo else ui_theme.LIGHT_GRAY,
        padding=ui_theme.SPACE_MD,
        border_radius=ui_theme.RADIUS_MD,
        border=ft.Border.all(1, ui_theme.BORDER),
        content=ft.Column(
            spacing=ui_theme.SPACE_SM,
            tight=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Column(
                            spacing=2,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(
                                    u.nombre,
                                    weight=ft.FontWeight.BOLD,
                                    size=15,
                                    color=ui_theme.DARK_TEXT,
                                ),
                                ft.Text(
                                    f"{u.login} · {u.rol}",
                                    size=12,
                                    color=ui_theme.MID_GRAY,
                                ),
                            ],
                        ),
                        ui.status_chip(
                            "Activo" if u.activo else "Inactivo",
                            tone="ok" if u.activo else "neutral",
                        ),
                    ],
                ),
                ft.Row(controls=[rename, rol_dd, pwd]),
                ft.Row(wrap=True, controls=acciones),
            ],
        ),
    )


def _panel_responsables(screen: AdminScreenVM, **cbs) -> ft.Control:
    on_filtro = cbs["on_filtro"]
    on_proponer_crear = cbs["on_proponer_crear"]
    on_proponer_renombrar = cbs["on_proponer_renombrar"]
    on_proponer_desactivar = cbs["on_proponer_desactivar"]
    on_proponer_reactivar = cbs["on_proponer_reactivar"]

    crear_tf = ft.TextField(label="Nuevo responsable", expand=True)
    lista: list[ft.Control] = []
    if not screen.responsables:
        lista.append(
            ui.empty_state(
                "Sin responsables",
                "No hay coincidencias con el filtro."
                if screen.filtro
                else "Cree el primero para registrar mermas.",
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

    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        controls=[
            ui.page_header(
                "Responsables de merma",
                "Quién responde por mermas · motivos de catálogo fijo",
                actions=[
                    ui.status_chip(
                        f"{len(screen.responsables)} en listado",
                        tone="info",
                    ),
                ],
            ),
            ui.card_surface(
                ft.Row(
                    controls=[
                        crear_tf,
                        ui.primary_button(
                            "Añadir",
                            lambda: on_proponer_crear(crear_tf.value or ""),
                            icon=ft.Icons.PERSON_ADD,
                            disabled=screen.mutando,
                        ),
                    ]
                ),
                title="Alta",
            ),
            _filtro_row(screen, on_filtro),
            ui.card_surface(*lista, title="Listado"),
            ui.card_surface(
                ui_theme.text_help(" · ".join(screen.motivos_fijos) or "—"),
                title="Motivos de merma (fijos)",
            ),
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
    acciones: list[ft.Control] = [
        ui.secondary_button(
            "Renombrar",
            lambda rid=r.id, tf=rename_tf: on_renombrar(rid, tf.value or ""),
            disabled=disabled,
        ),
    ]
    if r.activo:
        acciones.append(
            ft.TextButton(
                "Desactivar",
                disabled=disabled,
                style=ft.ButtonStyle(color=ui_theme.DANGER),
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
        bgcolor=ui_theme.SURFACE_CARD if r.activo else ui_theme.LIGHT_GRAY,
        padding=ui_theme.SPACE_MD,
        border_radius=ui_theme.RADIUS_MD,
        border=ft.Border.all(1, ui_theme.BORDER),
        content=ft.Column(
            spacing=ui_theme.SPACE_SM,
            tight=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(
                            r.nombre,
                            size=15,
                            weight=ft.FontWeight.BOLD,
                            color=ui_theme.DARK_TEXT,
                        ),
                        ui.status_chip(
                            "Activo" if r.activo else "Inactivo",
                            tone="ok" if r.activo else "neutral",
                        ),
                    ],
                ),
                ft.Text(f"Id: {r.id}", size=12, color=ui_theme.MID_GRAY),
                rename_tf,
                ft.Row(controls=acciones),
            ],
        ),
    )


def _panel_proveedores(screen: AdminScreenVM, **cbs) -> ft.Control:
    on_filtro = cbs["on_filtro"]
    on_crear = cbs["on_crear_proveedor"]
    on_editar = cbs["on_editar_proveedor"]
    on_des = cbs["on_desactivar_proveedor"]
    on_rea = cbs["on_reactivar_proveedor"]
    nombre = ft.TextField(label="Nombre fiscal", expand=True)
    codigo = ft.TextField(label="Código", width=140)
    comercial = ft.TextField(label="Nombre comercial", expand=True)
    nif = ft.TextField(label="NIF/CIF", width=140)

    def _crear(_e=None) -> None:
        on_crear(
            nombre.value or "",
            codigo.value or "",
            comercial.value or "",
            nif.value or "",
        )

    lista = [
        _proveedor_row(
            p,
            disabled=screen.mutando or screen.pending is not None,
            on_editar=on_editar,
            on_desactivar=on_des,
            on_reactivar=on_rea,
        )
        for p in screen.proveedores
    ]
    if not lista:
        lista = [
            ui.empty_state(
                "Sin proveedores",
                "Cree la ficha fiscal del primero.",
            )
        ]

    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        controls=[
            ui.page_header(
                "Proveedores",
                "Ficha fiscal y estado",
                actions=[
                    ui.status_chip(f"{len(screen.proveedores)} en listado", tone="info"),
                ],
            ),
            ui.card_surface(
                ft.Row(controls=[nombre, codigo]),
                ft.Row(
                    controls=[
                        comercial,
                        nif,
                        ui.primary_button(
                            "Crear",
                            _crear,
                            icon=ft.Icons.ADD_BUSINESS,
                            disabled=screen.mutando,
                        ),
                    ]
                ),
                title="Alta",
            ),
            _filtro_row(screen, on_filtro),
            ui.card_surface(*lista, title="Listado"),
        ],
    )


def _proveedor_row(
    p: ProveedorAdminVM,
    *,
    disabled: bool,
    on_editar: Callable[..., None],
    on_desactivar: Callable[[str], None],
    on_reactivar: Callable[[str], None],
) -> ft.Control:
    nombre_tf = ft.TextField(
        label="Nombre fiscal",
        value=p.nombre_fiscal,
        expand=True,
        disabled=disabled,
    )
    codigo_tf = ft.TextField(
        label="Código",
        value=p.codigo,
        width=120,
        disabled=disabled,
    )
    acciones: list[ft.Control] = [
        ui.secondary_button(
            "Guardar",
            lambda pid=p.id, nf=nombre_tf, cf=codigo_tf: on_editar(
                pid, nf.value or "", cf.value or ""
            ),
            disabled=disabled,
        ),
    ]
    if p.activo:
        acciones.append(
            ft.TextButton(
                "Desactivar",
                disabled=disabled,
                style=ft.ButtonStyle(color=ui_theme.DANGER),
                on_click=lambda _e, pid=p.id: on_desactivar(pid),
            )
        )
    else:
        acciones.append(
            ft.TextButton(
                "Reactivar",
                disabled=disabled,
                on_click=lambda _e, pid=p.id: on_reactivar(pid),
            )
        )
    return ft.Container(
        bgcolor=ui_theme.SURFACE_CARD if p.activo else ui_theme.LIGHT_GRAY,
        padding=ui_theme.SPACE_MD,
        border_radius=ui_theme.RADIUS_MD,
        border=ft.Border.all(1, ui_theme.BORDER),
        content=ft.Column(
            spacing=ui_theme.SPACE_SM,
            tight=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(
                            p.nombre_comercial or p.nombre_fiscal,
                            size=15,
                            weight=ft.FontWeight.BOLD,
                            color=ui_theme.DARK_TEXT,
                        ),
                        ui.status_chip(
                            "Activo" if p.activo else "Inactivo",
                            tone="ok" if p.activo else "neutral",
                        ),
                    ],
                ),
                ft.Text(
                    f"Id: {p.id} · NIF: {p.nif_cif or '—'}",
                    size=12,
                    color=ui_theme.MID_GRAY,
                ),
                ft.Row(controls=[nombre_tf, codigo_tf]),
                ft.Row(controls=acciones),
            ],
        ),
    )


def _panel_documentos(screen: AdminScreenVM, **cbs) -> ft.Control:
    on_filtro = cbs["on_filtro"]
    on_export = cbs.get("on_exportar_documentos")
    on_anular = cbs.get("on_proponer_anular_documento")
    on_rect_eco = cbs.get("on_proponer_rectificativa_economica")
    on_rect_stock = cbs.get("on_proponer_rectificativa_stock")
    on_adjuntar = cbs.get("on_adjuntar_archivo")
    on_abrir = cbs.get("on_abrir_adjunto")

    filas = []
    for d in screen.documentos:
        motivo_tf = ft.TextField(
            label="Motivo",
            dense=True,
            width=180,
            disabled=screen.mutando,
        )
        estado_l = d.estado.lower()
        anulado = estado_l in ("anulado", "anulada")
        filas.append(
            ft.Container(
                padding=8,
                border=ft.Border(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
                content=ft.Column(
                    spacing=6,
                    controls=[
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Column(
                                    spacing=2,
                                    expand=True,
                                    controls=[
                                        ft.Text(
                                            f"{d.tipo} · {d.n_lineas} línea(s)",
                                            weight=ft.FontWeight.W_600,
                                            size=13,
                                            color=ui_theme.DARK_TEXT,
                                        ),
                                        ft.Text(
                                            f"{d.fecha} · {d.proveedor or 'Sin proveedor'}"
                                            + (
                                                f" · ref. {d.referencia}"
                                                if d.referencia
                                                else ""
                                            ),
                                            size=12,
                                            color=ui_theme.MID_GRAY,
                                        ),
                                    ],
                                ),
                                ui.status_chip(
                                    d.estado,
                                    tone="danger"
                                    if anulado
                                    else ("ok" if "confirm" in estado_l else "info"),
                                ),
                                motivo_tf,
                            ],
                        ),
                        ft.Row(
                            wrap=True,
                            controls=[
                                ft.TextButton(
                                    "Anular",
                                    disabled=screen.mutando or anulado or on_anular is None,
                                    on_click=lambda _e, did=d.id, tf=motivo_tf: (
                                        on_anular(did, tf.value or "")
                                        if on_anular
                                        else None
                                    ),
                                ),
                                ft.TextButton(
                                    "Rect. económica",
                                    disabled=screen.mutando
                                    or anulado
                                    or on_rect_eco is None,
                                    on_click=lambda _e, did=d.id, tf=motivo_tf: (
                                        on_rect_eco(did, tf.value or "")
                                        if on_rect_eco
                                        else None
                                    ),
                                ),
                                ft.TextButton(
                                    "Rect. stock",
                                    disabled=screen.mutando
                                    or anulado
                                    or on_rect_stock is None,
                                    on_click=lambda _e, did=d.id, tf=motivo_tf: (
                                        on_rect_stock(did, tf.value or "")
                                        if on_rect_stock
                                        else None
                                    ),
                                ),
                            ],
                        ),
                    ],
                ),
            )
        )
    if not filas:
        filas = [
            ui.empty_state(
                "Sin documentos",
                "No hay resultados o no tiene permiso de consulta.",
            )
        ]

    adj_rows: list[ft.Control] = []
    for a in screen.archivos:
        adj_rows.append(
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                border=ft.Border(bottom=ft.BorderSide(1, ui_theme.BORDER)),
                content=ft.Row(
                    controls=[
                        ft.Text(
                            a.nombre,
                            expand=True,
                            size=13,
                            weight=ft.FontWeight.W_600,
                            color=ui_theme.DARK_TEXT,
                        ),
                        ft.Text(
                            f"doc {a.documento_id or '—'}",
                            size=12,
                            color=ui_theme.MID_GRAY,
                            width=140,
                        ),
                        ft.TextButton(
                            "Abrir",
                            disabled=screen.mutando or on_abrir is None,
                            on_click=lambda _e, aid=a.id: on_abrir(aid)
                            if on_abrir
                            else None,
                        ),
                    ]
                ),
            )
        )
    if not adj_rows:
        adj_rows = [
            ui.empty_state(
                "Sin adjuntos",
                "Adjunte un archivo local a un documento del listado.",
            )
        ]

    doc_adj = ft.Dropdown(
        label="Documento destino",
        options=[
            ft.dropdown.Option(key=d.id, text=f"{d.tipo} {d.referencia or d.id}")
            for d in screen.documentos[:40]
        ],
        width=280,
    )
    ruta_tf = ft.TextField(label="Ruta local del archivo", expand=True)

    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        controls=[
            ui.alert_banner(
                "Deprecado: use Terminal Inventario → Documentos / Pendientes. "
                "Este panel Admin queda como fallback.",
                severity="warning",
            ),
            ui.page_header(
                "Documentos",
                "Consulta, anulación, rectificativas y adjuntos",
                actions=[
                    ui.status_chip(f"{len(screen.documentos)} docs", tone="info"),
                    ui.status_chip(f"{len(screen.archivos)} adjuntos", tone="neutral"),
                    ui.secondary_button(
                        "Exportar CSV",
                        lambda: on_export() if on_export else None,
                        icon=ft.Icons.DOWNLOAD,
                        disabled=screen.mutando or on_export is None,
                    ),
                ],
            ),
            ft.Row(
                controls=[
                    ft.TextField(
                        label="Buscar documentos",
                        value=screen.filtro,
                        prefix_icon=ft.Icons.SEARCH,
                        on_submit=lambda e: on_filtro(e.control.value or ""),
                        on_blur=lambda e: on_filtro(e.control.value or ""),
                        expand=True,
                    ),
                ]
            ),
            ui.card_surface(*filas, title="Listado"),
            ui.card_surface(
                ft.Row(
                    controls=[
                        doc_adj,
                        ruta_tf,
                        ui.primary_button(
                            "Adjuntar",
                            lambda: (
                                on_adjuntar(doc_adj.value or "", ruta_tf.value or "")
                                if on_adjuntar
                                else None
                            ),
                            icon=ft.Icons.ATTACH_FILE,
                            disabled=screen.mutando or on_adjuntar is None,
                        ),
                    ]
                ),
                *adj_rows,
                title="Adjuntos",
            ),
        ],
    )


def _panel_compras(screen: AdminScreenVM, **cbs) -> ft.Control:
    on_set_cab = cbs["on_set_compra_cabecera"]
    on_add = cbs["on_añadir_linea_compra"]
    on_add_busq = cbs.get("on_añadir_linea_compra_busqueda")
    on_update = cbs.get("on_update_linea_compra")
    on_quitar = cbs["on_quitar_linea_compra"]
    on_guardar = cbs["on_guardar_borrador_compra"]
    on_confirmar = cbs["on_confirmar_compra"]
    on_limpiar = cbs["on_limpiar_borrador_compra"]
    on_busq = cbs.get("on_set_compra_prod_busqueda")
    on_sugerir = cbs.get("on_seleccionar_sugerencia_compra")
    on_cargar = cbs.get("on_cargar_borrador_compra")
    on_anular_borr = cbs.get("on_anular_borrador_compra")
    on_import_noray = cbs.get("on_importar_noray")
    on_set_ubi = cbs.get("on_set_compra_linea_ubicacion")
    on_set_prod = cbs.get("on_set_compra_linea_producto")
    on_verificar = cbs.get("on_verificar_linea_compra")
    on_crear_prod_ln = cbs.get("on_crear_producto_linea_noray")

    deprecacion = ui.alert_banner(
        "Deprecado: use Terminal Inventario → Albarán / Factura / Documentos "
        "(flujo Noray). Este panel Admin queda como fallback.",
        severity="warning",
    )

    activos_prov = [p for p in screen.proveedores if p.activo]
    activos_ubi = [u for u in screen.ubicaciones if u.activo]
    activos_prod = [p for p in screen.productos if p.activo]
    ubi_options = [
        ft.dropdown.Option(
            key=u.id,
            text=f"{u.codigo} · {u.nombre}" if u.codigo else u.nombre,
        )
        for u in activos_ubi
    ]
    prod_options = [
        ft.dropdown.Option(
            key=p.id,
            text=f"{p.nombre}" + (f" [{p.codigo}]" if p.codigo else ""),
        )
        for p in activos_prod[:400]
    ]

    def _parse_num(raw: str | None, default: float = 0.0) -> float:
        try:
            return float((raw or "0").replace(",", "."))
        except ValueError:
            return default

    def _sync_cab(tipo_v: str, prov_v: str, ref_v: str) -> None:
        on_set_cab(prov_v or "", ref_v or "", tipo_v or "albaran")

    tipo = ft.Dropdown(
        label="Tipo",
        options=[
            ft.dropdown.Option(key="albaran", text="Albarán"),
            ft.dropdown.Option(key="factura", text="Factura"),
        ],
        value=screen.compra_tipo or "albaran",
        width=140,
        on_select=lambda e: _sync_cab(
            getattr(e.control, "value", None) or "albaran",
            prov.value or "",
            ref.value or "",
        ),
    )
    prov = ft.Dropdown(
        label="Proveedor",
        options=[
            ft.dropdown.Option(
                key=p.id,
                text=p.nombre_comercial or p.nombre_fiscal,
            )
            for p in activos_prov
        ],
        value=screen.compra_proveedor_id or None,
        expand=True,
        on_select=lambda e: _sync_cab(
            tipo.value or "albaran",
            getattr(e.control, "value", None) or "",
            ref.value or "",
        ),
    )
    ref = ft.TextField(
        label="Referencia / nº doc.",
        value=screen.compra_referencia,
        width=180,
        on_blur=lambda e: _sync_cab(
            tipo.value or "albaran",
            prov.value or "",
            e.control.value or "",
        ),
        on_submit=lambda e: _sync_cab(
            tipo.value or "albaran",
            prov.value or "",
            e.control.value or "",
        ),
    )

    busqueda = ft.TextField(
        label="Buscar producto (parcial)",
        hint_text="Ej. huevo → opciones con «huevo»",
        prefix_icon=ft.Icons.SEARCH,
        value=screen.compra_prod_busqueda,
        expand=True,
        autofocus=True,
        on_change=lambda e: on_busq(e.control.value or "") if on_busq else None,
    )
    cantidad = ft.TextField(label="Cant.", width=100, value="1")
    precio = ft.TextField(
        label="P. unit.",
        width=120,
        value="0",
        hint_text="0 = último precio",
    )

    def _add(_e=None) -> None:
        _sync_cab(tipo.value or "albaran", prov.value or "", ref.value or "")
        cant = _parse_num(cantidad.value, 0.0)
        prec = _parse_num(precio.value, 0.0)
        texto = (busqueda.value or screen.compra_prod_busqueda or "").strip()
        if texto and on_add_busq is not None:
            on_add_busq(texto, cant, prec)
        elif screen.compra_prod_sugerencias:
            if len(screen.compra_prod_sugerencias) == 1:
                on_add(screen.compra_prod_sugerencias[0].id, cant, prec)
            elif on_busq:
                on_busq(texto)
        else:
            on_add("", cant, prec)
        cantidad.value = "1"

    busqueda.on_submit = _add
    cantidad.on_submit = _add
    precio.on_submit = _add

    sugerencias: list[ft.Control] = []
    if screen.compra_prod_busqueda.strip() and len(screen.compra_prod_busqueda.strip()) >= 2:
        if not screen.compra_prod_sugerencias:
            sugerencias.append(
                ui_theme.text_help("Sin coincidencias. Pruebe otro término.")
            )
        else:
            chips: list[ft.Control] = []
            for p in screen.compra_prod_sugerencias:
                label = p.nombre + (f" [{p.codigo}]" if p.codigo else "")
                chips.append(
                    ft.TextButton(
                        label,
                        icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                        disabled=screen.mutando,
                        on_click=lambda _e, pid=p.id: (
                            on_sugerir(pid) if on_sugerir else None
                        ),
                    )
                )
            sugerencias.append(ft.Row(wrap=True, spacing=4, controls=chips))
            sugerencias.append(
                ui_theme.text_help(
                    "Pulse una opción para añadirla al borrador (cant. 1; ajuste en la tabla)."
                )
            )

    noray_help = (
        f"Archivo: {screen.compra_noray_archivo}"
        if screen.compra_noray_archivo
        else "Suba el Excel de líneas Noray/BC. Empareja por nombre y verifica "
        "código; si no cuadran puede reasignar, verificar o crear producto."
    )
    if screen.compra_noray_omitidas:
        noray_help += (
            f" · {screen.compra_noray_omitidas} línea(s) pendientes de resolver."
        )
    noray_card = ui.card_surface(
        ui_theme.text_help(noray_help),
        ft.Row(
            wrap=True,
            controls=[
                ui.primary_button(
                    "Subir Excel Noray",
                    on_import_noray or (lambda: None),
                    icon=ft.Icons.UPLOAD_FILE,
                    disabled=screen.mutando or on_import_noray is None,
                ),
            ],
        ),
        title="Importar albarán / factura Noray",
    )

    total = sum(l.cantidad * l.precio_unitario for l in screen.compra_lineas)
    header = ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        bgcolor=ui_theme.LIGHT_GRAY,
        content=ft.Text(
            "Líneas del documento — producto, ubicación, cantidad (Ud/Kg), "
            "precio unitario y total",
            size=11,
            weight=ft.FontWeight.W_600,
            color=ui_theme.DARK_TEXT,
        ),
    )
    lineas: list[ft.Control] = [header]
    if screen.compra_lineas:
        for i, ln in enumerate(screen.compra_lineas):
            lineas.append(
                _compra_linea_row(
                    i,
                    ln,
                    on_quitar,
                    on_update=on_update,
                    on_set_ubicacion=on_set_ubi,
                    on_set_producto=on_set_prod,
                    on_verificar=on_verificar,
                    on_crear_producto=on_crear_prod_ln,
                    ubicacion_options=ubi_options,
                    producto_options=prod_options,
                    disabled=screen.mutando,
                )
            )
    else:
        lineas.append(
            ui.empty_state(
                "Borrador vacío",
                "Suba un Excel Noray o escriba parte del nombre y elija una opción.",
            )
        )

    tipo_lbl = "factura" if (screen.compra_tipo or "") == "factura" else "albarán"
    alb_dd = ft.Dropdown(
        label="Albarán a conciliar",
        options=[
            ft.dropdown.Option(
                key=a.id,
                text=f"{a.referencia or a.id} · {a.proveedor}",
            )
            for a in screen.albaranes_conciliables
        ],
        value=screen.compra_albaran_id or None,
        expand=True,
        visible=(screen.compra_tipo or "") == "factura",
        on_select=lambda e: cbs.get("on_set_compra_albaran")
        and cbs["on_set_compra_albaran"](getattr(e.control, "value", None) or ""),
    )

    borradores_ui: list[ft.Control] = []
    if not screen.compra_borradores:
        borradores_ui.append(
            ui_theme.text_help("No hay borradores guardados de albarán/factura.")
        )
    else:
        for d in screen.compra_borradores:
            etiqueta = (
                f"{d.tipo} · {d.referencia or d.id} · {d.proveedor or '—'} "
                f"· {d.n_lineas} línea(s)"
            )
            borradores_ui.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                    border=ft.Border(bottom=ft.BorderSide(1, ui_theme.BORDER)),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(
                                etiqueta,
                                size=12,
                                color=ui_theme.DARK_TEXT,
                                expand=True,
                            ),
                            ui.secondary_button(
                                "Editar",
                                lambda did=d.id: on_cargar(did) if on_cargar else None,
                                disabled=screen.mutando or on_cargar is None,
                            ),
                            ft.TextButton(
                                "Anular",
                                disabled=screen.mutando or on_anular_borr is None,
                                style=ft.ButtonStyle(color=ui_theme.DANGER),
                                on_click=lambda _e, did=d.id: (
                                    on_anular_borr(did) if on_anular_borr else None
                                ),
                            ),
                        ],
                    ),
                )
            )

    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        controls=[
            deprecacion,
            ui.page_header(
                "Registro de compras",
                f"Albarán / factura · import Noray · ubicación por línea · {tipo_lbl}",
                actions=[
                    ui.status_chip(
                        f"{len(screen.compra_lineas)} línea(s)",
                        tone="info",
                    ),
                    ui.status_chip(
                        f"Total {total:.2f}",
                        tone="ok" if total else "neutral",
                    ),
                    ui.status_chip(
                        f"Doc {screen.compra_documento_id}"
                        if screen.compra_documento_id
                        else "Nuevo / en memoria",
                        tone="ok" if screen.compra_documento_id else "warn",
                    ),
                ],
            ),
            noray_card,
            ui.card_surface(
                *borradores_ui,
                title=f"Borradores guardados ({len(screen.compra_borradores)})",
            ),
            ui.card_surface(
                ft.Row(controls=[tipo, prov, ref]),
                alb_dd,
                title="Cabecera",
            ),
            ui.card_surface(
                ui_theme.text_help(
                    "Escriba parte del nombre o código (≥2 letras). "
                    "Elija una sugerencia o pulse Enter si hay coincidencia única."
                ),
                ft.Row(controls=[busqueda, cantidad, precio]),
                *sugerencias,
                ft.Row(
                    wrap=True,
                    controls=[
                        ui.primary_button(
                            "Añadir línea",
                            _add,
                            icon=ft.Icons.ADD,
                            disabled=screen.mutando,
                        ),
                        ui.secondary_button(
                            "Guardar borrador",
                            on_guardar,
                            icon=ft.Icons.SAVE_OUTLINED,
                            disabled=screen.mutando,
                        ),
                        ui.primary_button(
                            "Confirmar documento",
                            on_confirmar,
                            icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                            disabled=screen.mutando or not screen.compra_lineas,
                        ),
                        ft.TextButton(
                            "Limpiar pantalla",
                            disabled=screen.mutando,
                            on_click=lambda _e: on_limpiar(),
                        ),
                    ],
                ),
                title="Captura de líneas",
            ),
            ft.Container(
                bgcolor=ui_theme.SURFACE_CARD,
                border_radius=ui_theme.RADIUS_MD,
                border=ft.Border.all(1, ui_theme.BORDER),
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                content=ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, controls=lineas),
            ),
        ],
    )


def _compra_campo_etiquetado(
    etiqueta: str,
    control: ft.Control,
    *,
    width: float | None = None,
    expand: bool = False,
) -> ft.Control:
    """Etiqueta encima del control para que se sepa qué es cada caja."""
    return ft.Container(
        width=width,
        expand=expand,
        content=ft.Column(
            spacing=2,
            tight=True,
            controls=[
                ft.Text(
                    etiqueta,
                    size=10,
                    weight=ft.FontWeight.W_600,
                    color=ui_theme.MID_GRAY,
                ),
                control,
            ],
        ),
    )


def _compra_linea_row(
    index: int,
    ln: CompraLineaVM,
    on_quitar: Callable[[int], None],
    *,
    on_update: Callable[..., None] | None,
    on_set_ubicacion: Callable[[int, str], None] | None,
    on_set_producto: Callable[[int, str], None] | None,
    on_verificar: Callable[[int], None] | None,
    on_crear_producto: Callable[[int], None] | None,
    ubicacion_options: list,
    producto_options: list,
    disabled: bool,
) -> ft.Control:
    unidad = (ln.unidad or "Ud").strip() or "Ud"
    cant_tf = ft.TextField(
        value=f"{ln.cantidad:g}",
        width=110,
        dense=True,
        text_align=ft.TextAlign.RIGHT,
        disabled=disabled or on_update is None,
    )
    prec_tf = ft.TextField(
        value=f"{ln.precio_unitario:.4g}",
        width=120,
        dense=True,
        text_align=ft.TextAlign.RIGHT,
        disabled=disabled or on_update is None,
        prefix_text="€ ",
    )
    subtotal = ln.cantidad * ln.precio_unitario
    ubi_dd = ft.Dropdown(
        options=ubicacion_options,
        value=ln.ubicacion_destino_id or None,
        width=200,
        dense=True,
        hint_text="Dónde se guarda",
        disabled=disabled or on_set_ubicacion is None or not ubicacion_options,
        on_select=lambda e, i=index: (
            on_set_ubicacion(i, getattr(e.control, "value", None) or "")
            if on_set_ubicacion
            else None
        ),
    )
    prod_dd = ft.Dropdown(
        options=producto_options,
        value=ln.producto_id or None,
        expand=True,
        dense=True,
        hint_text="Elegir / cambiar producto",
        disabled=disabled or on_set_producto is None or not producto_options,
        on_select=lambda e, i=index: (
            on_set_producto(i, getattr(e.control, "value", None) or "")
            if on_set_producto
            else None
        ),
    )

    def _commit(_e=None, i=index, ct=cant_tf, pt=prec_tf) -> None:
        if on_update is None:
            return
        try:
            cant = float((ct.value or "0").replace(",", "."))
        except ValueError:
            cant = ln.cantidad
        try:
            prec = float((pt.value or "0").replace(",", "."))
        except ValueError:
            prec = ln.precio_unitario
        if cant == ln.cantidad and prec == ln.precio_unitario:
            return
        on_update(i, cant, prec)

    cant_tf.on_submit = _commit
    cant_tf.on_blur = _commit
    prec_tf.on_submit = _commit
    prec_tf.on_blur = _commit

    estado = ln.match_estado or "ok"
    etiq = MATCH_ESTADO_ETIQUETA.get(estado, estado)
    tone = {
        "ok": "ok",
        "revisar": "warn",
        "conflicto": "danger",
        "sin_match": "danger",
        "ambiguo": "warn",
    }.get(estado, "neutral")

    noray_nom = ln.nombre_noray or ln.nombre
    noray_cod = ln.codigo_noray or "—"
    cat_cod = ln.producto_codigo or "—"

    # Nombre completo visible (sin ellipsis de 1 línea).
    titulo_noray = f"Noray: {noray_nom}"
    if noray_cod and noray_cod != "—":
        titulo_noray = f"{titulo_noray}  ·  código {noray_cod}"
    detalle_cols: list[ft.Control] = [
        ft.Row(
            spacing=8,
            wrap=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ui.status_chip(etiq, tone=tone),
                ft.Text(
                    titulo_noray,
                    size=13,
                    weight=ft.FontWeight.W_600,
                    color=ui_theme.DARK_TEXT,
                    selectable=True,
                ),
            ],
        ),
    ]
    if ln.producto_id:
        detalle_cols.append(
            ft.Text(
                f"Catálogo: {ln.nombre}"
                + (f"  ·  código {cat_cod}" if cat_cod != "—" else ""),
                size=12,
                color=ui_theme.MID_GRAY,
                selectable=True,
            )
        )
    meta_bits = [
        x
        for x in (
            f"Almacén Noray: {ln.almacen_noray}" if ln.almacen_noray else "",
            f"Unidad: {unidad}",
            ln.aviso,
        )
        if x
    ]
    if meta_bits:
        detalle_cols.append(
            ft.Text(
                " · ".join(meta_bits),
                size=11,
                color=ui_theme.MID_GRAY,
                selectable=True,
            )
        )

    acciones: list[ft.Control] = []
    if estado in ("revisar", "conflicto") and ln.producto_id and on_verificar:
        acciones.append(
            ft.TextButton(
                "Verificar",
                disabled=disabled,
                on_click=lambda _e, i=index: on_verificar(i),
            )
        )
    if estado in ("sin_match", "conflicto", "ambiguo", "revisar") and on_crear_producto:
        acciones.append(
            ft.TextButton(
                "Crear producto",
                disabled=disabled or not (ln.codigo_noray or "").strip(),
                on_click=lambda _e, i=index: on_crear_producto(i),
            )
        )
    acciones.append(
        ft.TextButton(
            "Quitar",
            disabled=disabled,
            on_click=lambda _e, i=index: on_quitar(i),
        )
    )

    total_box = ft.Container(
        width=120,
        padding=ft.Padding.symmetric(horizontal=8, vertical=10),
        bgcolor=ui_theme.LIGHT_GRAY,
        border_radius=ui_theme.RADIUS_SM,
        content=ft.Column(
            spacing=2,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.END,
            controls=[
                ft.Text(
                    "Total línea",
                    size=10,
                    weight=ft.FontWeight.W_600,
                    color=ui_theme.MID_GRAY,
                ),
                ft.Text(
                    f"{subtotal:.2f} €",
                    size=14,
                    weight=ft.FontWeight.BOLD,
                    color=ui_theme.DARK_TEXT,
                ),
            ],
        ),
    )

    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        border=ft.Border(bottom=ft.BorderSide(1, ui_theme.BORDER)),
        bgcolor=ui_theme.WARNING_BG
        if estado in ("revisar", "ambiguo")
        else (ui_theme.DANGER_BG if estado in ("sin_match", "conflicto") else None),
        content=ft.Column(
            spacing=8,
            tight=True,
            controls=[
                ft.Column(spacing=2, tight=True, controls=detalle_cols),
                ft.Row(
                    wrap=True,
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        _compra_campo_etiquetado(
                            "Producto (catálogo)",
                            prod_dd,
                            expand=True,
                        ),
                        _compra_campo_etiquetado(
                            "Ubicación de guardado",
                            ubi_dd,
                            width=200,
                        ),
                        _compra_campo_etiquetado(
                            f"Cantidad ({unidad})",
                            cant_tf,
                            width=120,
                        ),
                        _compra_campo_etiquetado(
                            "Precio unitario",
                            prec_tf,
                            width=130,
                        ),
                        total_box,
                        ft.Container(
                            padding=ft.Padding.only(top=14),
                            content=ft.Row(spacing=4, tight=True, controls=acciones),
                        ),
                    ],
                ),
            ],
        ),
    )


def _panel_inventario(screen: AdminScreenVM, **cbs) -> ft.Control:
    on_registrar = cbs["on_registrar_lote"]
    activos = [p for p in screen.productos if p.activo]
    ubis_activas = [u for u in screen.ubicaciones if u.activo]

    if not activos:
        return ft.Column(
            spacing=ui_theme.SPACE_MD,
            controls=[
                ui.page_header(
                    "Inventario inicial",
                    "Alta de lote con valoración total",
                ),
                ui.empty_state(
                    "Sin productos activos",
                    "Cree o reactive productos en Catálogo antes de registrar lotes.",
                ),
                ui.secondary_button(
                    "Ir a Productos",
                    lambda: (cbs.get("on_seccion") or (lambda _s: None))("productos"),
                    icon=ft.Icons.INVENTORY_2,
                ),
            ],
        )

    prod = ft.Dropdown(
        label="Producto",
        options=[
            ft.dropdown.Option(key=p.id, text=f"{p.nombre} ({p.unidad})") for p in activos
        ],
        expand=True,
    )
    cantidad = ft.TextField(label="Cantidad", width=120, value="1")
    precio = ft.TextField(label="Precio total", width=140, value="1")
    marca = ft.TextField(label="Marca / proveedor", expand=True)
    ubi = ft.Dropdown(
        label="Ubicación destino",
        options=[
            ft.dropdown.Option(key=u.id, text=u.nombre if not u.codigo else f"{u.nombre} ({u.codigo})")
            for u in ubis_activas
        ],
        value=ubis_activas[0].id if ubis_activas else None,
        expand=True,
        visible=bool(ubis_activas),
    )

    def _go(_e=None) -> None:
        try:
            cant = float((cantidad.value or "0").replace(",", "."))
        except ValueError:
            cant = 0.0
        try:
            prec = float((precio.value or "0").replace(",", "."))
        except ValueError:
            prec = 0.0
        on_registrar(
            prod.value or "",
            cant,
            prec,
            marca.value or "",
            ubi.value or "",
        )

    body: list[ft.Control] = [
        ui.page_header(
            "Inventario inicial",
            "Alta de lote (cantidad + precio total del lote)",
            actions=[
                ui.status_chip(f"{len(activos)} productos", tone="info"),
                ui.status_chip(
                    f"{len(ubis_activas)} ubicaciones" if ubis_activas else "Sin ubicación",
                    tone="neutral" if ubis_activas else "warn",
                ),
            ],
        ),
        ui.card_surface(
            ft.Row(controls=[prod, cantidad, precio]),
            ft.Row(
                controls=[
                    marca,
                    ubi if ubis_activas else ft.Container(),
                    ui.primary_button(
                        "Registrar lote",
                        lambda: _go(),
                        icon=ft.Icons.ADD_BOX,
                        disabled=screen.mutando,
                    ),
                ]
            ),
            title="Nuevo lote",
        ),
    ]

    if not ubis_activas:
        body.append(
            ui.alert_banner(
                "No hay ubicaciones activas: el lote se registrará sin destino de ubicación. "
                "Puede crearlas en Catálogos.",
                severity="warning",
            )
        )

    la = screen.lote_alta
    if la is not None:
        ubi_lbl = la.ubicacion_destino_id or "—"
        for u in screen.ubicaciones:
            if u.id == la.ubicacion_destino_id:
                ubi_lbl = u.nombre
                break
        body.append(
            ui.card_surface(
                ft.Text(
                    f"{la.producto_nombre} · cant. {la.cantidad:g} · total {la.precio_total:.2f}",
                    size=14,
                    weight=ft.FontWeight.W_600,
                    color=ui_theme.DARK_TEXT,
                ),
                ft.Text(
                    f"Marca: {la.marca_proveedor or '—'} · Ubicación: {ubi_lbl}",
                    size=12,
                    color=ui_theme.MID_GRAY,
                ),
                title="Último lote en pantalla",
            )
        )

    return ft.Column(spacing=ui_theme.SPACE_MD, controls=body)


def _panel_backup(screen: AdminScreenVM, **cbs) -> ft.Control:
    on_gen = cbs["on_generar_backup"]
    on_insp = cbs["on_inspeccionar_backup"]
    on_rest = cbs["on_proponer_restaurar"]
    confirm = ft.TextField(
        label="Confirmación restauración",
        hint_text="Escriba RESTAURAR",
        width=220,
    )

    lista: list[ft.Control] = []
    if not screen.backups:
        lista.append(
            ui.empty_state(
                "Sin backups locales",
                "Genere un ZIP para crear el primero.",
            )
        )
    else:
        for b in screen.backups:
            lista.append(
                _backup_row(
                    b,
                    screen=screen,
                    confirm_tf=confirm,
                    on_insp=on_insp,
                    on_rest=on_rest,
                )
            )

    restore_help: ft.Control
    if screen.puede_restaurar_backup:
        restore_help = confirm
    else:
        restore_help = ui.alert_banner(
            "Restaurar requiere permiso Dirección (RESTAURAR_BACKUP).",
            severity="warning",
        )

    body: list[ft.Control] = [
        ui.page_header(
            "Backup",
            "ZIP local verificable · inspección y restauración controlada",
            actions=[
                ui.status_chip(f"{len(screen.backups)} archivo(s)", tone="info"),
                ui.primary_button(
                    "Generar backup ZIP",
                    on_gen,
                    icon=ft.Icons.BACKUP,
                    disabled=screen.mutando or not screen.puede_exportar_backup,
                ),
            ],
        ),
    ]
    if screen.inspeccion_backup:
        body.append(ui.alert_banner(screen.inspeccion_backup, severity="info"))
    body.append(ui.card_surface(*lista, title="Archivos"))
    body.append(
        ui.card_surface(
            restore_help,
            title="Restauración",
        )
    )
    return ft.Column(spacing=ui_theme.SPACE_MD, controls=body)


def _backup_row(
    b: BackupItemVM,
    *,
    screen: AdminScreenVM,
    confirm_tf: ft.TextField,
    on_insp: Callable[[str], None],
    on_rest: Callable[[str, str], None],
) -> ft.Control:
    acciones: list[ft.Control] = []
    if screen.puede_restaurar_backup:
        acciones.extend(
            [
                ui.secondary_button(
                    "Inspeccionar",
                    lambda ruta=b.ruta: on_insp(ruta),
                    icon=ft.Icons.SEARCH,
                    disabled=screen.mutando,
                ),
                ft.TextButton(
                    "Restaurar…",
                    disabled=screen.mutando or screen.pending is not None,
                    style=ft.ButtonStyle(color=ui_theme.DANGER),
                    on_click=lambda _e, ruta=b.ruta, tf=confirm_tf: on_rest(
                        ruta, tf.value or ""
                    ),
                ),
            ]
        )
    return ft.Container(
        padding=ui_theme.SPACE_MD,
        border=ft.Border(bottom=ft.BorderSide(1, ui_theme.BORDER)),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    spacing=2,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Text(
                            b.nombre,
                            weight=ft.FontWeight.W_600,
                            size=13,
                            color=ui_theme.DARK_TEXT,
                        ),
                        ft.Text(
                            f"{_fmt_bytes(b.tamano_bytes)} · {b.modificado}",
                            size=12,
                            color=ui_theme.MID_GRAY,
                        ),
                    ],
                ),
                ft.Row(spacing=ui_theme.SPACE_SM, tight=True, controls=acciones),
            ],
        ),
    )


def _panel_config(screen: AdminScreenVM, **cbs) -> ft.Control:
    on_guardar = cbs["on_guardar_hotel"]
    nombre = ft.TextField(label="Nombre del establecimiento", value=screen.hotel_nombre, expand=True)
    moneda = ft.Dropdown(
        label="Moneda",
        width=120,
        options=[ft.dropdown.Option("EUR"), ft.dropdown.Option("USD"), ft.dropdown.Option("GBP")],
        value=screen.hotel_moneda or "EUR",
    )
    return ft.Column(
        spacing=12,
        controls=[
            ui.page_header("Configuración", "Establecimiento y moneda"),
            ui.card_surface(
                ft.Row(
                    controls=[
                        nombre,
                        moneda,
                        ui.primary_button(
                            "Guardar",
                            lambda: on_guardar(nombre.value or "", moneda.value or "EUR"),
                            icon=ft.Icons.SAVE,
                            disabled=screen.mutando,
                        ),
                    ]
                ),
                title="Hotel / instancia",
            ),
        ],
    )


def _catalogo_lista(items: tuple[CatalogoItemVM, ...], *, con_codigo: bool = False) -> list[ft.Control]:
    activos = [i for i in items if i.activo]
    if not activos:
        return [ui.empty_state("Ninguno activo", "Cree el primero abajo.")]
    out: list[ft.Control] = []
    for it in activos:
        label = it.nombre
        if con_codigo and it.codigo:
            label = f"{it.nombre} ({it.codigo})"
        out.append(
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                border=ft.Border(bottom=ft.BorderSide(1, ui_theme.BORDER)),
                content=ft.Text(label, size=13, color=ui_theme.DARK_TEXT),
            )
        )
    return out


def _panel_catalogos(screen: AdminScreenVM, **cbs) -> ft.Control:
    on_dep = cbs["on_crear_departamento"]
    on_cat = cbs["on_crear_categoria"]
    on_ubi = cbs["on_crear_ubicacion"]
    dep_tf = ft.TextField(label="Nuevo departamento", expand=True)
    cat_tf = ft.TextField(label="Nueva categoría", expand=True)
    ubi_tf = ft.TextField(label="Nueva ubicación", expand=True)
    ubi_cod = ft.TextField(label="Código", width=120)

    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        controls=[
            ui.page_header(
                "Catálogos de inventario",
                "Departamentos, categorías y ubicaciones",
            ),
            ui.card_surface(
                *_catalogo_lista(screen.departamentos),
                ft.Row(
                    controls=[
                        dep_tf,
                        ui.primary_button(
                            "Añadir",
                            lambda: on_dep(dep_tf.value or ""),
                            disabled=screen.mutando,
                        ),
                    ]
                ),
                title="Departamentos",
            ),
            ui.card_surface(
                *_catalogo_lista(screen.categorias),
                ft.Row(
                    controls=[
                        cat_tf,
                        ui.primary_button(
                            "Añadir",
                            lambda: on_cat(cat_tf.value or ""),
                            disabled=screen.mutando,
                        ),
                    ]
                ),
                title="Categorías",
            ),
            ui.card_surface(
                *_catalogo_lista(screen.ubicaciones, con_codigo=True),
                ft.Row(
                    controls=[
                        ubi_tf,
                        ubi_cod,
                        ui.primary_button(
                            "Añadir",
                            lambda: on_ubi(ubi_tf.value or "", ubi_cod.value or ""),
                            disabled=screen.mutando,
                        ),
                    ]
                ),
                title="Ubicaciones",
            ),
        ],
    )


def _panel_actividad(screen: AdminScreenVM) -> ft.Control:
    filas: list[ft.Control] = []
    for a in screen.actividades:
        filas.append(
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=8, vertical=8),
                border=ft.Border(bottom=ft.BorderSide(1, ui_theme.BORDER)),
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Column(
                            spacing=2,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(
                                    a.accion,
                                    size=13,
                                    weight=ft.FontWeight.W_600,
                                    color=ui_theme.DARK_TEXT,
                                ),
                                ft.Text(
                                    a.detalle or "—",
                                    size=12,
                                    color=ui_theme.MID_GRAY,
                                ),
                            ],
                        ),
                        ft.Column(
                            spacing=2,
                            tight=True,
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                            controls=[
                                ui.status_chip(a.usuario or "—", tone="neutral"),
                                ft.Text(a.fecha, size=11, color=ui_theme.MID_GRAY),
                            ],
                        ),
                    ],
                ),
            )
        )
    if not filas:
        filas = [
            ui.empty_state(
                "Sin actividad reciente",
                "Las mutaciones administrativas aparecerán aquí.",
            )
        ]
    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        controls=[
            ui.page_header(
                "Actividad",
                "Últimas 50 entradas (solo lectura)",
                actions=[
                    ui.status_chip(f"{len(screen.actividades)} eventos", tone="info"),
                ],
            ),
            ui.card_surface(*filas, title="Registro"),
        ],
    )


def _panel_servidor(screen: AdminScreenVM, **cbs) -> ft.Control:
    on_guardar = cbs["on_guardar_shared_root"]
    path_tf = ft.TextField(
        label="Raíz compartida (UNC o local)",
        value=screen.shared_root_label if screen.shared_root_label != "—" else "",
        hint_text=r"\\servidor\bm-datos  o  D:\BM_shared",
        expand=True,
    )
    return ft.Column(
        spacing=ui_theme.SPACE_MD,
        controls=[
            ui.page_header(
                "Servidor / datos compartidos",
                "Config de cliente (shared_root). No copia datos del hotel.",
                actions=[
                    ui.status_chip(f"Rev. {screen.revision}", tone="neutral"),
                ],
            ),
            ui.card_surface(
                ft.Row(
                    wrap=True,
                    spacing=ui_theme.SPACE_SM,
                    controls=[
                        ui.status_chip(
                            f"Datos: {screen.data_path_label or '—'}",
                            tone="info",
                        ),
                        ui.status_chip(
                            f"Shared: {screen.shared_root_label or '—'}",
                            tone="neutral",
                        ),
                    ],
                ),
                ft.Row(
                    controls=[
                        path_tf,
                        ui.primary_button(
                            "Guardar",
                            lambda: on_guardar(path_tf.value or ""),
                            icon=ft.Icons.SAVE,
                            disabled=screen.mutando,
                        ),
                    ]
                ),
                title="Instancia",
            ),
        ],
    )


def _panel_zona_peligro(screen: AdminScreenVM, **cbs) -> ft.Control:
    if not screen.puede_zona_peligro:
        return ft.Column(
            spacing=ui_theme.SPACE_MD,
            controls=[
                ui.page_header("Zona de peligro", "Solo Dirección"),
                ui.alert_banner(
                    "Solo Dirección puede ver la zona de peligro.",
                    severity="error",
                ),
            ],
        )
    on_ejec = cbs["on_ejecutar_destructiva"]
    controls: list[ft.Control] = [
        ui.page_header(
            "Zona de peligro",
            "Acciones que sustituyen datos operativos",
        ),
        ui.alert_banner(
            "Confirmación reforzada obligatoria. No hay deshacer automático.",
            severity="error",
        ),
    ]
    if not screen.ops_destructivas:
        controls.append(
            ui.empty_state(
                "Sin operaciones destructivas",
                "No hay acciones expuestas en esta instancia.",
            )
        )
        return ft.Column(spacing=ui_theme.SPACE_MD, controls=controls)

    ops: list[ft.Control] = []
    for op in screen.ops_destructivas:
        frase_tf = ft.TextField(
            label=f"Escriba exactamente {op.frase}",
            width=320,
        )
        chk = ft.Checkbox(
            label="Entiendo que se sustituirán todos los datos operativos",
            value=False,
        )
        ops.append(
            ft.Container(
                bgcolor=ui_theme.DANGER_BG,
                padding=ui_theme.SPACE_MD,
                border_radius=ui_theme.RADIUS_MD,
                border=ft.Border.all(1, ui_theme.DANGER),
                content=ft.Column(
                    spacing=ui_theme.SPACE_SM,
                    controls=[
                        ft.Text(
                            op.etiqueta,
                            weight=ft.FontWeight.BOLD,
                            color=ui_theme.DANGER,
                        ),
                        ft.Text(op.nota or "", size=12, color=ui_theme.MID_GRAY),
                        chk,
                        frase_tf,
                        ft.FilledButton(
                            "Ejecutar",
                            style=ft.ButtonStyle(
                                bgcolor=ui_theme.DANGER,
                                color=ui_theme.WHITE,
                            ),
                            disabled=screen.mutando,
                            on_click=lambda _e, oid=op.id, tf=frase_tf, c=chk: on_ejec(
                                oid, tf.value or "", bool(c.value)
                            ),
                        ),
                    ],
                ),
            )
        )
    controls.append(ui.card_surface(*ops, title="Operaciones"))
    return ft.Column(spacing=ui_theme.SPACE_MD, controls=controls)
