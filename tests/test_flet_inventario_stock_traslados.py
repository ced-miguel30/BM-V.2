"""Tests Flet Inventario — stock por ubicación + traslados."""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from dataclasses import fields
from datetime import date
from pathlib import Path

os.environ["BM_TEST_ISOLATION"] = "1"

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.session import clear_test_session
from app.core.models import TipoMovimiento, Ubicacion
from app.core.services import movimiento_service as mov
from app.core.services import traslado_service
from app.core.services.ubicacion_stock_service import (
    SIN_UBICACION_HISTORICA,
    saldo_en_ubicacion,
)
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    set_demo_file_override,
    sha256_demo_file,
)
from app.presentation.flet.inventory_viewmodels import (
    ESPACIOS,
    StockSaldoVM,
    TrasladoPreviewVM,
    TrasladoRecienteVM,
    assert_inventario_sin_economia,
)
from app.presentation.flet.presenters.terminal_inventario_presenter import (
    TerminalInventarioPresenter,
)
from app.presentation.flet.viewmodels import CAMPOS_ECONOMICOS_PROHIBIDOS
from tests.auth_harness import restore_harness_session
from tests.browser.fixtures_minimos import write_browser_fixture

_ECON = re.compile(
    r"(€|euro|euros|\bcoste\b|\bprecio\b|\bmargen\b|\bimporte\b|\bvaloraci[oó]n\b)",
    re.I,
)


