"""Shell Flet de Terminal Restaurante."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path

import flet as ft

from app.presentation.flet.presenters.terminal_restaurante_presenter import (
    TerminalRestaurantePresenter,
)
from app.presentation.flet.viewmodels import FeedbackVM
from app.presentation.flet.views.login_terminal_view import build_login_view
from app.presentation.flet.views.registro_servicio_view import (
    build_catalog_result_controls,
    build_registro_view,
)


class TerminalRestauranteShell:
    def __init__(
        self,
        page: ft.Page,
        presenter: TerminalRestaurantePresenter | None = None,
        *,
        on_volver_al_menu: Callable[[], None] | None = None,
    ):
        self.page = page
        self.presenter = presenter or TerminalRestaurantePresenter()
        self._on_volver_al_menu = on_volver_al_menu
        self._root = ft.Container(expand=True)
        self._search_field: ft.TextField | None = None
        self._catalog_results: ft.Column | None = None
        self._last_refresh_kind: str | None = None
        self._file_picker: ft.FilePicker | None = None
        self._import_bloqueado: bool = False
        self._resize_handler = None

    def refresh(self) -> None:
        """Reconstrucción completa (servicio, cesta, login, confirmación…)."""
        if self._import_bloqueado:
            return
        self._refresh_full()

    def mount(self) -> None:
        page = self.page
        from app.presentation.flet.theme import apply_page_theme, APP_NAME

        apply_page_theme(page, title=f"{APP_NAME} — Terminal Restaurante")
        self._resize_handler = lambda _e: self.refresh()
        page.on_resize = self._resize_handler
        self._file_picker = ft.FilePicker()
        page.add(self._root)
        self.refresh()

    def _refresh_full(self) -> None:
        """Reconstrucción completa (servicio, cesta, login, confirmación…)."""
        screen = self.presenter.screen()
        narrow = (self.page.width or 900) < 720
        on_volver = (
            self._on_volver_wrapped if self._on_volver_al_menu is not None else None
        )
        if not screen.session.authenticated:
            self._search_field = None
            self._catalog_results = None
            self._last_refresh_kind = "login"
            self._root.content = build_login_view(
                on_enter=self._on_enter,
                on_volver_menu=on_volver,
            )
        else:
            content, search, catalog = build_registro_view(
                screen,
                on_select_servicio=self._on_servicio,
                on_search=self._on_search,
                on_add_receta=self._on_add_receta,
                on_add_producto=self._on_add_producto,
                on_add_extra=self._on_add_extra,
                on_qty_receta=self._on_qty_receta,
                on_qty_producto=self._on_qty_producto,
                on_remove_receta=self._on_remove_receta,
                on_remove_producto=self._on_remove_producto,
                on_clear=self._on_clear,
                on_confirm=self._on_confirm,
                on_huespedes=self._on_huespedes,
                on_logout=self._on_logout,
                on_volver_menu=on_volver,
                on_iniciar_anulacion=self._on_iniciar_anulacion,
                on_set_motivo_anulacion=self._on_set_motivo,
                on_cancelar_anulacion=self._on_cancelar_anulacion,
                on_confirmar_anulacion=self._on_confirmar_anulacion,
                on_confirmar_revision_historial=self._on_confirmar_revision_historial,
                on_catalogo_tipo=self._on_catalogo_tipo,
                on_upload_documento=self._on_upload_documento,
                on_cerrar_importacion_tpv=self._on_cerrar_importacion_tpv,
                on_iniciar_edicion=self._on_iniciar_edicion,
                on_cancelar_edicion=self._on_cancelar_edicion,
                on_guardar_edicion=self._on_guardar_edicion,
                on_ajustar_edicion=self._on_ajustar_edicion,
                on_quitar_edicion=self._on_quitar_edicion,
                narrow=narrow,
                search_field=None,
                catalog_results=None,
            )
            self._search_field = search
            self._catalog_results = catalog
            self._last_refresh_kind = "full"
            self._root.content = content
        self.page.update()

    def update_catalog_only(self) -> None:
        """Actualiza solo el listado filtrado; conserva TextField, servicio y cesta UI."""
        if self._catalog_results is None or self._search_field is None:
            self.refresh()
            return
        screen = self.presenter.screen()
        self._catalog_results.controls = build_catalog_result_controls(
            screen,
            on_add_receta=self._on_add_receta,
            on_add_producto=self._on_add_producto,
            on_add_extra=self._on_add_extra,
        )
        self._last_refresh_kind = "catalog"
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

    def _on_servicio(self, sid: str) -> None:
        self.presenter.seleccionar_servicio(sid)
        self.refresh()

    def _on_search(self, texto: str) -> None:
        self.presenter.set_busqueda(texto)
        self.update_catalog_only()

    def _on_catalogo_tipo(self, tipo: str) -> None:
        self.presenter.set_catalogo_tipo(tipo)
        self.refresh()

    def _on_add_receta(self, rid: str) -> None:
        # Siempre 1 ración al añadir; el usuario ajusta en cesta si hace falta.
        self.presenter.anadir_receta(rid, 1.0)
        self.refresh()

    def _on_add_producto(self, pid: str, cantidad: float = 1.0) -> None:
        self.presenter.anadir_producto_directo(pid, float(cantidad))
        self.refresh()

    def _on_add_extra(self, pid: str, cantidad: float = 1.0) -> None:
        self.presenter.anadir_extra_o_omision(pid, float(cantidad))
        self.refresh()

    def _on_qty_receta(self, gid: str, delta: float) -> None:
        self.presenter.ajustar_porciones_receta(gid, delta)
        self.refresh()

    def _on_qty_producto(self, lid: str, delta: float) -> None:
        self.presenter.ajustar_linea_producto(lid, delta)
        self.refresh()

    def _on_remove_receta(self, gid: str) -> None:
        self.presenter.quitar_grupo_receta(gid)
        self.refresh()

    def _on_remove_producto(self, lid: str) -> None:
        self.presenter.quitar_linea_producto(lid)
        self.refresh()

    def _on_clear(self) -> None:
        self.presenter.vaciar_cesta()
        self.refresh()

    def _on_confirm(self) -> None:
        self.presenter.confirmar()
        self.refresh()

    def _on_huespedes(self, n: int) -> None:
        self.presenter.set_num_huespedes(n)
        self.refresh()

    def _on_iniciar_anulacion(self, rid: str) -> None:
        self.presenter.iniciar_anulacion(rid)
        self.refresh()

    def _on_set_motivo(self, motivo: str) -> None:
        self.presenter.set_motivo_anulacion(motivo)
        self.refresh()

    def _on_cancelar_anulacion(self) -> None:
        self.presenter.cancelar_anulacion()
        self.refresh()

    def _on_confirmar_anulacion(self) -> None:
        self.presenter.confirmar_anulacion()
        self.refresh()

    def _on_confirmar_revision_historial(self, registro_id: str) -> None:
        self.presenter.confirmar_revision_historial(registro_id)
        self.refresh()

    def _on_cerrar_importacion_tpv(self) -> None:
        self.presenter.cerrar_panel_importacion_tpv()
        self.refresh()

    def _on_iniciar_edicion(self, rid: str) -> None:
        self.presenter.iniciar_edicion(rid)
        self.refresh()

    def _on_cancelar_edicion(self) -> None:
        self.presenter.cancelar_edicion()
        self.refresh()

    def _on_guardar_edicion(self) -> None:
        self.presenter.guardar_edicion()
        self.refresh()

    def _on_ajustar_edicion(self, pid: str, delta: float) -> None:
        self.presenter.ajustar_linea_edicion(pid, delta)
        self.refresh()

    def _on_quitar_edicion(self, pid: str) -> None:
        self.presenter.quitar_linea_edicion(pid)
        self.refresh()

    def _on_upload_documento(self) -> None:
        async def _pick_and_import() -> None:
            picker = self._file_picker
            if picker is None:
                picker = ft.FilePicker()
                self._file_picker = picker
                self.page.update()
            try:
                files = await picker.pick_files(
                    dialog_title="Importar documento TPV (comida / bebidas)",
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["pdf", "png", "jpg", "jpeg", "webp"],
                    allow_multiple=False,
                )
            except Exception as exc:  # noqa: BLE001
                self.presenter._feedback = FeedbackVM(
                    ok=False, mensaje=f"No se pudo abrir el selector: {exc}"
                )
                self.refresh()
                return
            if not files:
                return
            path = getattr(files[0], "path", None) or ""
            if not path:
                self.presenter._feedback = FeedbackVM(
                    ok=False,
                    mensaje=(
                        "No se obtuvo la ruta del archivo "
                        "(solo disponible en escritorio)."
                    ),
                )
                self.refresh()
                return

            self.presenter.set_importacion_tpv_activa(True)
            self.presenter.marcar_importando_tpv(True)
            self._import_bloqueado = True
            self.page.on_resize = None
            self._refresh_full()
            from app.core.storage.demo_files import get_demo_file

            # Misma instancia que el resto de la app (shared root / BM_DEMO_FILE),
            # nunca hardcodear BM-V2-local (rompe la carpeta 2-BM-DATOS del servidor).
            hotel_path = get_demo_file()
            try:
                from app.core.services.tpv_documento_service import (
                    importar_documento_tpv_aislado,
                )

                resultado = await asyncio.to_thread(
                    importar_documento_tpv_aislado,
                    path,
                    hotel_path=hotel_path,
                )
                self.presenter.aplicar_resultado_importacion_tpv(resultado)
                # El worker escribe en otro proceso: recargar JSON en el store del UI.
                try:
                    from app.bootstrap import get_container

                    get_container().app_data_store.reload_from_disk()
                except Exception:  # noqa: BLE001
                    pass
            except Exception as exc:  # noqa: BLE001
                self.presenter._confirmando = False
                self.presenter._feedback = FeedbackVM(
                    ok=False,
                    mensaje=f"Error al importar documento: {exc}",
                )
            finally:
                self.presenter.set_importacion_tpv_activa(False)
                self._import_bloqueado = False
                self.page.on_resize = self._resize_handler
            self.refresh()

        if hasattr(self.page, "run_task"):
            self.page.run_task(_pick_and_import)
        else:
            self.presenter._feedback = FeedbackVM(
                ok=False,
                mensaje="Selector de archivos no disponible en este entorno.",
            )
            self.refresh()


def attach_terminal(page: ft.Page) -> TerminalRestauranteShell:
    shell = TerminalRestauranteShell(page)
    shell.mount()
    return shell
