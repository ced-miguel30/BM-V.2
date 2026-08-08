"""F19 — cierre de cobertura residual de autorización.

    python -m unittest tests.test_f19_residual_auth -v
"""

from __future__ import annotations

import hashlib
import os
import sys
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
from app.core.auth.session import (
    AuthSession,
    clear_test_session,
    set_test_session,
)
from app.core.models import (
    AppData,
    CategoriaReceta,
    IngredienteReceta,
    LoteStock,
    Producto,
    Proveedor,
    Receta,
    UnidadProducto,
)
from app.core.services import (
    albaran_service,
    analitica_consumo_service,
    bi_service,
    catalogo_service,
    costes_service,
    dashboard_service,
    factura_service,
    merma_analisis_service,
    proveedor_service,
    receta_service,
    rectificativa_service,
    sidebar_service,
    stock_service,
)
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    sha256_demo_file,
)
from app.data.serializers import appdata_to_dict
from tests.auth_harness import restore_harness_session


def _sess(role: str, *, actor_type: str = "usuario", actor_id: str = "u1") -> AuthSession:
    return AuthSession(
        authenticated=True,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=role,
        role=role,
        session_id=f"f19-{role}",
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
        recetas=[
            Receta(
                "r1",
                "Tostada",
                [IngredienteReceta("p1", 1.0)],
                CategoriaReceta.DESAYUNO,
            )
        ],
        proveedores=[
            Proveedor(id="prov1", nombre_fiscal="Prov SA", codigo="PROV1", activo=True)
        ],
    )