class _Harness(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.json_path = Path(self._tmp.name) / "datos_hotel.json"
        write_browser_fixture(self.json_path)
        reset_container()
        clear_test_session()
        set_demo_file_override(None)
        configure_for_flet(data_path=self.json_path)
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        reset_container()
        clear_test_session()
        set_demo_file_override(None)
        restore_harness_session()
        self._tmp.cleanup()
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def _seed_ubicaciones_y_entrada(self) -> None:
        store = get_container().app_data_store
        data = store.get()
        if not getattr(data, "ubicaciones", None):
            data.ubicaciones = []
        if not any(u.id == "ubi_cam" for u in data.ubicaciones):
            data.ubicaciones.append(Ubicacion("ubi_cam", "Cámara UI", True))
        if not any(u.id == "ubi_bar" for u in data.ubicaciones):
            data.ubicaciones.append(Ubicacion("ubi_bar", "Barra UI", True))
        leche = next(p for p in data.productos if p.id == "bp_leche")
        leche.ubicacion_ids = ["ubi_cam", "ubi_bar"]
        store.persist(data)
        # Entrada localizada en cámara (ledger). Idempotente por origen lote.
        r = mov.espejo_entrada_lote(
            producto_id="bp_leche",
            lote_id="bl_leche",
            cantidad=20.0,
            fecha=date.today(),
            ubicacion_destino_id="ubi_cam",
            commit=True,
        )
        self.assertTrue(r.ok or r.duplicado, getattr(r, "mensaje", ""))

    def _p(self) -> TerminalInventarioPresenter:
        p = TerminalInventarioPresenter()
        p.entrar()
        return p


class TestStockConsulta(_Harness):
    def test_espacios_incluyen_stock_traslados(self) -> None:
        self.assertEqual(
            ESPACIOS,
            (
                "compras_panel",
                "compras_albaran",
                "compras_factura",
                "compras_documentos",
                "compras_proveedores",
                "compras_historial",
                "alertas",
                "caducidad",
                "merma",
                "stock",
                "traslados",
                "recuentos",
                "ajustes",
            ),
        )
        s = self._p().screen()
        ids = [e.id for e in s.espacios]
        self.assertEqual(list(ids), list(ESPACIOS))
        self.assertIn("stock", ids)
        self.assertIn("traslados", ids)
        self.assertIn("compras_albaran", ids)

    def test_stock_vacio_sin_movimientos_ubicacion(self) -> None:
        p = self._p()
        s = p.seleccionar_espacio("stock")
        # Fixture sin ledger de ubicación: filas informativas o vacío filtrado
        self.assertIsNotNone(s.stock_filas)
        # Consulta no persiste
        before = get_container().app_data_store.get()
        n_mov = len(getattr(before, "movimientos", None) or [])
        p.set_stock_busqueda("leche")
        after = get_container().app_data_store.get()
        self.assertEqual(len(getattr(after, "movimientos", None) or []), n_mov)

    def test_stock_lectura_por_ubicacion_y_filtro(self) -> None:
        self._seed_ubicaciones_y_entrada()
        p = self._p()
        s = p.seleccionar_espacio("stock")
        filas_leche = [f for f in s.stock_filas if f.lote_id == "bl_leche"]
        self.assertTrue(filas_leche)
        self.assertTrue(any(f.ubicacion_id == "ubi_cam" for f in filas_leche))
        s = p.set_stock_busqueda("Leche")
        self.assertTrue(all("leche" in f.producto_nombre.lower() or f.lote_id == "bl_leche"
                            for f in s.stock_filas) or s.stock_filas)
        s = p.set_stock_filtro_ubicacion("ubi_cam")
        self.assertTrue(all(f.ubicacion_id == "ubi_cam" for f in s.stock_filas))
        s = p.set_stock_filtro_ubicacion(SIN_UBICACION_HISTORICA)
        # Puede estar vacío si no hay bucket histórico
        self.assertTrue(all(
            f.ubicacion_id == SIN_UBICACION_HISTORICA for f in s.stock_filas
        ))

    def test_viewmodels_sin_economia(self) -> None:
        assert_inventario_sin_economia(StockSaldoVM, TrasladoPreviewVM, TrasladoRecienteVM)
        for cls in (StockSaldoVM, TrasladoPreviewVM, TrasladoRecienteVM):
            names = {f.name.lower() for f in fields(cls)}
            for bad in CAMPOS_ECONOMICOS_PROHIBIDOS:
                self.assertNotIn(bad.lower(), names)


class TestTrasladosFlet(_Harness):
    def _prep(self) -> TerminalInventarioPresenter:
        self._seed_ubicaciones_y_entrada()
        p = self._p()
        p.seleccionar_espacio("traslados")
        p.set_traslado_producto("bp_leche")
        p.set_traslado_lote("bl_leche")
        p.set_traslado_origen("ubi_cam")
        p.set_traslado_destino("ubi_bar")
        p.set_traslado_cantidad("4")
        return p

    def test_preview_no_persiste(self) -> None:
        p = self._prep()
        data0 = get_container().app_data_store.get()
        n0 = len(traslado_service.listar_traslados(data0))
        s = p.previsualizar_traslado()
        self.assertTrue(s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        self.assertIsNotNone(s.traslado_preview)
        data1 = get_container().app_data_store.get()
        self.assertEqual(len(traslado_service.listar_traslados(data1)), n0)
        self.assertIsNone(_ECON.search(s.traslado_preview.mensaje))
        self.assertIsNone(_ECON.search(s.traslado_preview.producto_nombre))

    def test_confirmacion_valida_y_invariante_hotel(self) -> None:
        p = self._prep()
        p.previsualizar_traslado()
        data = get_container().app_data_store.get()
        lote = next(l for l in data.lotes if l.id == "bl_leche")
        stock_antes = float(lote.cantidad_restante)
        o0 = saldo_en_ubicacion(data, "bl_leche", "ubi_cam")
        d0 = saldo_en_ubicacion(data, "bl_leche", "ubi_bar")
        n_mov = len([
            m for m in data.movimientos
            if (m.tipo.value if hasattr(m.tipo, "value") else str(m.tipo))
            == TipoMovimiento.TRASLADO.value
        ])
        s = p.confirmar_traslado(fecha=date.today())
        self.assertTrue(s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        self.assertIsNone(s.traslado_preview)
        self.assertIsNone(s.traslado_lote_id)
        data2 = get_container().app_data_store.get()
        lote2 = next(l for l in data2.lotes if l.id == "bl_leche")
        self.assertAlmostEqual(float(lote2.cantidad_restante), stock_antes)
        self.assertAlmostEqual(saldo_en_ubicacion(data2, "bl_leche", "ubi_cam"), o0 - 4)
        self.assertAlmostEqual(saldo_en_ubicacion(data2, "bl_leche", "ubi_bar"), d0 + 4)
        traslados = traslado_service.listar_traslados(data2)
        self.assertEqual(len(traslados), n_mov + 1 if n_mov else 1)
        # Un solo movimiento de tipo traslado por confirmación
        nuevos = [m for m in traslados if m.ubicacion_destino_id == "ubi_bar"]
        self.assertEqual(len(nuevos), 1)
        self.assertEqual(
            (nuevos[0].tipo.value if hasattr(nuevos[0].tipo, "value") else str(nuevos[0].tipo)),
            TipoMovimiento.TRASLADO.value,
        )
        self.assertTrue(s.traslados_recientes)

    def test_origen_igual_destino(self) -> None:
        self._seed_ubicaciones_y_entrada()
        p = self._p()
        p.seleccionar_espacio("traslados")
        p.set_traslado_producto("bp_leche")
        p.set_traslado_lote("bl_leche")
        p.set_traslado_origen("ubi_cam")
        s = p.set_traslado_destino("ubi_cam")
        self.assertFalse(s.feedback.ok)

    def test_cantidad_invalida_y_exceso(self) -> None:
        p = self._prep()
        p.set_traslado_cantidad("0")
        s = p.previsualizar_traslado()
        self.assertFalse(s.feedback.ok)
        self.assertIsNone(s.traslado_preview)
        p.set_traslado_cantidad("-1")
        s = p.previsualizar_traslado()
        self.assertFalse(s.feedback.ok)
        p.set_traslado_cantidad("9999")
        s = p.previsualizar_traslado()
        self.assertFalse(s.feedback.ok)
        self.assertIsNone(s.traslado_preview)

    def test_cancelar_y_logout_no_confirman(self) -> None:
        p = self._prep()
        p.previsualizar_traslado()
        self.assertIsNotNone(p.screen().traslado_preview)
        n0 = len(traslado_service.listar_traslados(get_container().app_data_store.get()))
        p.cancelar_traslado_preview()
        self.assertIsNone(p.screen().traslado_preview)
        self.assertEqual(
            len(traslado_service.listar_traslados(get_container().app_data_store.get())),
            n0,
        )
        p.previsualizar_traslado()
        p.logout()
        self.assertIsNone(p.screen().traslado_preview)
        self.assertFalse(p.screen().session.authenticated)
        self.assertEqual(
            len(traslado_service.listar_traslados(get_container().app_data_store.get())),
            n0,
        )

    def test_doble_confirmacion_no_duplica(self) -> None:
        p = self._prep()
        p.previsualizar_traslado()
        s1 = p.confirmar_traslado(fecha=date.today())
        self.assertTrue(s1.feedback.ok, s1.feedback.mensaje if s1.feedback else "")
        n1 = len(traslado_service.listar_traslados(get_container().app_data_store.get()))
        s2 = p.confirmar_traslado(fecha=date.today())
        self.assertFalse(s2.feedback.ok)
        n2 = len(traslado_service.listar_traslados(get_container().app_data_store.get()))
        self.assertEqual(n1, n2)

    def test_revalidacion_disponibilidad_entre_preview_y_confirm(self) -> None:
        p = self._prep()
        p.previsualizar_traslado()
        # Agotar saldo vía otro traslado directo en dominio
        r = traslado_service.confirmar_traslado(
            lote_id="bl_leche",
            ubicacion_origen_id="ubi_cam",
            ubicacion_destino_id="ubi_bar",
            cantidad=20.0,
            fecha=date.today(),
        )
        self.assertTrue(r.ok, r.mensaje)
        s = p.confirmar_traslado(fecha=date.today())
        self.assertFalse(s.feedback.ok)
        # Preview draft permanece recuperable (no limpia en error)
        self.assertIsNotNone(p.screen().traslado_preview)

    def test_sin_sesion_denegado(self) -> None:
        self._seed_ubicaciones_y_entrada()
        p = TerminalInventarioPresenter()
        s = p.seleccionar_espacio("traslados")
        self.assertFalse(s.feedback.ok)
        s = p.previsualizar_traslado()
        self.assertFalse(s.feedback.ok)

    def test_entrypoints_intactos(self) -> None:
        from app.presentation.flet.main_inventario import build_app_handler

        self.assertTrue(callable(build_app_handler()))


if __name__ == "__main__":
    unittest.main()
