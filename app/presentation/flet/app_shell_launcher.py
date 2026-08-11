"""Shell del launcher Flet — monta destinos existentes tras limpiar sesión."""

from __future__ import annotations

import flet as ft

from app.presentation.flet import session_bridge
from app.presentation.flet.launcher_routing import (
    DESTINO_ADMINISTRACION,
    DESTINO_INVENTARIO,
    DESTINO_RESTAURANTE,
    DestinoDesconocidoError,
    resolver_destino,
)
from app.presentation.flet.views.launcher_view import build_launcher_view


class LauncherShell:
    """Pantalla de selección. No autentica ni concede permisos."""

    def __init__(self, page: ft.Page):
        self.page = page
        self._root = ft.Container(expand=True)
        self._cargando = False
        self._error = ""
        self._mounted_destino: str | None = None

    def mount(self) -> None:
        page = self.page
        page.title = "BM — Launcher Flet"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.padding = 0
        page.bgcolor = ft.Colors.GREY_100
        page.on_resize = lambda _e: self._safe_refresh()
        page.add(self._root)
        self.show_launcher()

    def show_launcher(self) -> None:
        # Evita reutilizar sesión entre verticales.
        session_bridge.logout_terminal()
        self._mounted_destino = None
        self._cargando = False
        self._root.content = build_launcher_view(
            on_select=self._on_select,
            cargando=False,
            error=self._error,
        )
        self.page.update()

    def _safe_refresh(self) -> None:
        if self._mounted_destino is None and not self._cargando:
            self._root.content = build_launcher_view(
                on_select=self._on_select,
                cargando=False,
                error=self._error,
            )
            self.page.update()

    def _on_select(self, destino_raw: str) -> None:
        self._error = ""
        self._cargando = True
        self._root.content = build_launcher_view(
            on_select=self._on_select,
            cargando=True,
            error="",
        )
        self.page.update()
        try:
            destino = resolver_destino(destino_raw)
            if destino not in (
                DESTINO_RESTAURANTE,
                DESTINO_INVENTARIO,
                DESTINO_ADMINISTRACION,
            ):
                raise DestinoDesconocidoError(destino_raw)
            session_bridge.logout_terminal()
            self._mount_destino(destino)
            self._mounted_destino = destino
            self._cargando = False
        except DestinoDesconocidoError:
            self._cargando = False
            self._error = "Destino no reconocido."
            self.show_launcher()
        except Exception:  # noqa: BLE001 — error recuperable de UI
            self._cargando = False
            self._error = "No se pudo abrir el destino. Inténtelo de nuevo."
            self.show_launcher()

    def _mount_destino(self, destino: str) -> None:
        """Sustituye el contenido del launcher por el shell del destino.

        Lazy-import de shells para evitar acoplar verticales entre sí.
        """
        if destino == DESTINO_RESTAURANTE:
            from app.presentation.flet.app_shell import TerminalRestauranteShell

            self.page.title = "BM — Terminal Restaurante"
            shell = TerminalRestauranteShell(self.page)
            shell._root = self._root
            shell.refresh()
            return
        if destino == DESTINO_INVENTARIO:
            from app.presentation.flet.app_shell_inventario import TerminalInventarioShell

            self.page.title = "BM — Terminal Inventario"
            shell = TerminalInventarioShell(self.page)
            shell._root = self._root
            shell.refresh()
            return
        if destino == DESTINO_ADMINISTRACION:
            from app.presentation.flet.app_shell_administracion import (
                TerminalAdministracionShell,
            )

            self.page.title = "BM — Administración operativa"
            shell = TerminalAdministracionShell(self.page)
            shell._root = self._root
            shell.refresh()
            return
        raise DestinoDesconocidoError(destino)


def attach_launcher(page: ft.Page) -> LauncherShell:
    shell = LauncherShell(page)
    shell.mount()
    return shell
