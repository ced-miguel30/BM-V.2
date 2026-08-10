"""Entrada Flet — Terminal Restaurante (primera vertical).

Uso:
  python -m app.presentation.flet.main

Variables:
  BM_DEMO_FILE — JSON de datos (opcional; por defecto el demo canónico)
  BM_FLET_VIEW — web | desktop (default desktop)
"""

from __future__ import annotations

import os
import sys


def build_app_handler():
    """Construye el handler ``main(page)`` (útil en tests/smoke)."""
    from app.bootstrap import configure_for_flet

    terminal = (os.environ.get("BM_FLET_TERMINAL") or "restaurante").strip().lower()
    configure_for_flet()

    if terminal in ("inventario", "inventory"):
        from app.presentation.flet.app_shell_inventario import attach_terminal_inventario

        def main(page) -> None:
            attach_terminal_inventario(page)

        return main

    if terminal in ("administracion", "admin", "administración"):
        from app.presentation.flet.app_shell_administracion import (
            attach_terminal_administracion,
        )

        def main(page) -> None:
            attach_terminal_administracion(page)

        return main

    from app.presentation.flet.app_shell import attach_terminal

    def main(page) -> None:
        attach_terminal(page)

    return main


def main() -> None:
    import flet as ft

    handler = build_app_handler()
    view_mode = (os.environ.get("BM_FLET_VIEW") or "desktop").strip().lower()
    if view_mode == "web":
        ft.run(handler, view=ft.AppView.WEB_BROWSER)
    elif view_mode in ("none", "headless", "asgi"):
        # Construcción controlada sin abrir ventana (smoke / CI).
        app = ft.run(handler, export_asgi_app=True)
        assert app is not None
    else:
        ft.run(handler, view=ft.AppView.FLET_APP)


if __name__ == "__main__":
    # Permite ``python -m app.presentation.flet.main``
    if __package__ is None:
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
    main()
