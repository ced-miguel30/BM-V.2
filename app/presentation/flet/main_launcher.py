"""Entrada Flet — launcher mínimo entre verticales existentes.

Uso:
  python -m app.presentation.flet.main_launcher

Variables:
  BM_DEMO_FILE — JSON de datos (opcional)
  BM_FLET_VIEW — web | desktop | asgi

Los entrypoints específicos (main / main_inventario / main_administracion)
siguen operativos. Este launcher no autentica ni concede permisos.
"""

from __future__ import annotations

import os
import sys


def build_app_handler():
    import flet as ft

    from app.bootstrap import configure_for_flet
    from app.core.deploy.runtime import prepare_runtime
    from app.core.deploy.writer_lock import WriterLockError
    from app.presentation.flet.app_shell_launcher import attach_launcher

    try:
        prepare_runtime(role="flet_launcher")
    except WriterLockError as exc:
        def _lock_error(page: ft.Page) -> None:
            page.title = "BM — No disponible"
            page.add(
                ft.Container(
                    expand=True,
                    padding=24,
                    content=ft.Column(
                        spacing=12,
                        controls=[
                            ft.Text(
                                "Otra ventana de BM ya está abierta",
                                size=22,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(str(exc), size=14),
                            ft.Text(
                                "Cierre la otra ventana o espere a que termine de cargar.",
                                size=13,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                    ),
                )
            )

        return _lock_error

    configure_for_flet()

    def main(page: ft.Page) -> None:
        if hasattr(page, "wait_until_visible"):
            page.wait_until_visible()
        attach_launcher(page)

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
