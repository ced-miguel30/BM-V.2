"""Shell Flet de Administración operativa (maestros + backup)."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.presentation.flet.presenters.terminal_administracion_presenter import (
    TerminalAdministracionPresenter,
)
from app.presentation.flet.views.admin_shell_view import (
    build_admin_shell,
    build_login_admin,
)


class TerminalAdministracionShell:
    def __init__(
        self,
        page: ft.Page,
        presenter: TerminalAdministracionPresenter | None = None,
        *,
        on_volver_al_menu: Callable[[], None] | None = None,
    ):
        self.page = page
        self.presenter = presenter or TerminalAdministracionPresenter()
        self._on_volver_al_menu = on_volver_al_menu
        self._root = ft.Container(expand=True)

    def mount(self) -> None:
        page = self.page
        page.title = "BM — Administración"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.padding = 0
        page.bgcolor = ft.Colors.GREY_100
        page.on_resize = lambda _e: self.refresh()
        page.add(self._root)
        self.refresh()

    def refresh(self) -> None:
        screen = self.presenter.screen()
        if not screen.session.authenticated:
            msg = ""
            if screen.feedback and not screen.feedback.ok:
                msg = screen.feedback.mensaje
            content = build_login_admin(
                on_login=self._on_login,
                feedback_mensaje=msg,
                on_volver_menu=self._on_volver_al_menu,
            )
        else:
            content = build_admin_shell(
                screen,
                on_logout=self._on_logout,
                on_volver_menu=self._on_volver_al_menu,
                on_seccion=self._on_seccion,
                on_filtro=self._on_filtro,
                on_proponer_crear=self._on_crear_responsable,
                on_proponer_renombrar=self._on_renombrar,
                on_proponer_desactivar=self._on_desactivar,
                on_proponer_reactivar=self._on_reactivar,
                on_crear_producto=self._on_crear_producto,
                on_desactivar_producto=self._on_desactivar_producto,
                on_reactivar_producto=self._on_reactivar_producto,
                on_crear_receta=self._on_crear_receta,
                on_desactivar_receta=self._on_desactivar_receta,
                on_reactivar_receta=self._on_reactivar_receta,
                on_crear_usuario=self._on_crear_usuario,
                on_editar_usuario=self._on_editar_usuario,
                on_cambiar_rol=self._on_cambiar_rol,
                on_desactivar_usuario=self._on_desactivar_usuario,
                on_reactivar_usuario=self._on_reactivar_usuario,
                on_restablecer_password=self._on_restablecer_password,
                on_registrar_lote=self._on_registrar_lote,
                on_crear_proveedor=self._on_crear_proveedor,
                on_editar_proveedor=self._on_editar_proveedor,
                on_desactivar_proveedor=self._on_desactivar_proveedor,
                on_reactivar_proveedor=self._on_reactivar_proveedor,
                on_set_compra_cabecera=self._on_set_compra_cabecera,
                on_añadir_linea_compra=self._on_añadir_linea_compra,
                on_quitar_linea_compra=self._on_quitar_linea_compra,
                on_guardar_borrador_compra=self._on_guardar_borrador_compra,
                on_confirmar_compra=self._on_confirmar_compra,
                on_limpiar_borrador_compra=self._on_limpiar_borrador_compra,
                on_generar_backup=self._on_generar_backup,
                on_inspeccionar_backup=self._on_inspeccionar_backup,
                on_proponer_restaurar=self._on_proponer_restaurar,
                on_guardar_hotel=self._on_guardar_hotel,
                on_confirmar=self._on_confirmar,
                on_cancelar=self._on_cancelar,
            )
        self._root.content = content
        self.page.update()

    def _on_login(self, login: str, password: str) -> None:
        self.presenter.login(login, password)
        self.refresh()

    def _on_logout(self) -> None:
        self.presenter.logout()
        self.refresh()

    def _on_seccion(self, seccion: str) -> None:
        self.presenter.set_seccion(seccion)
        self.refresh()

    def _on_filtro(self, texto: str) -> None:
        self.presenter.set_filtro(texto)
        self.refresh()

    def _on_crear_responsable(self, nombre: str) -> None:
        self.presenter.proponer_creacion(nombre)
        self.refresh()

    def _on_renombrar(self, rid: str, nombre: str) -> None:
        self.presenter.proponer_renombre(rid, nombre)
        self.refresh()

    def _on_desactivar(self, rid: str) -> None:
        self.presenter.proponer_desactivacion(rid)
        self.refresh()

    def _on_reactivar(self, rid: str) -> None:
        self.presenter.proponer_reactivacion(rid)
        self.refresh()

    def _on_crear_producto(
        self,
        nombre: str,
        unidad: str,
        stock_minimo: float | None,
        codigo: str,
        tipo_articulo: str,
        es_bebida: bool,
        servicios: list[str],
    ) -> None:
        self.presenter.crear_producto(
            nombre,
            unidad,
            stock_minimo,
            codigo,
            tipo_articulo,
            es_bebida=es_bebida,
            servicios_disponibles=servicios,
        )
        self.refresh()

    def _on_desactivar_producto(self, pid: str) -> None:
        self.presenter.proponer_desactivar_producto(pid)
        self.refresh()

    def _on_reactivar_producto(self, pid: str) -> None:
        self.presenter.proponer_reactivar_producto(pid)
        self.refresh()

    def _on_crear_receta(
        self,
        nombre: str,
        ingredientes: list[tuple[str, float]],
        categoria: str,
        porciones: float | None,
        servicios: list[str],
    ) -> None:
        self.presenter.crear_receta(
            nombre,
            ingredientes,
            categoria,
            porciones,
            servicios_disponibles=servicios,
        )
        self.refresh()

    def _on_desactivar_receta(self, rid: str) -> None:
        self.presenter.proponer_desactivar_receta(rid)
        self.refresh()

    def _on_reactivar_receta(self, rid: str) -> None:
        self.presenter.proponer_reactivar_receta(rid)
        self.refresh()

    def _on_crear_usuario(
        self, nombre: str, rol: str, login: str, password: str
    ) -> None:
        self.presenter.crear_usuario(nombre, rol, login=login, password=password)
        self.refresh()

    def _on_editar_usuario(self, uid: str, nombre: str) -> None:
        self.presenter.editar_usuario(uid, nombre)
        self.refresh()

    def _on_cambiar_rol(self, uid: str, rol: str) -> None:
        self.presenter.cambiar_rol_usuario(uid, rol)
        self.refresh()

    def _on_desactivar_usuario(self, uid: str) -> None:
        self.presenter.proponer_desactivar_usuario(uid)
        self.refresh()

    def _on_reactivar_usuario(self, uid: str) -> None:
        self.presenter.proponer_reactivar_usuario(uid)
        self.refresh()

    def _on_restablecer_password(self, uid: str, password: str) -> None:
        self.presenter.restablecer_password(uid, password)
        self.refresh()

    def _on_registrar_lote(
        self,
        producto_id: str,
        cantidad: float,
        precio_total: float,
        marca: str,
        ubicacion: str,
    ) -> None:
        self.presenter.registrar_lote_inicial(
            producto_id,
            cantidad,
            precio_total,
            marca_proveedor=marca,
            ubicacion_destino_id=ubicacion,
        )
        self.refresh()

    def _on_crear_proveedor(
        self,
        nombre_fiscal: str,
        codigo: str,
        nombre_comercial: str,
        nif_cif: str,
    ) -> None:
        self.presenter.crear_proveedor(
            nombre_fiscal,
            codigo,
            nombre_comercial=nombre_comercial,
            nif_cif=nif_cif,
        )
        self.refresh()

    def _on_editar_proveedor(
        self, proveedor_id: str, nombre_fiscal: str, codigo: str
    ) -> None:
        self.presenter.editar_proveedor(
            proveedor_id,
            nombre_fiscal=nombre_fiscal,
            codigo=codigo,
        )
        self.refresh()

    def _on_desactivar_proveedor(self, proveedor_id: str) -> None:
        self.presenter.proponer_desactivar_proveedor(proveedor_id)
        self.refresh()

    def _on_reactivar_proveedor(self, proveedor_id: str) -> None:
        self.presenter.proponer_reactivar_proveedor(proveedor_id)
        self.refresh()

    def _on_set_compra_cabecera(self, proveedor_id: str, referencia: str) -> None:
        self.presenter.set_compra_cabecera(proveedor_id, referencia)
        self.refresh()

    def _on_añadir_linea_compra(
        self, producto_id: str, cantidad: float, precio_unitario: float
    ) -> None:
        self.presenter.añadir_linea_compra(producto_id, cantidad, precio_unitario)
        self.refresh()

    def _on_quitar_linea_compra(self, index: int) -> None:
        self.presenter.quitar_linea_compra(index)
        self.refresh()

    def _on_guardar_borrador_compra(self) -> None:
        self.presenter.guardar_borrador_compra()
        self.refresh()

    def _on_confirmar_compra(self) -> None:
        self.presenter.confirmar_compra_borrador()
        self.refresh()

    def _on_limpiar_borrador_compra(self) -> None:
        self.presenter.limpiar_borrador_compra()
        self.refresh()

    def _on_generar_backup(self) -> None:
        self.presenter.generar_backup()
        self.refresh()

    def _on_inspeccionar_backup(self, ruta: str) -> None:
        self.presenter.inspeccionar_backup_archivo(ruta)
        self.refresh()

    def _on_proponer_restaurar(self, ruta: str, confirmacion: str) -> None:
        self.presenter.proponer_restaurar_backup(ruta, confirmacion)
        self.refresh()

    def _on_guardar_hotel(self, nombre: str, moneda: str) -> None:
        self.presenter.guardar_hotel(nombre, moneda)
        self.refresh()

    def _on_confirmar(self) -> None:
        self.presenter.confirmar_pendiente()
        self.refresh()

    def _on_cancelar(self) -> None:
        self.presenter.cancelar_pendiente()
        self.refresh()


def attach_terminal_administracion(page: ft.Page) -> TerminalAdministracionShell:
    shell = TerminalAdministracionShell(page)
    shell.mount()
    return shell