class TestF19ResidualAuth(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _data()
        self._session: dict = {}
        self._st = patch("streamlit.session_state", self._session)
        self._st.start()
        clear_test_session()
        self.addCleanup(self._st.stop)
        self.addCleanup(restore_harness_session)
        self._repo_patch = patch(
            "app.core.services.data_service.get_repository",
            return_value=_FakeRepo(self.data),
        )
        # Prefer InMemory via get_data patches where services use get_data/get_repository
        self.addCleanup(lambda: None)

    def _ctx(self, label: str = "Actor"):
        return build_app_context(
            uow=InMemoryUnitOfWork(self.data),
            clock=FixedClock(datetime(2026, 7, 30, 8, 0, 0)),
            actor=Actor(id="a1", nombre=label, rol="x"),
        )

    def _snap(self) -> tuple:
        return (
            appdata_to_dict(self.data),
            self.data.lotes[0].cantidad_restante,
            list(getattr(self.data, "movimientos", []) or []),
            len(self.data.productos),
            len(self.data.recetas),
            len(getattr(self.data, "documentos", []) or []),
            len(getattr(self.data, "departamentos", []) or []),
        )

    def test_01_costes_siblings_admin_ok_terminal_deny(self) -> None:
        set_test_session(_sess("administracion"))
        with patch(
            "app.core.services.costes_service.get_repository",
            return_value=_FakeRepo(self.data),
        ):
            r = costes_service.resumen_periodo(
                date(2026, 7, 1), date(2026, 7, 31), ["Consumo"]
            )
            self.assertIn("total", r)
            costes_service.comparar_periodos(
                date(2026, 7, 1),
                date(2026, 7, 15),
                date(2026, 6, 1),
                date(2026, 6, 15),
                ["Consumo"],
            )
            costes_service.costes_consumo_por_servicio(date(2026, 7, 1), date(2026, 7, 31))
            costes_service.desglose_costes_desayuno(date(2026, 7, 1), date(2026, 7, 31))
            costes_service.top_generadores_coste(date(2026, 7, 1), date(2026, 7, 31))
            costes_service.top_recetas_coste(date(2026, 7, 1), date(2026, 7, 31))
            costes_service.evolucion_coste_naturaleza(date(2026, 7, 1), date(2026, 7, 31))

        set_test_session(_sess("restaurante", actor_type="terminal"))
        with self.assertRaises(AuthorizationError):
            costes_service.resumen_periodo(
                date(2026, 7, 1), date(2026, 7, 31), ["Consumo"]
            )
        with self.assertRaises(AuthorizationError):
            costes_service.costes_consumo_por_servicio(date(2026, 7, 1), date(2026, 7, 31))

    def test_02_recepcion_sin_costes_ni_analisis(self) -> None:
        set_test_session(_sess("recepcion"))
        with self.assertRaises(AuthorizationError):
            costes_service.exportar_costes_excel(
                date(2026, 7, 1),
                date(2026, 7, 31),
                date(2026, 6, 1),
                date(2026, 6, 30),
                ["Consumo"],
            )
        with self.assertRaises(AuthorizationError):
            merma_analisis_service.resumen_merma(date(2026, 7, 1), date(2026, 7, 31), data=self.data)
        with self.assertRaises(AuthorizationError):
            analitica_consumo_service.resumen_consumo(
                date(2026, 7, 1), date(2026, 7, 31), data=self.data
            )
        with self.assertRaises(AuthorizationError):
            dashboard_service.evolucion_por_categoria(
                date(2026, 7, 1), date(2026, 7, 31), data=self.data
            )
        with self.assertRaises(AuthorizationError):
            bi_service.resumen_automatico()
        with self.assertRaises(AuthorizationError):
            sidebar_service.resumen_sidebar()

    def test_03_sesion_ausente_y_falsificada(self) -> None:
        clear_test_session()
        with self.assertRaises(AuthorizationError):
            costes_service.top_generadores_coste(date(2026, 7, 1), date(2026, 7, 31))
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
        with self.assertRaises(AuthorizationError):
            sidebar_service.resumen_sidebar()
        before = self._snap()
        self.assertFalse(
            stock_service.editar_producto_catalogo(
                "p1", servicios_disponibles=["desayuno"]
            ).ok
        )
        self.assertEqual(self._snap(), before)

    def test_04_crud_producto_receta_matriz(self) -> None:
        set_test_session(_sess("direccion"))
        with patch("app.core.services.stock_service.get_data", return_value=self.data), patch(
            "app.core.services.stock_service.persist_data"
        ), patch("app.core.services.receta_service.get_data", return_value=self.data), patch(
            "app.core.services.receta_service.persist_data"
        ):
            self.assertTrue(
                stock_service.editar_producto_catalogo(
                    "p1", servicios_disponibles=["desayuno", "comida"]
                ).ok
            )
            self.assertTrue(
                receta_service.editar_receta(
                    "r1",
                    "Tostada 2",
                    [IngredienteReceta("p1", 1.0)],
                    CategoriaReceta.DESAYUNO,
                ).ok
            )

        set_test_session(_sess("recepcion"))
        before = self._snap()
        with patch("app.core.services.stock_service.get_data", return_value=self.data), patch(
            "app.core.services.receta_service.get_data", return_value=self.data
        ):
            self.assertFalse(
                stock_service.editar_producto_catalogo(
                    "p1", servicios_disponibles=["cena"]
                ).ok
            )
            self.assertFalse(
                receta_service.eliminar_receta("r1").ok
            )
        self.assertEqual(len(self.data.recetas), before[4])
        self.assertEqual(self.data.lotes[0].cantidad_restante, before[1])

        set_test_session(_sess("restaurante", actor_type="terminal"))
        with patch("app.core.services.receta_service.get_data", return_value=self.data):
            self.assertFalse(
                receta_service.editar_receta(
                    "r1",
                    "X",
                    [IngredienteReceta("p1", 1.0)],
                ).ok
            )

    def test_05_crud_proveedor_catalogo(self) -> None:
        ctx = self._ctx("Dir")
        set_test_session(_sess("administracion"))
        self.assertTrue(catalogo_service.crear_departamento("Cocina F19", ctx=ctx).ok)
        self.assertTrue(
            proveedor_service.editar_proveedor(
                "prov1", nombre_fiscal="Prov SA Edit", ctx=ctx
            ).ok
        )

        set_test_session(_sess("recepcion"))
        before_deps = len(self.data.departamentos)
        before_prov = self.data.proveedores[0].nombre_fiscal
        self.assertFalse(catalogo_service.crear_departamento("Hack Dep", ctx=ctx).ok)
        self.assertFalse(
            proveedor_service.desactivar_proveedor("prov1", ctx=ctx).ok
        )
        self.assertEqual(len(self.data.departamentos), before_deps)
        self.assertEqual(self.data.proveedores[0].nombre_fiscal, before_prov)

        set_test_session(_sess("restaurante", actor_type="terminal"))
        self.assertFalse(
            catalogo_service.crear_categoria("Cat Hack", ctx=ctx).ok
        )

    def test_06_legacy_albaran_factura_rechazo_antes_escritura(self) -> None:
        ctx = self._ctx()
        set_test_session(_sess("recepcion"))
        before = self._snap()
        r = albaran_service.crear_borrador_albaran(ctx=ctx)
        self.assertFalse(r.ok)
        self.assertEqual(self._snap(), before)

        r2 = factura_service.crear_borrador_factura(ctx=ctx)
        self.assertFalse(r2.ok)
        self.assertEqual(self._snap(), before)

        r3 = rectificativa_service.crear_borrador_rectificativa(
            "missing",
            motivo="x",
            ctx=ctx,
        )
        self.assertFalse(r3.ok)
        self.assertEqual(self._snap(), before)

        set_test_session(_sess("restaurante", actor_type="terminal"))
        before2 = self._snap()
        self.assertFalse(albaran_service.confirmar_albaran("nope", ctx=ctx).ok)
        self.assertFalse(factura_service.anular_factura("nope", ctx=ctx).ok)
        self.assertEqual(self._snap(), before2)

    def test_07_legacy_autorizado_direccion(self) -> None:
        ctx = self._ctx("Dir")
        set_test_session(_sess("direccion"))
        r = albaran_service.crear_borrador_albaran(
            proveedor_id="prov1", ctx=ctx
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertTrue(any(d.id == r.documento.id for d in self.data.documentos))

        r_f = factura_service.crear_borrador_factura(proveedor_id="prov1", ctx=ctx)
        self.assertTrue(r_f.ok, r_f.mensaje)

    def test_08_helpers_puros_sin_auth(self) -> None:
        clear_test_session()
        # date math / string matcher / transform — no AuthSession
        a, b = analitica_consumo_service.periodo_anterior(
            date(2026, 7, 1), date(2026, 7, 31)
        )
        self.assertIsInstance(a, date)
        self.assertIsNone(bi_service.buscar_pregunta("zzz-inexistente-xyz"))
        filas = costes_service.datos_grafico_comparacion(
            {
                "periodo_a": {"costes": {"Consumo": 1.0}},
                "periodo_b": {"costes": {"Consumo": 2.0}},
            }
        )
        self.assertEqual(len(filas), 2)
        self.assertEqual(
            merma_analisis_service.bucket_servicio_linea("desayuno"),
            "desayuno",
        )

    def test_09_compat_f18_registro_y_coste(self) -> None:
        set_test_session(_sess("administracion"))
        with self.assertRaises(AuthorizationError):
            # recepción already covered; terminal:
            set_test_session(_sess("restaurante", actor_type="terminal"))
            costes_service.resumen_ejecutivo_costes(date(2026, 7, 1), date(2026, 7, 31))

    def test_10_demo_hash(self) -> None:
        self.assertEqual(os.environ.get("BM_TEST_ISOLATION"), "1")
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)


class _FakeRepo:
    """Minimal repo surface for costes/sidebar/bi reads."""

    def __init__(self, data: AppData) -> None:
        self.data = data

    def formato_precio(self, v: float) -> str:
        return f"{v:.2f} €"

    def coste_consumo_mes(self) -> float:
        return 0.0

    def coste_total_mes(self) -> float:
        return 0.0

    def coste_merma_periodo(self, *_a, **_k) -> float:
        return 0.0

    def coste_expiracion_periodo(self, *_a, **_k) -> float:
        return 0.0

    def top_productos_costosos_periodo(self, *_a, **_k) -> list:
        return []

    def alertas_activas(self) -> list:
        return []

    def productos_stock_bajo(self) -> list:
        return []

    def productos_stock_negativo(self) -> list:
        return []

    def productos_stock_cero(self) -> list:
        return []

    def desayuno_registrado_hoy(self) -> bool:
        return True

    def get_nombre_producto(self, pid: str) -> str:
        return pid


# Patch bi/sidebar get_repository for deny tests that raise before repo use —
# still needed for authorized paths in other modules via harness + real repo.
# For resumen_automatico deny, AuthorizationError raises before get_repository.


if __name__ == "__main__":
    unittest.main()
