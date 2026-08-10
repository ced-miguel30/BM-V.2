"""Shim de compatibilidad hacia el composition root.

NO es almacenamiento independiente de UI. Delega en
``app.bootstrap.get_container().app_data_store``.

En Streamlit, ``configure_for_streamlit()`` instala el adaptador de
``st.session_state``. En tests/scripts, el store por defecto es file-backed
sin Streamlit (o el configurado vía ``configure_for_tests``).

Preferir: ``from app.bootstrap import get_container``.
"""

from __future__ import annotations

from app.bootstrap import get_container
from app.core.models import AppData
from app.core.storage.demo_files import get_demo_file

SESSION_KEY = "bm_data"  # clave histórica del adaptador Streamlit


def init_data() -> AppData:
    return get_container().app_data_store.get()


def get_data() -> AppData:
    return get_container().app_data_store.get()


def persist_data(data: AppData) -> AppData:
    return get_container().app_data_store.persist(data)


def reset_data() -> AppData:
    from app.data.mock_data import crear_datos_mock

    return persist_data(crear_datos_mock())


def reload_from_disk() -> AppData:
    return get_container().app_data_store.reload_from_disk()


def get_demo_path() -> str:
    return str(get_demo_file())
