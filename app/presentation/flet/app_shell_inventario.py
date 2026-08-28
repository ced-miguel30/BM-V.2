"""Shell Flet de Terminal Inventario."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.presentation.flet.presenters.terminal_inventario_presenter import (
    TerminalInventarioPresenter,
)
from app.presentation.flet.views.inventario_shell_view import (
    build_inventario_shell,
    build_login_inventario,
)


class TerminalInventarioShell:
    def __init__(
        self,
        page: ft.Page,
        presenter: TerminalInventarioPresenter | None = None,
        *,
        on_volver_al_menu: Callable[[], None] | None = None,
    ):
        self.page = page
        self.presenter = presenter or TerminalInventarioPresenter()
        self._on_volver_al_menu = on_volver_al_menu
        self._root = ft.Container(expand=True)

    def mount(self) -> None:
        page = self.page
        from app.presentation.flet.theme import apply_page_theme, APP_NAME

        apply_page_theme(page, title=f"{APP_NAME} — Terminal Inventario")
        page.on_resize = lambda _e: self.refresh()
        page.add(self._root)
        self.refresh()

    def refresh(self) -> None:
        screen = self.presenter.screen()
        narrow = (self.page.width or 900) < 720
        on_volver = (
            self._on_volver_wrapped if self._on_volver_al_menu is not None else None
        )
        if not screen.session.authenticated:
            content = build_login_inventario(
                on_enter=self._on_enter,
                on_volver_menu=on_volver,
            )
        else:
            content = build_inventario_shell(
                screen,
                on_espacio=self._on_espacio,
                on_logout=self._on_logout,
                on_volver_menu=on_volver,
                on_alerta_estado=self._on_alerta,
                on_caducidad_a_merma=self._on_caducidad,
                on_anadir_merma=self._on_anadir_merma,
                on_seleccionar_responsable=self._on_responsable,
                on_vaciar_merma=self._on_vaciar_merma,
                on_confirmar_merma=self._on_confirmar_merma,
                on_preview_ajuste=self._on_preview_ajuste,
                on_confirmar_ajuste=self._on_confirmar_ajuste,
                on_stock_busqueda=self._on_stock_busqueda,
                on_stock_filtro_ubicacion=self._on_stock_filtro,
                on_traslado_producto=self._on_tr_producto,
                on_traslado_lote=self._on_tr_lote,
                on_traslado_origen=self._on_tr_origen,
                on_traslado_destino=self._on_tr_destino,
                on_traslado_cantidad=self._on_tr_cantidad,
                on_preview_traslado=self._on_tr_preview,
                on_confirmar_traslado=self._on_tr_confirm,
                on_cancelar_traslado=self._on_tr_cancel,
                on_recuento_ubicacion=self._on_rc_ubicacion,
                on_recuento_producto=self._on_rc_producto,
                on_recuento_lote=self._on_rc_lote,
                on_recuento_cantidad=self._on_rc_cantidad,
                on_anadir_linea_recuento=self._on_rc_anadir,
                on_quitar_linea_recuento=self._on_rc_quitar,
                on_preview_recuento=self._on_rc_preview,
                on_confirmar_recuento=self._on_rc_confirm,
                on_cancelar_recuento=self._on_rc_cancel,
                on_seleccionar_borrador=self._on_rc_sel_borrador,
                on_descartar_borrador=self._on_rc_descartar,
                on_abandonar_borrador=self._on_rc_abandonar,
                economato_callbacks=self._economato_callbacks(),
                narrow=narrow,
            )
        self._root.content = content
        self.page.update()

    def _on_enter(self) -> None:
        self.presenter.entrar()
        self.refresh()

    def _on_logout(self) -> None:
        self.presenter.logout()
        self.refresh()

    def _on_volver_wrapped(self) -> None:
        self.presenter.preparar_salida()
        if self._on_volver_al_menu is not None:
            self._on_volver_al_menu()

    def _on_espacio(self, eid: str) -> None:
        self.presenter.seleccionar_espacio(eid)
        self.refresh()

    def _on_alerta(self, aid: str, estado: str) -> None:
        self.presenter.marcar_alerta(aid, estado)
        self.refresh()

    def _on_caducidad(self, lid: str, cant: float) -> None:
        self.presenter.enviar_caducidad_a_merma(lid, cant)
        self.refresh()

    def _on_anadir_merma(self, lid: str, cant: float, motivo: str) -> None:
        self.presenter.anadir_merma(lid, cant, motivo)
        self.refresh()

    def _on_responsable(self, rid: str | None) -> None:
        self.presenter.seleccionar_responsable(rid)
        self.refresh()

    def _on_vaciar_merma(self) -> None:
        self.presenter.vaciar_cesta_merma()
        self.refresh()

    def _on_confirmar_merma(self) -> None:
        self.presenter.confirmar_merma()
        self.refresh()

    def _on_preview_ajuste(self, lid: str, cant: float, motivo: str) -> None:
        self.presenter.previsualizar_ajuste(lid, cant, motivo)
        self.refresh()

    def _on_confirmar_ajuste(self) -> None:
        self.presenter.confirmar_ajuste()
        self.refresh()

    def _on_stock_busqueda(self, texto: str) -> None:
        self.presenter.set_stock_busqueda(texto)
        self.refresh()

    def _on_stock_filtro(self, uid: str | None) -> None:
        self.presenter.set_stock_filtro_ubicacion(uid)
        self.refresh()

    def _on_tr_producto(self, pid: str | None) -> None:
        self.presenter.set_traslado_producto(pid)
        self.refresh()

    def _on_tr_lote(self, lid: str | None) -> None:
        self.presenter.set_traslado_lote(lid)
        self.refresh()

    def _on_tr_origen(self, uid: str | None) -> None:
        self.presenter.set_traslado_origen(uid)
        self.refresh()

    def _on_tr_destino(self, uid: str | None) -> None:
        self.presenter.set_traslado_destino(uid)
        self.refresh()

    def _on_tr_cantidad(self, cant: str) -> None:
        self.presenter.set_traslado_cantidad(cant)
        self.refresh()

    def _on_tr_preview(self) -> None:
        self.presenter.previsualizar_traslado()
        self.refresh()

    def _on_tr_confirm(self) -> None:
        self.presenter.confirmar_traslado()
        self.refresh()

    def _on_tr_cancel(self) -> None:
        self.presenter.cancelar_traslado_preview()
        self.refresh()

    def _on_rc_ubicacion(self, uid: str | None) -> None:
        self.presenter.set_recuento_ubicacion(uid)
        self.refresh()

    def _on_rc_producto(self, pid: str | None) -> None:
        self.presenter.set_recuento_producto(pid)
        self.refresh()

    def _on_rc_lote(self, lid: str | None) -> None:
        self.presenter.set_recuento_lote(lid)
        self.refresh()

    def _on_rc_cantidad(self, cant: str) -> None:
        self.presenter.set_recuento_cantidad(cant)
        self.refresh()

    def _on_rc_anadir(self) -> None:
        self.presenter.anadir_linea_recuento()
        self.refresh()

    def _on_rc_quitar(self, lid: str) -> None:
        self.presenter.quitar_linea_recuento(lid)
        self.refresh()

    def _on_rc_preview(self) -> None:
        self.presenter.previsualizar_recuento()
        self.refresh()

    def _on_rc_confirm(self) -> None:
        self.presenter.confirmar_recuento()
        self.refresh()

    def _on_rc_cancel(self) -> None:
        self.presenter.cancelar_recuento_memoria()
        self.refresh()

    def _on_rc_sel_borrador(self, rid: str) -> None:
        self.presenter.seleccionar_borrador_pendiente(rid)
        self.refresh()

    def _on_rc_descartar(self) -> None:
        self.presenter.descartar_borrador_pendiente()
        self.refresh()

    def _on_rc_abandonar(self) -> None:
        self.presenter.abandonar_recuento_dejando_pendiente()
        self.refresh()

    def _economato_callbacks(self) -> dict:
        p = self.presenter

        def _go(fn, *a, **kw):
            fn(*a, **kw)
            self.refresh()

        return {
            "on_maestro_tab": lambda t: _go(p.set_maestro_tab, t),
            "on_compra_tipo": lambda t: _go(p.set_compra_tipo, t),
            "on_compra_cabecera": lambda **kw: _go(p.set_compra_cabecera, **kw),
            # Sin refresh: la vista filtra chips en local (evita salto de scroll).
            "on_compra_busqueda": lambda t: p.set_compra_prod_busqueda(t),
            "on_add_linea": lambda pid, **kw: _go(p.añadir_linea_compra, pid, **kw),
            "on_add_linea_busqueda": lambda t, **kw: _go(
                p.añadir_linea_compra_por_busqueda, t, **kw
            ),
            "on_update_linea": lambda i, **kw: _go(p.update_linea_compra, i, **kw),
            "on_quitar_linea": lambda i: _go(p.quitar_linea_compra, i),
            "on_guardar_borrador": lambda: _go(p.guardar_borrador_compra),
            "on_confirmar_compra": lambda: _go(p.confirmar_compra_borrador),
            "on_limpiar_compra": lambda: _go(p.limpiar_borrador_compra),
            "on_toggle_albaran": lambda aid: _go(p.toggle_albaran_conciliacion, aid),
            "on_incorporar_albaranes": lambda: _go(
                p.incorporar_albaranes_seleccionados
            ),
            "on_cargar_borrador": lambda did: _go(p.cargar_borrador_compra, did),
            "on_anular_borrador": lambda did: _go(p.anular_borrador_compra, did),
            "on_goto_espacio": lambda eid: _go(p.seleccionar_espacio, eid),
            "on_doc_filtros": lambda **kw: _go(p.set_doc_filtros, **kw),
            "on_sel_documento": lambda did: _go(p.seleccionar_documento, did),
            "on_anular_doc": lambda did, m: _go(p.anular_documento_confirmado, did, m),
            "on_rectificativa": lambda did, m: _go(p.crear_rectificativa, did, m),
            "on_crear_depto": lambda n: _go(p.crear_departamento_maestro, n),
            "on_crear_ubicacion": lambda n, c, t: _go(
                p.crear_ubicacion_maestro, n, c, t
            ),
            "on_tipo_ubicacion": lambda uid, t: _go(
                p.set_tipo_ubicacion_maestro, uid, t
            ),
            "on_crear_proveedor": lambda nf, c, nif: _go(
                p.crear_proveedor_maestro, nf, c, nif_cif=nif
            ),
            "on_crear_impuesto": lambda n, pct: _go(p.crear_impuesto_maestro, n, pct),
            "on_desactivar_impuesto": lambda iid: _go(
                p.desactivar_impuesto_maestro, iid
            ),
            "on_vincular": lambda pid, prid, uc, fac, prec: _go(
                p.vincular_producto_proveedor_maestro,
                pid,
                prid,
                unidad_compra=uc,
                factor_compra=fac,
                ultimo_precio=prec,
            ),
            "on_hist_filtros": lambda **kw: _go(p.set_historial_filtros, **kw),
            "on_export_hist": self._on_export_hist,
        }

    def _on_export_hist(self) -> None:
        from app.presentation.flet.viewmodels import FeedbackVM

        nombre, contenido = self.presenter.exportar_historial_csv()
        from pathlib import Path
        import tempfile

        dest = Path(tempfile.gettempdir()) / nombre
        dest.write_text(contenido, encoding="utf-8")
        self.presenter._feedback = FeedbackVM(
            ok=True, mensaje=f"CSV exportado: {dest}"
        )
        self.refresh()


def attach_terminal_inventario(page: ft.Page) -> TerminalInventarioShell:
    shell = TerminalInventarioShell(page)
    shell.mount()
    return shell
