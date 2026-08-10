"""Shell Flet de Administración operativa."""

from __future__ import annotations

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
    ):
        self.page = page
        self.presenter = presenter or TerminalAdministracionPresenter()
        self._root = ft.Container(expand=True)

    def mount(self) -> None:
        page = self.page
        page.title = "BM — Administración operativa"
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
            content = build_login_admin(on_login=self._on_login, feedback_mensaje=msg)
        else:
            content = build_admin_shell(
                screen,
                on_logout=self._on_logout,
                on_filtro=self._on_filtro,
                on_proponer_crear=self._on_crear,
                on_proponer_renombrar=self._on_renombrar,
                on_proponer_desactivar=self._on_desactivar,
                on_proponer_reactivar=self._on_reactivar,
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

    def _on_filtro(self, texto: str) -> None:
        self.presenter.set_filtro(texto)
        self.refresh()

    def _on_crear(self, nombre: str) -> None:
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
