"""Shell Flet de Terminal Restaurante."""

from __future__ import annotations

import flet as ft

from app.presentation.flet.presenters.terminal_restaurante_presenter import (
    TerminalRestaurantePresenter,
)
from app.presentation.flet.views.login_terminal_view import build_login_view
from app.presentation.flet.views.registro_servicio_view import (
    build_catalog_result_controls,
    build_registro_view,
)


class TerminalRestauranteShell:
    def __init__(self, page: ft.Page, presenter: TerminalRestaurantePresenter | None = None):
        self.page = page
        self.presenter = presenter or TerminalRestaurantePresenter()
        self._root = ft.Container(expand=True)
        self._search_field: ft.TextField | None = None
        self._catalog_results: ft.Column | None = None
        self._last_refresh_kind: str | None = None

    def mount(self) -> None:
        page = self.page
        page.title = "BM — Terminal Restaurante"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.padding = 0
        page.bgcolor = ft.Colors.GREY_100
        page.on_resize = lambda _e: self.refresh()
        page.add(self._root)
        self.refresh()

    def refresh(self) -> None:
        """Reconstrucción completa (servicio, cesta, login, confirmación…)."""
        screen = self.presenter.screen()
        narrow = (self.page.width or 900) < 720
        if not screen.session.authenticated:
            self._search_field = None
            self._catalog_results = None
            self._last_refresh_kind = "login"
            self._root.content = build_login_view(on_enter=self._on_enter)
        else:
            # Nuevo TextField solo en rebuilds mayores (no en búsqueda tipada).
            content, search, catalog = build_registro_view(
                screen,
                on_select_servicio=self._on_servicio,
                on_search=self._on_search,
                on_add_receta=self._on_add_receta,
                on_add_producto=self._on_add_producto,
                on_qty_receta=self._on_qty_receta,
                on_qty_producto=self._on_qty_producto,
                on_remove_receta=self._on_remove_receta,
                on_remove_producto=self._on_remove_producto,
                on_clear=self._on_clear,
                on_confirm=self._on_confirm,
                on_huespedes=self._on_huespedes,
                on_logout=self._on_logout,
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
        )
        self._last_refresh_kind = "catalog"
        # Actualiza el árbol existente (no reconstruye el TextField).
        self.page.update()

    def _on_enter(self) -> None:
        self.presenter.entrar()
        self.refresh()

    def _on_logout(self) -> None:
        self.presenter.logout()
        self.refresh()

    def _on_servicio(self, sid: str) -> None:
        self.presenter.seleccionar_servicio(sid)
        self.refresh()

    def _on_search(self, texto: str) -> None:
        self.presenter.set_busqueda(texto)
        self.update_catalog_only()

    def _on_add_receta(self, rid: str) -> None:
        self.presenter.anadir_receta(
            rid, 4.0 if self.presenter.screen().servicio_activo == "desayuno" else 1.0
        )
        self.refresh()

    def _on_add_producto(self, pid: str) -> None:
        self.presenter.anadir_producto_directo(pid, 1.0)
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


def attach_terminal(page: ft.Page) -> TerminalRestauranteShell:
    shell = TerminalRestauranteShell(page)
    shell.mount()
    return shell
