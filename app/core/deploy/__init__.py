"""Despliegue local (estrategia C): perfil hotel, rutas de instancia y escritor único.

No empaqueta ``.exe``. No sustituye Streamlit ni el backup canónico schema v2.
"""

from __future__ import annotations

from app.core.deploy.config import DeployConfig, DeployConfigError, load_deploy_config
from app.core.deploy.writer_lock import WriterLockError, WriterLockInfo

__all__ = [
    "DeployConfig",
    "DeployConfigError",
    "WriterLockError",
    "WriterLockInfo",
    "load_deploy_config",
]
