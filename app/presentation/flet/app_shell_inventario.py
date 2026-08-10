"""Shell Flet de Terminal Inventario."""

from __future__ import annotations

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
        self, page: ft.Page, presenter: TerminalInventarioPresenter | None = None
    ):
        self.page = page
        self.presenter = presenter or TerminalInventarioPresenter()
        self._root = ft.Container(expand=True)

    def mount(self) -> None:
        page = self.page
        page.title = "BM — Terminal Inventario"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.padding = 0
        page.bgcolor = ft.Colors.GREY_100
        page.on_resize = lambda _e: self.refresh()
        page.add(self._root)
        self.refresh()

    def refresh(self) -> None:
        screen = self.presenter.screen()
        narrow = (self.page.width or 900) < 720
        if not screen.session.authenticated:
            content = build_login_inventario(on_enter=self._on_enter)
        else:
            content = build_inventario_shell(
                screen,
                on_espacio=self._on_espacio,
                on_logout=self._on_logout,
                on_alerta_estado=self._on_alerta,
                on_caducidad_a_merma=self._on_caducidad,
                on_anadir_merma=self._on_anadir_merma,
                on_vaciar_merma=self._on_vaciar_merma,
                on_confirmar_merma=self._on_confirmar_merma,
                on_preview_ajuste=self._on_preview_ajuste,
                on_confirmar_ajuste=self._on_confirmar_ajuste,
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


def attach_terminal_inventario(page: ft.Page) -> TerminalInventarioShell:
    shell = TerminalInventarioShell(page)
    shell.mount()
    return shell
