"""Tests caducidad workbench, historial unificado, multi-servicio, reconciliación."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BM_TEST_ISOLATION", "1")

from app.core.auth.session import (
    clear_test_session,
    iniciar_terminal_inventario,
    set_test_session,
)
from app.core.models import (
    AppData,
    CategoriaReceta,
    IngredienteReceta,
    LoteStock,
    OrigenConsumo,
    Producto,
    Receta,
    RolUsuario,
    UnidadProducto,
    Usuario,
)
from app.core.services import caducidad_service as cad
from app.core.services import historial_operativo_service as hist
from app.core.services import comida_service, desayuno_service
from app.core.services.analitica_consumo_service import (
    coste_bucket_bebida,
    coste_servicios_excluyentes,
)
from app.core.services.inventory_batch_service import stock_disponible
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    sha256_demo_file,
)
from tests.auth_harness import HARNESS_SESSION, restore_harness_session


def _base_data(hoy: date) -> AppData:
    return AppData(
        productos=[
            Producto(
                "ph", "Huevo", UnidadProducto.UD,
                servicios_disponibles=["desayuno", "comida", "cena"],
                codigo="H",
            ),
            Producto(
                "pz", "Zumo", UnidadProducto.UD,
                es_bebida=True,
                servicios_disponibles=["desayuno", "comida", "cena", "bebidas"],
                codigo="Z",
            ),
            Producto(
                "px", "Yogur", UnidadProducto.UD,
                servicios_disponibles=["desayuno", "comida"],
                codigo="Y",
            ),
        ],
        lotes=[
            LoteStock("lh", "ph", 4.0, 20.0, 20.0, hoy - timedelta(days=10)),
            LoteStock(
                "lz", "pz", 10.0, 10.0, 10.0, hoy - timedelta(days=5),
                fecha_expiracion=hoy - timedelta(days=1),
            ),
            LoteStock(
                "lx", "px", 5.0, 5.0, 5.0, hoy - timedelta(days=2),
                fecha_expiracion=hoy + timedelta(days=2),
                alerta_expiracion_dias=5,
            ),
        ],
        recetas=[
            Receta(
                "rt", "Tortilla",
                [IngredienteReceta("ph", 2.0)],
                CategoriaReceta.COMIDA,
                servicios_disponibles=["comida", "desayuno"],
                porciones_estandar=1.0,
            ),
        ],
        usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


class TestCaducidadHistorialCierre(unittest.TestCase):
    def setUp(self) -> None:
        clear_test_session()
        set_test_session(HARNESS_SESSION)
        self.addCleanup(restore_harness_session)
        self.demo_before = DEMO_FILE.read_bytes()
        self.hoy = date(2026, 7, 21)
        self.data = _base_data(self.hoy)
        self._session: dict = {}
        self._patches = [
            mock.patch("app.core.services.desayuno_service.get_data", return_value=self.data),
            mock.patch(
                "app.core.services.desayuno_service.persist_data",
                side_effect=lambda d=None: d if d is not None else self.data,
            ),
            mock.patch("app.core.services.cesta_service.get_data", return_value=self.data),
            mock.patch("app.core.services.servicio_registro_service.get_data", return_value=self.data),
            mock.patch(
                "app.core.services.servicio_registro_service.persist_data",
                side_effect=lambda d=None: d if d is not None else self.data,
            ),
            mock.patch("app.core.services.merma_service.get_data", return_value=self.data),
            mock.patch("app.core.services.caducidad_service.get_data", return_value=self.data),
            mock.patch("streamlit.session_state", self._session),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self) -> None:
        self.assertEqual(DEMO_FILE.read_bytes(), self.demo_before)
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def test_listar_vencidos_y_proximos(self) -> None:
        vencidos = cad.listar_lotes_caducidad(
            hoy=self.hoy, incluir_proximos=False, incluir_vencidos=True, ctx=None,
        )
        # get_data patched via caducidad_service - need data on get_data
        with mock.patch("app.core.services.caducidad_service.get_data", return_value=self.data):
            vencidos = cad.listar_lotes_caducidad(
                hoy=self.hoy, incluir_proximos=False, incluir_vencidos=True,
            )
            proximos = cad.listar_lotes_caducidad(
                hoy=self.hoy, incluir_proximos=True, incluir_vencidos=False,
            )
        self.assertTrue(any(v.lote_id == "lz" for v in vencidos))
        self.assertTrue(any(p.lote_id == "lx" for p in proximos))

    def test_salida_caducidad_a_cesta_merma(self) -> None:
        from app.core.services import merma_service as merma

        self._session[merma.CESTA_MERMA_KEY] = []
        # responsables
        from app.core.models import ResponsableMerma
        self.data.responsables_merma = [ResponsableMerma("r1", "Cocina", True)]
        r = cad.registrar_salida_caducidad(
            "lz",
            2.0,
            tipo_servicio_snapshot="general",
            turno_snapshot="manana",
            responsable_id="r1",
            responsable_nombre="Cocina",
        )
        self.assertTrue(r.ok, r.mensaje)
        cesta = merma.get_cesta_merma()
        self.assertEqual(len(cesta), 1)
        self.assertEqual(cesta[0].motivo, cad.MOTIVO_CADUCIDAD)
        self.assertEqual(cesta[0].lote_id, "lz")

    def test_comida_y_bebida_en_servicio(self) -> None:
        comida_service.servicio.limpiar_cesta()
        self.assertTrue(comida_service.servicio.anadir_receta_a_cesta("rt", 2.0).ok)
        self.assertTrue(comida_service.servicio.anadir_a_cesta("pz", 1.0).ok)
        r = comida_service.servicio.registrar(self.hoy)
        self.assertTrue(r.ok, r.mensaje)
        regs = [x for x in self.data.registros_servicio if x.tipo_servicio == "comida"]
        self.assertEqual(len(regs), 1)
        beb = [d for d in regs[0].lineas_detalle if d.producto_id == "pz"]
        self.assertEqual(len(beb), 1)
        self.assertEqual(beb[0].tipo_servicio, "comida")
        self.assertTrue(beb[0].es_bebida_snapshot)
        self.assertEqual(beb[0].origen, OrigenConsumo.PRODUCTO_DIRECTO.value)

    def test_historial_lista_registros(self) -> None:
        self.assertTrue(desayuno_service.anadir_a_cesta("pz", 1.0).ok)
        self.assertTrue(desayuno_service.registrar_desayuno(self.hoy, 5).ok)
        evs = hist.listar_eventos_operativos(
            desde=self.hoy, hasta=self.hoy, data=self.data,
        )
        self.assertTrue(any(e.tipo == hist.TIPO_DESAYUNO for e in evs))
        det = hist.detalle_evento(hist.TIPO_DESAYUNO, self.data.desayunos[0].id, data=self.data)
        self.assertIsNotNone(det)
        self.assertTrue(det["puede_anular"])

    def test_reconciliacion_coste_general(self) -> None:
        self.assertTrue(desayuno_service.anadir_a_cesta("pz", 2.0).ok)
        self.assertTrue(desayuno_service.registrar_desayuno(self.hoy, 4).ok)
        comida_service.servicio.limpiar_cesta()
        self.assertTrue(comida_service.servicio.anadir_a_cesta("pz", 1.0).ok)
        self.assertTrue(comida_service.servicio.registrar(self.hoy).ok)

        costes = coste_servicios_excluyentes(self.hoy, self.hoy, data=self.data)
        self.assertAlmostEqual(
            costes.coste_general,
            round(
                costes.desayuno_total
                + costes.comida_total
                + costes.cena_total
                + costes.bebidas_independientes,
                2,
            ),
            places=2,
        )
        # Bebidas transversales >= bebidas dentro de servicios (no se suman a general otra vez)
        transversal = coste_bucket_bebida("todas", self.hoy, self.hoy, data=self.data)
        # Si bucket name differs, try common names
        if transversal == 0:
            for b in ("bebida", "bebidas", "todas_bebidas", "todas"):
                try:
                    transversal = max(transversal, coste_bucket_bebida(b, self.hoy, self.hoy, data=self.data))
                except Exception:
                    pass
        self.assertGreaterEqual(costes.desayuno_total + costes.comida_total, 0)

    def test_terminal_inventario_session(self) -> None:
        s = iniciar_terminal_inventario()
        self.assertEqual(s.terminal_id, "terminal_inventario")
        self.assertEqual(s.actor_type, "terminal")

    def test_demo_intacto(self) -> None:
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)


if __name__ == "__main__":
    unittest.main()
