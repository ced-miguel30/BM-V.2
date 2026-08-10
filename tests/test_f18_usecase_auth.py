"""F18 — autorización en frontera de casos de uso de dominio.

    python -m unittest tests.test_f18_usecase_auth -v
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["BM_TEST_ISOLATION"] = "1"

from app.core.application.actor import Actor
from app.core.application.clock import FixedClock
from app.core.application.context import build_app_context
from app.core.application.unit_of_work import InMemoryUnitOfWork
from app.core.auth.permissions import AuthorizationError, Permiso
from tests.auth_harness import restore_harness_session
from app.core.auth.session import (
    AuthSession,
    clear_test_session,
    set_test_session,
)
from app.core.models import (
    AppData,
    LoteStock,
    MotivoAjuste,
    Producto,
    UnidadProducto,
)
from app.core.services import ajuste_service, backup_service as bak
from app.core.services import costes_service
from app.core.services import desayuno_service
from app.core.services import destructive_ops_service as dop
from app.core.services import restore_backup_service as rst
from app.core.services import stock_service
from app.core.services.cesta_service import LineaCesta
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    set_demo_file_override,
    sha256_demo_file,
)
from app.core.storage.json_atomic import atomic_write_json
from app.data.serializers import appdata_to_dict, dict_to_appdata


def _sess(role: str, *, actor_type: str = "usuario", actor_id: str = "u1") -> AuthSession:
    return AuthSession(
        authenticated=True,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=role,
        role=role,
        session_id=f"f18-{role}",
        login_at="2026-01-01T00:00:00",
        terminal_id="terminal_restaurante" if actor_type == "terminal" else None,
    )


def _data() -> AppData:
    return AppData(
        productos=[
            Producto(
                "p1",
                "Pan",
                UnidadProducto.UD,
                servicios_disponibles=["desayuno"],
            )
        ],
        lotes=[
            LoteStock(
                "l1",
                "p1",
                precio_total=10.0,
                cantidad=20.0,
                cantidad_restante=20.0,
                fecha_compra=date(2026, 7, 1),
            )
        ],
    )


class TestF18UseCaseAuth(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _data()
        self._session: dict = {}
        self._st = patch("streamlit.session_state", self._session)
        self._st.start()
        clear_test_session()
        self.addCleanup(self._st.stop)
        self.addCleanup(restore_harness_session)
        from tests.streamlit_store_harness import cleanup_container, use_patched_streamlit_stores

        use_patched_streamlit_stores()
        self.addCleanup(cleanup_container)

    def _ctx(self, label: str = "Actor") -> object:
        return build_app_context(
            uow=InMemoryUnitOfWork(self.data),
            clock=FixedClock(datetime(2026, 7, 30, 8, 0, 0)),
            actor=Actor(id="a1", nombre=label, rol="x"),
        )

    def _prep_cesta(self) -> None:
        self._session[desayuno_service.CESTA_SESSION_KEY] = [
            LineaCesta(
                linea_id="c1",
                producto_id="p1",
                nombre="Pan",
                unidad="Ud",
                cantidad=1.0,
            ),
        ]
        self._session[desayuno_service.CESTA_RECETAS_KEY] = []

    def test_01_direccion_registro(self) -> None:
        set_test_session(_sess("direccion"))
        self._prep_cesta()
        r = desayuno_service.registrar_desayuno(date(2026, 7, 28), 2, ctx=self._ctx("Dir"))
        self.assertTrue(r.ok, r.mensaje)

    def test_02_admin_registro_y_ajuste(self) -> None:
        set_test_session(_sess("administracion"))
        self._prep_cesta()
        self.assertTrue(
            desayuno_service.registrar_desayuno(date(2026, 7, 28), 2, ctx=self._ctx("Adm")).ok
        )
        r = ajuste_service.aplicar_ajuste(
            date(2026, 7, 22),
            "l1",
            18.0,
            MotivoAjuste.RECONTEO_FISICO.value,
            "ok",
            ctx=self._ctx("Adm"),
        )
        self.assertTrue(r.ok, r.mensaje)

    def test_03_admin_no_c2_c3(self) -> None:
        set_test_session(_sess("administracion"))
        self.assertFalse(
            rst.restaurar_desde_bytes(b"x", destino_json=Path("x")).ok
        )
        self.assertFalse(
            dop.restablecer_a_datos_mock(
                confirmacion_escrita=dop.FRASE_RESET_TOTAL,
                checkbox_aceptado=True,
                destino_json=Path("x"),
            ).ok
        )

    def test_04_recepcion_rechazada_todo(self) -> None:
        set_test_session(_sess("recepcion"))
        self._prep_cesta()
        before = self.data.lotes[0].cantidad_restante
        r = desayuno_service.registrar_desayuno(date(2026, 7, 28), 2, ctx=self._ctx())
        self.assertFalse(r.ok)
        self.assertEqual(self.data.lotes[0].cantidad_restante, before)
        self.assertFalse(
            stock_service.registrar_lote("p1", 1.0, 1.0, fecha_compra=date(2026, 7, 1)).ok
        )
        self.assertFalse(
            ajuste_service.aplicar_ajuste(
                date(2026, 7, 22), "l1", 1.0, MotivoAjuste.RECONTEO_FISICO.value, ctx=self._ctx()
            ).ok
        )
        with self.assertRaises(AuthorizationError):
            costes_service.resumen_ejecutivo_costes(date(2026, 7, 1), date(2026, 7, 31))

    def test_05_06_07_terminal_limites(self) -> None:
        set_test_session(
            _sess("restaurante", actor_type="terminal", actor_id="terminal_restaurante")
        )
        self._prep_cesta()
        before = self.data.lotes[0].cantidad_restante
        r = desayuno_service.registrar_desayuno(
            date(2026, 7, 28), 2, ctx=self._ctx("Restaurante")
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(self.data.lotes[0].cantidad_restante, before - 1.0)
        self.assertEqual(self.data.desayunos[0].registrado_por, "Restaurante")
        self.assertFalse(
            stock_service.registrar_lote("p1", 1.0, 1.0, fecha_compra=date(2026, 7, 1)).ok
        )
        self.assertFalse(
            ajuste_service.aplicar_ajuste(
                date(2026, 7, 22), "l1", 1.0, MotivoAjuste.RECONTEO_FISICO.value, ctx=self._ctx()
            ).ok
        )
        with self.assertRaises(AuthorizationError):
            costes_service.resumen_ejecutivo_costes(date(2026, 7, 1), date(2026, 7, 31))

    def test_08_09_sesion_ausente_invalida(self) -> None:
        clear_test_session()
        self._prep_cesta()
        before = self.data.lotes[0].cantidad_restante
        r = desayuno_service.registrar_desayuno(date(2026, 7, 28), 2, ctx=self._ctx())
        self.assertFalse(r.ok)
        self.assertEqual(self.data.lotes[0].cantidad_restante, before)
        set_test_session(
            AuthSession(
                authenticated=False,
                actor_type="usuario",
                actor_id="x",
                actor_label="x",
                role="direccion",
                session_id="",
                login_at="",
            )
        )
        r2 = desayuno_service.registrar_desayuno(date(2026, 7, 28), 2, ctx=self._ctx())
        self.assertFalse(r2.ok)

    def test_10_11_manipulacion_no_concede(self) -> None:
        # Rol "direccion" en objeto no autenticado → None
        set_test_session(
            AuthSession(
                authenticated=False,
                actor_type="usuario",
                actor_id="hack",
                actor_label="Hack",
                role="direccion",
                session_id="x",
                login_at="",
            )
        )
        self.assertFalse(
            stock_service.registrar_lote("p1", 1.0, 1.0, fecha_compra=date(2026, 7, 1)).ok
        )

    def test_12_13_14_15_auth_antes_escritura(self) -> None:
        set_test_session(_sess("recepcion"))
        self._prep_cesta()
        before_json = appdata_to_dict(self.data)
        before_lote = self.data.lotes[0].cantidad_restante
        before_mov = list(getattr(self.data, "movimientos", []) or [])
        desayuno_service.registrar_desayuno(date(2026, 7, 28), 2, ctx=self._ctx())
        self.assertEqual(self.data.lotes[0].cantidad_restante, before_lote)
        self.assertEqual(list(getattr(self.data, "movimientos", []) or []), before_mov)
        self.assertEqual(len(self.data.desayunos), 0)
        # JSON shape estable
        self.assertEqual(
            len(before_json.get("productos", [])),
            len(appdata_to_dict(self.data).get("productos", [])),
        )

    def test_16_adjuntos_no_publicados_en_rechazo(self) -> None:
        # confirmar_compra rechazado no llega a publish — comprobamos early return
        set_test_session(_sess("restaurante", actor_type="terminal"))
        from app.core.services import compra_registro_service as crs

        r = crs.confirmar_compra(
            "doc1",
            confirmacion_id="x",
            contenido_hash="y",
            json_path=Path("noop.json"),
        )
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo, "no_autorizado")
        self.assertIsNone(r.adjuntos_publicados)

    def test_17_18_autorizado_conserva_resultado(self) -> None:
        set_test_session(_sess("direccion"))
        self._prep_cesta()
        r = desayuno_service.registrar_desayuno(
            date(2026, 7, 28), 3, ctx=self._ctx("Dir")
        )
        self.assertTrue(r.ok)
        self.assertEqual(self.data.desayunos[0].registrado_por, "Dir")

    def test_19_helpers_sin_streamlit(self) -> None:
        from app.core.services.inventory_batch_service import snapshot_cantidades_restantes

        snap = snapshot_cantidades_restantes(self.data)
        self.assertIn("l1", snap)

    def test_20_historico_carga(self) -> None:
        from app.data.serializers import _usuario_from_dict

        u = _usuario_from_dict(
            {"id": "uh", "nombre": "H", "rol": "Owner", "activo": True}
        )
        self.assertEqual(u.password_hash, "")

    def test_21_22_23_demo_hash_limpieza(self) -> None:
        self.assertEqual(os.environ.get("BM_TEST_ISOLATION"), "1")
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)


class TestF18ExportBackupGate(unittest.TestCase):
    def setUp(self) -> None:
        clear_test_session()
        self.addCleanup(restore_harness_session)
        self.addCleanup(lambda: restore_harness_session())

    def test_export_requiere_permiso(self) -> None:
        set_test_session(_sess("recepcion"))
        with self.assertRaises(AuthorizationError):
            bak.generar_backup_zip(AppData())
        set_test_session(_sess("administracion"))
        r = bak.generar_backup_zip(AppData())
        self.assertTrue(r.contenido)


if __name__ == "__main__":
    unittest.main()
