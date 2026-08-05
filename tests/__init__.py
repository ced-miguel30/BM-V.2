"""Paquete de tests BM-V.2.

Única responsabilidad al importar: activar la red de seguridad
``BM_TEST_ISOLATION=1`` (bloquea escrituras a la ruta canónica del demo).

F18: instala una AuthSession de Dirección por defecto para tests de dominio
legados (mecanismo explícito del harness de tests, no bypass de producción).
Los tests F18 que validan rechazo llaman ``clear_test_session()``.

No monkeypatchea ``save_json`` / ``persist_data`` / ``save_demo_files``.
Cada test que persiste debe usar aislamiento local explícito.
"""

from __future__ import annotations

from tests.demo_isolation import enable_test_isolation_env

enable_test_isolation_env()

from tests.auth_harness import restore_harness_session

restore_harness_session()
