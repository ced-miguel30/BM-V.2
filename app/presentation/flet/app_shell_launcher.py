"""Shell del launcher Flet — monta destinos existentes tras limpiar sesión."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import flet as ft

_log = logging.getLogger("bm.flet.launcher")

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
        self._active_shell: object | None = None

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
        self._active_shell = None
        self._cargando = False
        self.page.title = "BM — Launcher Flet"
        self.page.on_resize = lambda _e: self._safe_refresh()
        self._root.content = build_launcher_view(
            on_select=self._on_select,
            cargando=False,
            error=self._error,
        )
        self.page.update()

    def volver_al_menu(self) -> None:
        """Transición interna: logout + remonte del launcher (misma Page)."""
        self._error = ""
        self.show_launcher()

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
        except DestinoDesconocidoError:
            self._cargando = False
            self._error = "Destino no reconocido."
            self.show_launcher()
            return
        if destino not in (
            DESTINO_RESTAURANTE,
            DESTINO_INVENTARIO,
            DESTINO_ADMINISTRACION,
        ):
            self._cargando = False
            self._error = "Destino no reconocido."
            self.show_launcher()
            return

        if hasattr(self.page, "run_task"):
            self.page.run_task(self._open_destino_task, destino)
        else:
            self._open_destino_sync(destino)

    async def _open_destino_task(self, destino: str) -> None:
        """Cede un tick al cliente Flet para pintar el indicador de carga."""
        await asyncio.sleep(0)
        self._open_destino_sync(destino)

    def _open_destino_sync(self, destino: str) -> None:
        try:
            session_bridge.logout_terminal()
            self._mount_destino(destino)
            self._cargando = False
        except Exception as exc:  # noqa: BLE001 — error recuperable de UI
            _log.exception("No se pudo montar destino %s", destino)
            self._cargando = False
            self._mounted_destino = None
            self._active_shell = None
            detail = str(exc).strip()
            if detail:
                self._error = (
                    "No se pudo abrir el destino. "
                    f"{detail[:180]}{'…' if len(detail) > 180 else ''}"
                )
            else:
                self._error = "No se pudo abrir el destino. Inténtelo de nuevo."
            self.show_launcher()

    def _mount_destino(self, destino: str) -> None:
        """Sustituye el contenido del launcher por el shell del destino.

        Lazy-import de shells para evitar acoplar verticales entre sí.
        Pasa callback de retorno sin que las verticales importen este módulo.
        """
        on_volver: Callable[[], None] = self.volver_al_menu
        self._mounted_destino = destino
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.padding = 0
        self.page.bgcolor = ft.Colors.GREY_100
        if destino == DESTINO_RESTAURANTE:
            from app.presentation.flet.app_shell import TerminalRestauranteShell

            self.page.title = "BM — Terminal Restaurante"
            shell = TerminalRestauranteShell(
                self.page, on_volver_al_menu=on_volver
            )
        elif destino == DESTINO_INVENTARIO:
            from app.presentation.flet.app_shell_inventario import TerminalInventarioShell

            self.page.title = "BM — Terminal Inventario"
            shell = TerminalInventarioShell(
                self.page, on_volver_al_menu=on_volver
            )
        elif destino == DESTINO_ADMINISTRACION:
            from app.presentation.flet.app_shell_administracion import (
                TerminalAdministracionShell,
            )

            self.page.title = "BM — Administración operativa"
            shell = TerminalAdministracionShell(
                self.page, on_volver_al_menu=on_volver
            )
        else:
            raise DestinoDesconocidoError(destino)
        shell._root = self._root
        self._active_shell = shell
        self.page.on_resize = lambda _e: shell.refresh()
        shell.refresh()


def attach_launcher(page: ft.Page) -> LauncherShell:
    shell = LauncherShell(page)
    shell.mount()
    return shell
