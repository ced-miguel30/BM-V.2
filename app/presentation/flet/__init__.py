"""Presentación Flet — Terminal Restaurante (primera vertical).

No importa Streamlit ni ``app.pages``. Consume el núcleo vía bootstrap.
"""

__all__ = ["run_terminal_restaurante"]


def run_terminal_restaurante() -> None:
    from app.presentation.flet.main import main

    main()
