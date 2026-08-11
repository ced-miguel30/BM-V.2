"""Entrada Flet — Terminal Inventario.

Uso:
  python -m app.presentation.flet.main_inventario

Variables:
  BM_DEMO_FILE — JSON de datos (opcional)
  BM_FLET_VIEW — web | desktop | asgi
"""

from __future__ import annotations

import os
import sys


def build_app_handler():
    from app.bootstrap import configure_for_flet
    from app.core.deploy.runtime import prepare_runtime
    from app.presentation.flet.app_shell_inventario import attach_terminal_inventario

    prepare_runtime(role="flet_inventario")
    configure_for_flet()

    def main(page) -> None:
        attach_terminal_inventario(page)

    return main


def main() -> None:
    import flet as ft

    handler = build_app_handler()
    view_mode = (os.environ.get("BM_FLET_VIEW") or "desktop").strip().lower()
    if view_mode == "web":
        ft.run(handler, view=ft.AppView.WEB_BROWSER)
    elif view_mode in ("none", "headless", "asgi"):
        app = ft.run(handler, export_asgi_app=True)
        assert app is not None
    else:
        ft.run(handler, view=ft.AppView.FLET_APP)


if __name__ == "__main__":
    if __package__ is None:
        sys.path.insert(
            0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
        )
    main()
