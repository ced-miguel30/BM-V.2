"""Vista Administración operativa — maestros, responsables, backup."""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.presentation.flet.admin_viewmodels import (
    ADMIN_SECCION_LABEL,
    ADMIN_SECCIONES,
    AdminScreenVM,
    BackupItemVM,
    CompraLineaVM,
    ProductoAdminVM,
    ProveedorAdminVM,
    RecetaAdminVM,
    ResponsableMermaVM,
    UsuarioAdminVM,
)
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
    err = (
        ft.Text(feedback_mensaje, color=ft.Colors.RED_700)
        if feedback_mensaje
        else ft.Container()
    )

    def _submit(_e=None) -> None:
        on_login(login_tf.value or "", pass_tf.value or "")

    pass_tf.on_submit = _submit
    controls: list[ft.Control] = [
        ft.Text(
            "Administración",
            size=32,
            weight=ft.FontWeight.BOLD,
        ),
        ft.Text(
            "Maestros operativos: productos, recetas, usuarios, responsables, "
            "proveedores, compras, inventario inicial y backup.",
            size=14,
            color=ft.Colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.CENTER,
            width=420,
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
            "Sin Streamlit para operación diaria. Costes avanzados siguen fuera de alcance.",
            size=12,
            color=ft.Colors.OUTLINE,
            text_align=ft.TextAlign.CENTER,
            width=420,
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
    on_set_compra_cabecera: Callable[[str, str], None],
    on_añadir_linea_compra: Callable[..., None],
    on_quitar_linea_compra: Callable[[int], None],
    on_guardar_borrador_compra: Callable[[], None],
    on_confirmar_compra: Callable[[], None],
    on_limpiar_borrador_compra: Callable[[], None],
    on_generar_backup: Callable[[], None],
    on_inspeccionar_backup: Callable[[str], None],
    on_proponer_restaurar: Callable[[str, str], None],
    on_guardar_hotel: Callable[[str, str], None],
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
                            "Administración",
                            color=ft.Colors.WHITE,
                            size=20,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            f"{screen.session.actor_label} · {screen.session.role}"
                            + (f" · {screen.hotel_nombre}" if screen.hotel_nombre else ""),
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

    pending_box = _pending_box(screen, on_confirmar=on_confirmar, on_cancelar=on_cancelar)

    selected = (
        ADMIN_SECCIONES.index(screen.seccion)
        if screen.seccion in ADMIN_SECCIONES
        else 0
    )
    rail = ft.NavigationRail(
        selected_index=selected,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=88,
        min_extended_width=180,
        destinations=[
            ft.NavigationRailDestination(
                icon=ft.Icons.HOME_OUTLINED,
                selected_icon=ft.Icons.HOME,
                label=ADMIN_SECCION_LABEL[s],
            )
            for s in ADMIN_SECCIONES
        ],
        on_change=lambda e: on_seccion(ADMIN_SECCIONES[int(e.control.selected_index or 0)]),
    )

    panel = _panel_for_seccion(
        screen,
        on_filtro=on_filtro,
        on_proponer_crear=on_proponer_crear,
        on_proponer_renombrar=on_proponer_renombrar,
        on_proponer_desactivar=on_proponer_desactivar,
        on_proponer_reactivar=on_proponer_reactivar,
        on_crear_producto=on_crear_producto,
        on_desactivar_producto=on_desactivar_producto,
        on_reactivar_producto=on_reactivar_producto,
        on_crear_receta=on_crear_receta,
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
        on_quitar_linea_compra=on_quitar_linea_compra,
        on_guardar_borrador_compra=on_guardar_borrador_compra,
        on_confirmar_compra=on_confirmar_compra,
        on_limpiar_borrador_compra=on_limpiar_borrador_compra,
        on_generar_backup=on_generar_backup,
        on_inspeccionar_backup=on_inspeccionar_backup,
        on_proponer_restaurar=on_proponer_restaurar,
        on_guardar_hotel=on_guardar_hotel,
    )

    body = ft.Row(
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[
            rail,
            ft.VerticalDivider(width=1),
            ft.Container(
                expand=True,
                padding=16,
                content=ft.Column(
                    expand=True,
                    spacing=12,
                    scroll=ft.ScrollMode.AUTO,
                    controls=[pending_box, panel],
                ),
            ),
        ],
    )

    return ft.Column(
        expand=True,
        spacing=12,
        controls=[header, feedback, body],
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


def _panel_for_seccion(screen: AdminScreenVM, **cbs) -> ft.Control:
    sec = screen.seccion
    if sec == "productos":
        return _panel_productos(screen, **cbs)
    if sec == "recetas":
        return _panel_recetas(screen, **cbs)
    if sec == "usuarios":
        return _panel_usuarios(screen, **cbs)
    if sec == "responsables":
        return _panel_responsables(screen, **cbs)
    if sec == "proveedores":
        return _panel_proveedores(screen, **cbs)
    if sec == "compras":
        return _panel_compras(screen, **cbs)
    if sec == "inventario_inicial":
        return _panel_inventario(screen, **cbs)
    if sec == "backup":
        return _panel_backup(screen, **cbs)
    if sec == "configuracion":
        return _panel_config(screen, **cbs)
    return _panel_inicio(screen)


def _panel_inicio(screen: AdminScreenVM) -> ft.Control:
    return ft.Column(
        spacing=10,
        controls=[
            ft.Text("Inicio", size=18, weight=ft.FontWeight.BOLD),
            ft.Text(
                "Seleccione una sección en el menú lateral para gestionar maestros "
                "operativos sin abrir Streamlit.",
                size=14,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Text(
                f"Productos: {len(screen.productos)} · Recetas: {len(screen.recetas)} · "
                f"Usuarios: {len(screen.usuarios)} · Responsables: {len(screen.responsables)} · "
                f"Proveedores: {len(screen.proveedores)} · Backups: {len(screen.backups)}",
                size=13,
            ),
        ],
    )


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
    nombre = ft.TextField(label="Nombre", expand=True)
    codigo = ft.TextField(label="Código", width=140)
    unidad = ft.Dropdown(
        label="Unidad",
        width=120,
        options=[ft.dropdown.Option(u) for u in screen.unidades],
        value=screen.unidades[0] if screen.unidades else None,
    )
    stock = ft.TextField(label="Stock mín.", width=110, value="0")
    tipo = ft.Dropdown(
        label="Tipo artículo",
        width=160,
        options=[ft.dropdown.Option(t) for t in screen.tipos_articulo],
        value="consumible" if "consumible" in screen.tipos_articulo else None,
    )
    es_bebida = ft.Checkbox(label="Es bebida", value=False)
    servicios = ft.TextField(
        label="Servicios (coma)",
        hint_text="desayuno,comida,cena,bebidas",
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

    lista = [_producto_row(p, screen.mutando or screen.pending is not None, on_des, on_rea) for p in screen.productos]
    if not lista:
        lista = [ft.Text("No hay productos.", color=ft.Colors.OUTLINE)]

    return ft.Column(
        spacing=12,
        controls=[
            ft.Text("Productos", size=18, weight=ft.FontWeight.BOLD),
            ft.Row(controls=[nombre, codigo, unidad, stock, tipo]),
            ft.Row(controls=[es_bebida, servicios, ft.FilledButton("Crear", disabled=screen.mutando, on_click=_crear)]),
            _filtro_row(screen, on_filtro),
            *lista,
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
                style=ft.ButtonStyle(color=ft.Colors.RED_700),
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
        bgcolor=ft.Colors.WHITE if p.activo else ft.Colors.BLUE_GREY_50,
        padding=12,
        border_radius=8,
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_300),
        content=ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Text(f"{p.nombre} ({p.codigo or 'sin código'})", weight=ft.FontWeight.BOLD),
                ft.Text(
                    f"{p.unidad} · mín {p.stock_minimo:g} · {p.tipo_articulo or 'sin clasificar'}"
                    + (" · bebida" if p.es_bebida else "")
                    + (" · activo" if p.activo else " · inactivo"),
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Row(controls=acciones),
            ],
        ),
    )


def _panel_recetas(screen: AdminScreenVM, **cbs) -> ft.Control:
    on_filtro = cbs["on_filtro"]
    on_crear = cbs["on_crear_receta"]
    on_des = cbs["on_desactivar_receta"]
    on_rea = cbs["on_reactivar_receta"]
    nombre = ft.TextField(label="Nombre receta", expand=True)
    categoria = ft.Dropdown(
        label="Categoría",
        width=160,
        options=[ft.dropdown.Option(c) for c in screen.categorias_receta],
        value=screen.categorias_receta[0] if screen.categorias_receta else None,
    )
    porciones = ft.TextField(label="Porciones", width=110, value="1")
    prod_opts = [
        ft.dropdown.Option(key=p.id, text=p.nombre)
        for p in screen.productos
        if p.activo
    ]
    ing_prod = ft.Dropdown(label="Ingrediente", options=prod_opts, expand=True)
    ing_cant = ft.TextField(label="Cantidad", width=110, value="1")
    servicios = ft.TextField(
        label="Servicios (coma)",
        hint_text="desayuno,comida",
        expand=True,
    )

    def _crear(_e=None) -> None:
        try:
            porc = float((porciones.value or "1").replace(",", "."))
        except ValueError:
            porc = None
        try:
            cant = float((ing_cant.value or "0").replace(",", "."))
        except ValueError:
            cant = 0.0
        pid = ing_prod.value or ""
        serv = [s.strip() for s in (servicios.value or "").split(",") if s.strip()]
        on_crear(nombre.value or "", [(pid, cant)], categoria.value or "", porc, serv)

    lista = [
        _receta_row(r, screen.mutando or screen.pending is not None, on_des, on_rea)
        for r in screen.recetas
    ]
    if not lista:
        lista = [ft.Text("No hay recetas.", color=ft.Colors.OUTLINE)]

    return ft.Column(
        spacing=12,
        controls=[
            ft.Text("Recetas", size=18, weight=ft.FontWeight.BOLD),
            ft.Row(controls=[nombre, categoria, porciones]),
            ft.Row(controls=[ing_prod, ing_cant, servicios]),
            ft.FilledButton("Crear receta", disabled=screen.mutando, on_click=_crear),
            _filtro_row(screen, on_filtro),
            *lista,
        ],
    )


def _receta_row(
    r: RecetaAdminVM,
    disabled: bool,
    on_des: Callable[[str], None],
    on_rea: Callable[[str], None],
) -> ft.Control:
    acciones = []
    if r.activo:
        acciones.append(
            ft.TextButton(
                "Desactivar",
                disabled=disabled,
                style=ft.ButtonStyle(color=ft.Colors.RED_700),
                on_click=lambda _e, rid=r.id: on_des(rid),
            )
        )
    else:
        acciones.append(
            ft.TextButton(
                "Reactivar",
                disabled=disabled,
                on_click=lambda _e, rid=r.id: on_rea(rid),
            )
        )
    return ft.Container(
        bgcolor=ft.Colors.WHITE if r.activo else ft.Colors.BLUE_GREY_50,
        padding=12,
        border_radius=8,
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_300),
        content=ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Text(r.nombre, weight=ft.FontWeight.BOLD),
                ft.Text(
                    f"{r.categoria} · {r.n_ingredientes} ing. · "
                    f"porciones {r.porciones_estandar if r.porciones_estandar is not None else '—'}"
                    + (" · activa" if r.activo else " · inactiva"),
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Row(controls=acciones),
            ],
        ),
    )


def _panel_usuarios(screen: AdminScreenVM, **cbs) -> ft.Control:
    if not screen.puede_gestionar_usuarios:
        return ft.Text("Sin permiso GESTIONAR_USUARIOS.", color=ft.Colors.RED_700)

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

    lista = [
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

    return ft.Column(
        spacing=12,
        controls=[
            ft.Text("Usuarios", size=18, weight=ft.FontWeight.BOLD),
            ft.Row(controls=[nombre, login, password, rol]),
            ft.FilledButton("Crear usuario", disabled=screen.mutando, on_click=_crear),
            _filtro_row(screen, on_filtro),
            *lista,
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
        ft.OutlinedButton(
            "Renombrar",
            disabled=disabled,
            on_click=lambda _e, uid=u.id, tf=rename: on_editar(uid, tf.value or ""),
        ),
        ft.OutlinedButton(
            "Rol",
            disabled=disabled,
            on_click=lambda _e, uid=u.id, dd=rol_dd: on_rol(uid, dd.value or ""),
        ),
        ft.OutlinedButton(
            "Password",
            disabled=disabled,
            on_click=lambda _e, uid=u.id, tf=pwd: on_pwd(uid, tf.value or ""),
        ),
    ]
    if u.activo:
        acciones.append(
            ft.TextButton(
                "Desactivar",
                disabled=disabled,
                style=ft.ButtonStyle(color=ft.Colors.RED_700),
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
        bgcolor=ft.Colors.WHITE if u.activo else ft.Colors.BLUE_GREY_50,
        padding=12,
        border_radius=8,
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_300),
        content=ft.Column(
            spacing=6,
            tight=True,
            controls=[
                ft.Text(f"{u.nombre} · {u.login} · {u.rol}", weight=ft.FontWeight.BOLD),
                ft.Row(controls=[rename, rol_dd, pwd]),
                ft.Row(controls=acciones),
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
            ft.Text(
                "No hay responsables con ese filtro."
                if screen.filtro
                else "No hay responsables. Cree el primero.",
                color=ft.Colors.ON_SURFACE,
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

    return ft.Column(
        spacing=12,
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
            _filtro_row(screen, on_filtro),
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
            on_click=lambda _e, rid=r.id, tf=rename_tf: on_renombrar(rid, tf.value or ""),
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
                                estado,
                                color=ft.Colors.WHITE,
                                size=12,
                                weight=ft.FontWeight.W_600,
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
        lista = [ft.Text("No hay proveedores.", color=ft.Colors.OUTLINE)]

    return ft.Column(
        spacing=12,
        controls=[
            ft.Text("Proveedores", size=18, weight=ft.FontWeight.BOLD),
            ft.Row(controls=[nombre, codigo]),
            ft.Row(
                controls=[
                    comercial,
                    nif,
                    ft.FilledButton("Crear", disabled=screen.mutando, on_click=_crear),
                ]
            ),
            _filtro_row(screen, on_filtro),
            *lista,
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
    estado = "Activo" if p.activo else "Inactivo"
    chip_bg = ft.Colors.TEAL_700 if p.activo else ft.Colors.BLUE_GREY_600
    acciones: list[ft.Control] = [
        ft.OutlinedButton(
            "Guardar",
            disabled=disabled,
            on_click=lambda _e, pid=p.id, nf=nombre_tf, cf=codigo_tf: on_editar(
                pid, nf.value or "", cf.value or ""
            ),
        ),
    ]
    if p.activo:
        acciones.append(
            ft.TextButton(
                "Desactivar",
                disabled=disabled,
                style=ft.ButtonStyle(color=ft.Colors.RED_700),
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
        bgcolor=ft.Colors.WHITE if p.activo else ft.Colors.BLUE_GREY_50,
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
                        ft.Text(
                            p.nombre_comercial or p.nombre_fiscal,
                            size=16,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Container(
                            bgcolor=chip_bg,
                            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                            border_radius=12,
                            content=ft.Text(
                                estado,
                                color=ft.Colors.WHITE,
                                size=12,
                                weight=ft.FontWeight.W_600,
                            ),
                        ),
                    ],
                ),
                ft.Text(
                    f"Id: {p.id} · NIF: {p.nif_cif or '—'}",
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Row(controls=[nombre_tf, codigo_tf]),
                ft.Row(controls=acciones),
            ],
        ),
    )


def _panel_compras(screen: AdminScreenVM, **cbs) -> ft.Control:
    on_set_cab = cbs["on_set_compra_cabecera"]
    on_add = cbs["on_añadir_linea_compra"]
    on_quitar = cbs["on_quitar_linea_compra"]
    on_guardar = cbs["on_guardar_borrador_compra"]
    on_confirmar = cbs["on_confirmar_compra"]
    on_limpiar = cbs["on_limpiar_borrador_compra"]

    activos_prov = [p for p in screen.proveedores if p.activo]
    activos_prod = [p for p in screen.productos if p.activo]
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
    )
    ref = ft.TextField(
        label="Referencia externa",
        value=screen.compra_referencia,
        width=180,
    )
    prod = ft.Dropdown(
        label="Producto",
        options=[
            ft.dropdown.Option(key=p.id, text=f"{p.nombre} ({p.unidad})")
            for p in activos_prod
        ],
        expand=True,
    )
    cantidad = ft.TextField(label="Cantidad", width=110, value="1")
    precio = ft.TextField(label="Precio unitario", width=140, value="0")

    def _aplicar_cab(_e=None) -> None:
        on_set_cab(prov.value or "", ref.value or "")

    def _add(_e=None) -> None:
        on_set_cab(prov.value or "", ref.value or "")
        try:
            cant = float((cantidad.value or "0").replace(",", "."))
        except ValueError:
            cant = 0.0
        try:
            prec = float((precio.value or "0").replace(",", "."))
        except ValueError:
            prec = 0.0
        on_add(prod.value or "", cant, prec)

    lineas: list[ft.Control] = []
    for i, ln in enumerate(screen.compra_lineas):
        lineas.append(_compra_linea_row(i, ln, on_quitar, disabled=screen.mutando))
    if not lineas:
        lineas = [ft.Text("Sin líneas en el borrador.", color=ft.Colors.OUTLINE)]

    doc_info = (
        f"Borrador guardado: {screen.compra_documento_id}"
        if screen.compra_documento_id
        else "Borrador aún no persistido."
    )

    return ft.Column(
        spacing=12,
        controls=[
            ft.Text("Compras", size=18, weight=ft.FontWeight.BOLD),
            ft.Text(
                "Flujo productivo: borrador → confirmar (crea lotes/movimientos).",
                size=13,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Row(
                controls=[
                    prov,
                    ref,
                    ft.OutlinedButton("Aplicar cabecera", on_click=_aplicar_cab),
                ]
            ),
            ft.Row(controls=[prod, cantidad, precio]),
            ft.Row(
                controls=[
                    ft.FilledButton(
                        "Añadir línea",
                        disabled=screen.mutando,
                        on_click=_add,
                    ),
                    ft.OutlinedButton(
                        "Guardar borrador",
                        disabled=screen.mutando,
                        on_click=lambda _e: on_guardar(),
                    ),
                    ft.FilledButton(
                        "Confirmar compra",
                        disabled=screen.mutando,
                        on_click=lambda _e: on_confirmar(),
                    ),
                    ft.TextButton(
                        "Limpiar",
                        disabled=screen.mutando,
                        on_click=lambda _e: on_limpiar(),
                    ),
                ]
            ),
            ft.Text(doc_info, size=12, color=ft.Colors.OUTLINE),
            *lineas,
        ],
    )


def _compra_linea_row(
    index: int,
    ln: CompraLineaVM,
    on_quitar: Callable[[int], None],
    *,
    disabled: bool,
) -> ft.Control:
    return ft.Container(
        bgcolor=ft.Colors.WHITE,
        padding=12,
        border_radius=8,
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_300),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Text(
                    f"{ln.nombre} · cant. {ln.cantidad} · p.u. {ln.precio_unitario}",
                    size=14,
                ),
                ft.TextButton(
                    "Quitar",
                    disabled=disabled,
                    on_click=lambda _e, i=index: on_quitar(i),
                ),
            ],
        ),
    )


def _panel_inventario(screen: AdminScreenVM, **cbs) -> ft.Control:
    on_registrar = cbs["on_registrar_lote"]
    activos = [p for p in screen.productos if p.activo]
    prod = ft.Dropdown(
        label="Producto",
        options=[ft.dropdown.Option(key=p.id, text=f"{p.nombre} ({p.unidad})") for p in activos],
        expand=True,
    )
    cantidad = ft.TextField(label="Cantidad", width=120, value="1")
    precio = ft.TextField(label="Precio total", width=140, value="1")
    marca = ft.TextField(label="Marca / proveedor", expand=True)

    def _go(_e=None) -> None:
        try:
            cant = float((cantidad.value or "0").replace(",", "."))
        except ValueError:
            cant = 0.0
        try:
            prec = float((precio.value or "0").replace(",", "."))
        except ValueError:
            prec = 0.0
        on_registrar(prod.value or "", cant, prec, marca.value or "", "")

    return ft.Column(
        spacing=12,
        controls=[
            ft.Text("Inventario inicial", size=18, weight=ft.FontWeight.BOLD),
            ft.Text(
                "Alta de lote vía registrar_lote. El precio total solo se usa aquí.",
                size=13,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Row(controls=[prod, cantidad, precio]),
            ft.Row(
                controls=[
                    marca,
                    ft.FilledButton(
                        "Registrar lote",
                        disabled=screen.mutando,
                        on_click=_go,
                    ),
                ]
            ),
        ],
    )


def _panel_backup(screen: AdminScreenVM, **cbs) -> ft.Control:
    on_gen = cbs["on_generar_backup"]
    on_insp = cbs["on_inspeccionar_backup"]
    on_rest = cbs["on_proponer_restaurar"]
    confirm = ft.TextField(
        label="Confirmación restauración",
        hint_text="Escriba RESTAURAR",
        width=220,
    )
    controls: list[ft.Control] = [
        ft.Text("Backup", size=18, weight=ft.FontWeight.BOLD),
        ft.FilledButton(
            "Generar backup ZIP",
            icon=ft.Icons.BACKUP,
            disabled=screen.mutando or not screen.puede_exportar_backup,
            on_click=lambda _e: on_gen(),
        ),
    ]
    if screen.inspeccion_backup:
        controls.append(ft.Text(screen.inspeccion_backup, size=12))
    if not screen.backups:
        controls.append(ft.Text("No hay backups en la carpeta local.", color=ft.Colors.OUTLINE))
    else:
        for b in screen.backups:
            controls.append(
                _backup_row(
                    b,
                    screen=screen,
                    confirm_tf=confirm,
                    on_insp=on_insp,
                    on_rest=on_rest,
                )
            )
    if screen.puede_restaurar_backup:
        controls.append(confirm)
    else:
        controls.append(
            ft.Text(
                "Restaurar requiere Dirección (RESTAURAR_BACKUP).",
                size=12,
                color=ft.Colors.OUTLINE,
            )
        )
    return ft.Column(spacing=12, controls=controls)


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
                ft.OutlinedButton(
                    "Inspeccionar",
                    disabled=screen.mutando,
                    on_click=lambda _e, ruta=b.ruta: on_insp(ruta),
                ),
                ft.TextButton(
                    "Restaurar…",
                    disabled=screen.mutando or screen.pending is not None,
                    style=ft.ButtonStyle(color=ft.Colors.RED_700),
                    on_click=lambda _e, ruta=b.ruta, tf=confirm_tf: on_rest(
                        ruta, tf.value or ""
                    ),
                ),
            ]
        )
    return ft.Container(
        bgcolor=ft.Colors.WHITE,
        padding=12,
        border_radius=8,
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_300),
        content=ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Text(b.nombre, weight=ft.FontWeight.BOLD),
                ft.Text(
                    f"{b.tamano_bytes} bytes · {b.modificado}",
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Row(controls=acciones) if acciones else ft.Container(),
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
            ft.Text("Configuración", size=18, weight=ft.FontWeight.BOLD),
            ft.Row(
                controls=[
                    nombre,
                    moneda,
                    ft.FilledButton(
                        "Guardar",
                        disabled=screen.mutando,
                        on_click=lambda _e: on_guardar(nombre.value or "", moneda.value or "EUR"),
                    ),
                ]
            ),
        ],
    )
