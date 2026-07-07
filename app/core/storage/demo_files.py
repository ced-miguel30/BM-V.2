"""Lectura y escritura de datos en data/demo/."""

from pathlib import Path

from app.core.models import AppData
from app.data.mock_data import crear_datos_mock
from app.data.serializers import appdata_to_dict, dict_to_appdata, load_json, save_json

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEMO_DIR = PROJECT_ROOT / "data" / "demo"
DEMO_FILE = DEMO_DIR / "datos_hotel.json"


def demo_exists() -> bool:
    return DEMO_FILE.exists()


def save_demo_files(data: AppData | None = None) -> Path:
    payload = appdata_to_dict(data or crear_datos_mock())
    save_json(DEMO_FILE, payload)
    return DEMO_FILE


def load_demo_files() -> AppData:
    if not demo_exists():
        save_demo_files()
    return dict_to_appdata(load_json(DEMO_FILE))


def delete_demo_files() -> bool:
    if DEMO_FILE.exists():
        DEMO_FILE.unlink()
        return True
    return False
