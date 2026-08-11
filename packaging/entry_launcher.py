"""Entrypoint empaquetable del launcher Flet BM‑V.2."""

from __future__ import annotations

import os
import sys


def main() -> None:
    # Asegura imports del paquete app cuando se ejecuta congelado o como script.
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ.setdefault("BM_FLET_TERMINAL", "launcher")
    from app.presentation.flet.main_launcher import main as flet_main

    flet_main()


if __name__ == "__main__":
    main()
