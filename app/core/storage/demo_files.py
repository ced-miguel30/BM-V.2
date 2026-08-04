"""Lectura y escritura de datos en data/demo/."""

from __future__ import annotations

from pathlib import Path

from app.core.models import AppData
from app.data.mock_data import crear_datos_mock
from app.data.serializers import appdata_to_dict, dict_to_appdata, load_json, save_json

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEMO_DIR = PROJECT_ROOT / "data" / "demo"
# Ruta canónica de producción/demo. No reasignar en tests; usar set_demo_file_override.
DEMO_FILE = DEMO_DIR / "datos_hotel.json"

_demo_file_override: Path | None = None


def set_demo_file_override(path: Path | str | None) -> None:
    """Inyecta una ruta alternativa (p. ej. TemporaryDirectory) para tests.

    Pasar ``None`` restaura la ruta canónica ``DEMO_FILE``.
    """
    global _demo_file_override
    if path is None:
        _demo_file_override = None
    else:
        _demo_file_override = Path(path).resolve()


def get_demo_file() -> Path:
    """Ruta efectiva del JSON de datos (override de test o DEMO_FILE)."""
    if _demo_file_override is not None:
        return _demo_file_override
    return DEMO_FILE


def demo_exists() -> bool:
    return get_demo_file().exists()


def save_demo_files(data: AppData | None = None) -> Path:
    target = get_demo_file()
    payload = appdata_to_dict(data or crear_datos_mock())
    save_json(target, payload)
    return target


def load_demo_files() -> AppData:
    if not demo_exists():
        save_demo_files()
    return dict_to_appdata(load_json(get_demo_file()))


def delete_demo_files() -> bool:
    target = get_demo_file()
    import os

    flag = os.environ.get("BM_TEST_ISOLATION", "").strip().lower()
    if flag in ("1", "true", "yes") and target.resolve() == DEMO_FILE.resolve():
        raise RuntimeError(
            f"BM_TEST_ISOLATION: forbidden delete of {DEMO_FILE.resolve()}"
        )
    if target.exists():
        target.unlink()
        return True
    return False
