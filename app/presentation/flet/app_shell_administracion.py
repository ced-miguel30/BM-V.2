"""Shell Flet de Administración operativa (maestros + backup)."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.presentation.flet.presenters.terminal_administracion_presenter import (
    TerminalAdministracionPresenter,
)
from app.presentation.flet.views.admin_shell_view import (
    build_admin_shell,
    build_bootstrap_admin,
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
        from app.bootstrap import get_container
        from app.core.auth.session import necesita_bootstrap

        screen = self.presenter.screen()
        if not screen.session.authenticated:
            msg = ""
            if screen.feedback and not screen.feedback.ok:
                msg = screen.feedback.mensaje
            data = get_container().app_data_store.get()
            if necesita_bootstrap(data.usuarios):
                content = build_bootstrap_admin(
                    on_bootstrap=self._on_bootstrap,
                    feedback_mensaje=msg,
                    on_volver_menu=self._on_volver_al_menu,
                )
            else:
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
                on_set_compra_albaran=self._on_set_compra_albaran,
                on_generar_backup=self._on_generar_backup,
                on_inspeccionar_backup=self._on_inspeccionar_backup,
                on_proponer_restaurar=self._on_proponer_restaurar,
                on_guardar_hotel=self._on_guardar_hotel,
                on_refresh_datos=self._on_refresh_datos,
                on_guardar_shared_root=self._on_guardar_shared_root,
                on_crear_departamento=self._on_crear_departamento,
                on_crear_categoria=self._on_crear_categoria,
                on_crear_ubicacion=self._on_crear_ubicacion,
                on_ejecutar_destructiva=self._on_ejecutar_destructiva,
                on_exportar_documentos=self._on_exportar_documentos,
                on_proponer_anular_documento=self._on_proponer_anular_documento,
                on_proponer_rectificativa_economica=self._on_proponer_rectificativa_economica,
                on_proponer_rectificativa_stock=self._on_proponer_rectificativa_stock,
                on_adjuntar_archivo=self._on_adjuntar_archivo,
                on_abrir_adjunto=self._on_abrir_adjunto,
                on_analisis_hub=self._on_analisis_hub,
                on_analisis_pestana=self._on_analisis_pestana,
                on_analisis_subtab=self._on_analisis_subtab,
                on_analisis_periodo=self._on_analisis_periodo,
                on_analisis_busqueda=self._on_analisis_busqueda,
                on_analisis_tipo=self._on_analisis_tipo,
                on_analisis_comparacion=self._on_analisis_comparacion,
                on_analisis_export=self._on_analisis_export,
                on_confirmar=self._on_confirmar,
                on_cancelar=self._on_cancelar,
            )
        self._root.content = content
        self.page.update()

    def _on_login(self, login: str, password: str) -> None:
        self.presenter.login(login, password)
        self.refresh()

    def _on_bootstrap(
        self, nombre: str, login: str, password: str, password2: str
    ) -> None:
        self.presenter.bootstrap_direccion(nombre, login, password, password2)
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

    def _on_analisis_hub(self, hub: str) -> None:
        self.presenter.set_analisis_hub(hub)
        self.refresh()

    def _on_analisis_pestana(self, pestana: str) -> None:
        self.presenter.set_analisis_pestana(pestana)
        self.refresh()

    def _on_analisis_subtab(self, subtab: str) -> None:
        self.presenter.set_analisis_subtab(subtab)
        self.refresh()

    def _on_analisis_periodo(self, desde: str, hasta: str) -> None:
        self.presenter.set_analisis_periodo(desde, hasta)
        self.refresh()

    def _on_analisis_busqueda(self, texto: str) -> None:
        self.presenter.set_analisis_busqueda(texto)
        self.refresh()

    def _on_analisis_tipo(self, tipo: str) -> None:
        self.presenter.set_analisis_tipo_filtro(tipo)
        self.refresh()

    def _on_analisis_comparacion(
        self, a_desde: str, a_hasta: str, b_desde: str, b_hasta: str
    ) -> None:
        self.presenter.set_analisis_comparacion(a_desde, a_hasta, b_desde, b_hasta)
        self.refresh()

    def _on_analisis_export(self) -> None:
        self.presenter.exportar_analisis_costes_excel()
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

    def _on_set_compra_cabecera(
        self, proveedor_id: str, referencia: str, tipo: str = ""
    ) -> None:
        self.presenter.set_compra_cabecera(proveedor_id, referencia, tipo)
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

    def _on_set_compra_albaran(self, albaran_id: str) -> None:
        self.presenter.set_compra_albaran_conciliacion(albaran_id)
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

    def _on_refresh_datos(self) -> None:
        self.presenter.refresh_datos()
        self.refresh()

    def _on_guardar_shared_root(self, path: str) -> None:
        self.presenter.guardar_shared_root(path)
        self.refresh()

    def _on_crear_departamento(self, nombre: str) -> None:
        self.presenter.crear_departamento_catalogo(nombre)
        self.refresh()

    def _on_crear_categoria(self, nombre: str) -> None:
        self.presenter.crear_categoria_catalogo(nombre)
        self.refresh()

    def _on_crear_ubicacion(self, nombre: str, codigo: str) -> None:
        self.presenter.crear_ubicacion_catalogo(nombre, codigo)
        self.refresh()

    def _on_ejecutar_destructiva(
        self, op_id: str, frase: str, checkbox: bool
    ) -> None:
        self.presenter.ejecutar_op_destructiva(op_id, frase, checkbox)
        self.refresh()

    def _on_exportar_documentos(self) -> None:
        self.presenter.exportar_documentos_csv()
        self.refresh()

    def _on_proponer_anular_documento(self, documento_id: str, motivo: str) -> None:
        self.presenter.proponer_anular_documento(documento_id, motivo)
        self.refresh()

    def _on_proponer_rectificativa_economica(
        self, documento_id: str, motivo: str
    ) -> None:
        self.presenter.proponer_rectificativa_economica(documento_id, motivo)
        self.refresh()

    def _on_proponer_rectificativa_stock(
        self, documento_id: str, motivo: str
    ) -> None:
        self.presenter.proponer_rectificativa_stock(documento_id, motivo)
        self.refresh()

    def _on_adjuntar_archivo(self, documento_id: str, ruta: str) -> None:
        self.presenter.adjuntar_archivo_desde_ruta(documento_id, ruta)
        self.refresh()

    def _on_abrir_adjunto(self, archivo_id: str) -> None:
        self.presenter.abrir_adjunto(archivo_id)
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
