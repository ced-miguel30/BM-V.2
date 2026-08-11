"""Tests Flet Inventario — Recuentos (7B.6 vía presenter)."""

from __future__ import annotations

import ast
import os
import re
import tempfile
import unittest
from dataclasses import fields
from datetime import date
from pathlib import Path
from unittest.mock import patch

os.environ["BM_TEST_ISOLATION"] = "1"

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.session import clear_test_session
from app.core.models import MotivoAjuste, TipoMovimiento, Ubicacion
from app.core.models.recuento import EstadoRecuento
from app.core.services import movimiento_service as mov
from app.core.services import recuento_service
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
    RecuentoLineaVM,
    RecuentoPendienteVM,
    RecuentoPreviewVM,
    RecuentoRecienteVM,
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

ROOT = Path(__file__).resolve().parent.parent
FLET_ROOT = ROOT / "app" / "presentation" / "flet"


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

    def _seed(self) -> None:
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

    def _prep_lineas(
        self, contada: str, *, ubicacion: str = "ubi_cam"
    ) -> TerminalInventarioPresenter:
        self._seed()
        p = self._p()
        p.seleccionar_espacio("recuentos")
        p.set_recuento_ubicacion(ubicacion)
        p.set_recuento_producto("bp_leche")
        p.set_recuento_lote("bl_leche")
        p.set_recuento_cantidad(contada)
        s = p.anadir_linea_recuento()
        self.assertTrue(s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        return p


class TestRecuentosNav(_Harness):
    def test_01_siete_espacios_orden(self) -> None:
        self.assertEqual(
            ESPACIOS,
            (
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
        self.assertEqual([e.id for e in s.espacios], list(ESPACIOS))
        self.assertEqual(len(s.espacios), 7)

    def test_02_sin_sesion(self) -> None:
        p = TerminalInventarioPresenter()
        s = p.seleccionar_espacio("recuentos")
        self.assertFalse(s.feedback.ok)
        s = p.previsualizar_recuento()
        self.assertFalse(s.feedback.ok)
        s = p.confirmar_recuento()
        self.assertFalse(s.feedback.ok)

    def test_03_sin_economia(self) -> None:
        assert_inventario_sin_economia(
            RecuentoLineaVM, RecuentoPreviewVM, RecuentoPendienteVM, RecuentoRecienteVM
        )
        for cls in (
            RecuentoLineaVM,
            RecuentoPreviewVM,
            RecuentoPendienteVM,
            RecuentoRecienteVM,
        ):
            names = {f.name.lower() for f in fields(cls)}
            for bad in CAMPOS_ECONOMICOS_PROHIBIDOS:
                self.assertNotIn(bad.lower(), names)
        p = self._prep_lineas("20")
        s = p.previsualizar_recuento()
        blob = " ".join(
            [
                s.recuento_preview.mensaje,
                *(
                    f"{ln.producto_nombre} {ln.unidad} {ln.efecto}"
                    for ln in s.recuento_preview.lineas
                ),
            ]
        )
        self.assertIsNone(_ECON.search(blob))


class TestRecuentosFormulario(_Harness):
    def test_04_cascada_ubicacion_producto_lote(self) -> None:
        self._seed()
        p = self._p()
        p.seleccionar_espacio("recuentos")
        s = p.set_recuento_ubicacion("ubi_cam")
        self.assertTrue(s.recuento_productos)
        self.assertIsNone(s.recuento_producto_id)
        self.assertFalse(s.recuento_lotes)
        s = p.set_recuento_producto("bp_leche")
        self.assertTrue(s.recuento_lotes)
        self.assertIsNone(s.recuento_lote_id)
        p.set_recuento_lote("bl_leche")
        p.set_recuento_cantidad("5")
        p.anadir_linea_recuento()
        p.previsualizar_recuento()
        self.assertIsNotNone(p.screen().recuento_preview)
        s = p.set_recuento_ubicacion("ubi_bar")
        self.assertEqual(s.recuento_lineas, ())
        self.assertIsNone(s.recuento_preview)
        self.assertIsNone(s.recuento_producto_id)

    def test_05_rechazo_ubicacion_historica(self) -> None:
        self._seed()
        p = self._p()
        p.seleccionar_espacio("recuentos")
        s = p.set_recuento_ubicacion(SIN_UBICACION_HISTORICA)
        self.assertFalse(s.feedback.ok)
        self.assertIsNone(s.recuento_ubicacion_id)
        self.assertTrue(
            all(o.id != SIN_UBICACION_HISTORICA for o in s.recuento_ubicaciones)
        )

    def test_06_cantidad_negativa(self) -> None:
        self._seed()
        p = self._p()
        p.seleccionar_espacio("recuentos")
        p.set_recuento_ubicacion("ubi_cam")
        p.set_recuento_producto("bp_leche")
        p.set_recuento_lote("bl_leche")
        p.set_recuento_cantidad("-1")
        s = p.anadir_linea_recuento()
        self.assertFalse(s.feedback.ok)
        self.assertEqual(s.recuento_lineas, ())

    def test_07_cantidad_cero(self) -> None:
        p = self._prep_lineas("0")
        self.assertEqual(len(p.screen().recuento_lineas), 1)
        self.assertAlmostEqual(p.screen().recuento_lineas[0].cantidad_contada, 0.0)
        self.assertEqual(p.screen().recuento_lineas[0].efecto, "salida")

    def test_08_cantidad_decimal(self) -> None:
        p = self._prep_lineas("18.12345")
        # round(..., 4) bancario de Python → 18.1234
        self.assertAlmostEqual(p.screen().recuento_lineas[0].cantidad_contada, 18.1234)

    def test_09_producto_lote_incompatibles(self) -> None:
        self._seed()
        p = self._p()
        p.seleccionar_espacio("recuentos")
        p.set_recuento_ubicacion("ubi_cam")
        p.set_recuento_producto("bp_leche")
        p.set_recuento_lote("bl_leche")
        # Forzar producto distinto manteniendo lote
        p._rc_producto_id = "bp_pan"  # noqa: SLF001
        p.set_recuento_cantidad("1")
        s = p.anadir_linea_recuento()
        self.assertFalse(s.feedback.ok)

    def test_10_linea_duplicada(self) -> None:
        p = self._prep_lineas("20")
        p.set_recuento_producto("bp_leche")
        p.set_recuento_lote("bl_leche")
        p.set_recuento_cantidad("19")
        s = p.anadir_linea_recuento()
        self.assertFalse(s.feedback.ok)
        self.assertEqual(len(p.screen().recuento_lineas), 1)


class TestRecuentosPreviewMemoria(_Harness):
    def test_11_preview_sin_persistencia(self) -> None:
        p = self._prep_lineas("19")
        data0 = get_container().app_data_store.get()
        n_rc = len(getattr(data0, "recuentos", None) or [])
        n_aj = len(data0.ajustes)
        n_mov = len(getattr(data0, "movimientos", None) or [])
        stock0 = next(l for l in data0.lotes if l.id == "bl_leche").cantidad_restante
        s = p.previsualizar_recuento()
        self.assertTrue(s.feedback.ok)
        self.assertIsNotNone(s.recuento_preview)
        self.assertTrue(s.recuento_preview.en_memoria)
        data1 = get_container().app_data_store.get()
        self.assertEqual(len(getattr(data1, "recuentos", None) or []), n_rc)
        self.assertEqual(len(data1.ajustes), n_aj)
        self.assertEqual(len(getattr(data1, "movimientos", None) or []), n_mov)
        self.assertAlmostEqual(
            next(l for l in data1.lotes if l.id == "bl_leche").cantidad_restante,
            stock0,
        )

    def test_12_cancelar_antes_borrador(self) -> None:
        p = self._prep_lineas("19")
        p.previsualizar_recuento()
        n0 = len(getattr(get_container().app_data_store.get(), "recuentos", None) or [])
        s = p.cancelar_recuento_memoria()
        self.assertTrue(s.feedback.ok)
        self.assertEqual(s.recuento_lineas, ())
        self.assertIsNone(s.recuento_preview)
        self.assertEqual(
            len(getattr(get_container().app_data_store.get(), "recuentos", None) or []),
            n0,
        )

    def test_13_cambio_espacio_volver_logout_sin_confirmar(self) -> None:
        p = self._prep_lineas("19")
        p.previsualizar_recuento()
        n0 = len(getattr(get_container().app_data_store.get(), "recuentos", None) or [])
        p.seleccionar_espacio("stock")
        self.assertEqual(
            len(getattr(get_container().app_data_store.get(), "recuentos", None) or []),
            n0,
        )
        p.seleccionar_espacio("recuentos")
        p.set_recuento_ubicacion("ubi_cam")
        p.set_recuento_producto("bp_leche")
        p.set_recuento_lote("bl_leche")
        p.set_recuento_cantidad("19")
        p.anadir_linea_recuento()
        p.previsualizar_recuento()
        p.preparar_salida()
        self.assertEqual(
            len(getattr(get_container().app_data_store.get(), "recuentos", None) or []),
            n0,
        )
        p2 = self._p()
        p2.seleccionar_espacio("recuentos")
        p2.set_recuento_ubicacion("ubi_cam")
        p2.set_recuento_producto("bp_leche")
        p2.set_recuento_lote("bl_leche")
        p2.set_recuento_cantidad("19")
        p2.anadir_linea_recuento()
        p2.previsualizar_recuento()
        p2.logout()
        self.assertEqual(
            len(getattr(get_container().app_data_store.get(), "recuentos", None) or []),
            n0,
        )


class TestRecuentosConfirmacion(_Harness):
    def test_14_diff_cero(self) -> None:
        p = self._prep_lineas("20")
        p.previsualizar_recuento()
        data = get_container().app_data_store.get()
        stock0 = float(next(l for l in data.lotes if l.id == "bl_leche").cantidad_restante)
        n_aj = len(data.ajustes)
        n_mov = len(data.movimientos)
        s = p.confirmar_recuento(fecha=date.today())
        self.assertTrue(s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        data2 = get_container().app_data_store.get()
        self.assertAlmostEqual(
            float(next(l for l in data2.lotes if l.id == "bl_leche").cantidad_restante),
            stock0,
        )
        self.assertEqual(len(data2.ajustes), n_aj)
        self.assertEqual(len(data2.movimientos), n_mov)
        conf = [r for r in data2.recuentos if r.estado == EstadoRecuento.CONFIRMADO]
        self.assertEqual(len(conf), 1)

    def test_15_sobrante(self) -> None:
        p = self._prep_lineas("22")
        p.previsualizar_recuento()
        data = get_container().app_data_store.get()
        stock0 = float(next(l for l in data.lotes if l.id == "bl_leche").cantidad_restante)
        s0 = saldo_en_ubicacion(data, "bl_leche", "ubi_cam")
        s = p.confirmar_recuento(fecha=date.today())
        self.assertTrue(s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        data2 = get_container().app_data_store.get()
        self.assertAlmostEqual(
            float(next(l for l in data2.lotes if l.id == "bl_leche").cantidad_restante),
            stock0 + 2,
        )
        self.assertAlmostEqual(saldo_en_ubicacion(data2, "bl_leche", "ubi_cam"), s0 + 2)
        tipos = [
            (m.tipo.value if hasattr(m.tipo, "value") else str(m.tipo))
            for m in data2.movimientos
            if (m.tipo.value if hasattr(m.tipo, "value") else str(m.tipo))
            == TipoMovimiento.AJUSTE_ENTRADA.value
        ]
        self.assertEqual(len(tipos), 1)
        aj = data2.ajustes[-1]
        motivo = aj.lineas[0].motivo
        motivo_v = motivo.value if hasattr(motivo, "value") else str(motivo)
        self.assertEqual(motivo_v, MotivoAjuste.RECONTEO_FISICO.value)

    def test_16_faltante(self) -> None:
        p = self._prep_lineas("17")
        p.previsualizar_recuento()
        data = get_container().app_data_store.get()
        stock0 = float(next(l for l in data.lotes if l.id == "bl_leche").cantidad_restante)
        s0 = saldo_en_ubicacion(data, "bl_leche", "ubi_cam")
        s = p.confirmar_recuento(fecha=date.today())
        self.assertTrue(s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        data2 = get_container().app_data_store.get()
        self.assertAlmostEqual(
            float(next(l for l in data2.lotes if l.id == "bl_leche").cantidad_restante),
            stock0 - 3,
        )
        self.assertAlmostEqual(saldo_en_ubicacion(data2, "bl_leche", "ubi_cam"), s0 - 3)
        salidas = [
            m
            for m in data2.movimientos
            if (m.tipo.value if hasattr(m.tipo, "value") else str(m.tipo))
            == TipoMovimiento.AJUSTE_SALIDA.value
        ]
        self.assertEqual(len(salidas), 1)

    def test_17_18_un_movimiento_por_diff_no_cero(self) -> None:
        # Cubierto en 15/16; diff cero ya en 14.
        self.test_15_sobrante()

    def test_19_20_21_motivo_stock_saldo(self) -> None:
        self.test_15_sobrante()


class TestRecuentosPreviewObsoleto(_Harness):
    def test_22_23_24_preview_obsoleto_segunda_confirmacion(self) -> None:
        p = self._prep_lineas("20")
        p.previsualizar_recuento()
        from app.core.services import traslado_service

        tr = traslado_service.confirmar_traslado(
            lote_id="bl_leche",
            ubicacion_origen_id="ubi_cam",
            ubicacion_destino_id="ubi_bar",
            cantidad=2.0,
            fecha=date.today(),
        )
        self.assertTrue(tr.ok, tr.mensaje)
        # Memory expected still 20; draft will freeze 18
        s = p.confirmar_recuento(fecha=date.today())
        self.assertFalse(s.feedback.ok)
        self.assertTrue(s.recuento_requiere_confirmacion_borrador)
        self.assertIsNotNone(s.recuento_pendiente_id)
        rid = s.recuento_pendiente_id
        data = get_container().app_data_store.get()
        ses = next(r for r in data.recuentos if r.id == rid)
        self.assertEqual(ses.estado, EstadoRecuento.BORRADOR)
        self.assertAlmostEqual(float(ses.lineas[0].cantidad_esperada), 18.0)
        n_aj = len(data.ajustes)
        # No auto-confirm: segunda confirmación explícita
        s2 = p.confirmar_recuento(fecha=date.today())
        self.assertTrue(s2.feedback.ok, s2.feedback.mensaje if s2.feedback else "")
        data2 = get_container().app_data_store.get()
        ses2 = next(r for r in data2.recuentos if r.id == rid)
        self.assertEqual(ses2.estado, EstadoRecuento.CONFIRMADO)
        self.assertGreater(len(data2.ajustes), n_aj)


class TestRecuentosErrores(_Harness):
    def test_25_fallo_crear_borrador_recuperable(self) -> None:
        p = self._prep_lineas("19")
        p.previsualizar_recuento()
        p._rc_ubicacion_id = "ubi_fantasma"  # noqa: SLF001
        s = p.confirmar_recuento(fecha=date.today())
        self.assertFalse(s.feedback.ok)
        self.assertIsNone(s.recuento_pendiente_id)
        self.assertIsNotNone(s.recuento_preview)
        # Corregir y reintentar
        p._rc_ubicacion_id = "ubi_cam"  # noqa: SLF001
        s2 = p.confirmar_recuento(fecha=date.today())
        self.assertTrue(s2.feedback.ok, s2.feedback.mensaje if s2.feedback else "")

    def test_26_27_28_fallo_confirmar_conserva_borrador_reintento(self) -> None:
        # Contada 18 + traslado 1 → esperado borrador 19 → Δ≠0 (la corrupción de lote se ejerce).
        p = self._prep_lineas("18")
        p.previsualizar_recuento()
        store = get_container().app_data_store
        from app.core.services import traslado_service

        tr = traslado_service.confirmar_traslado(
            lote_id="bl_leche",
            ubicacion_origen_id="ubi_cam",
            ubicacion_destino_id="ubi_bar",
            cantidad=1.0,
            fecha=date.today(),
        )
        self.assertTrue(tr.ok, tr.mensaje)
        s = p.confirmar_recuento(fecha=date.today())
        self.assertTrue(s.recuento_requiere_confirmacion_borrador)
        rid = s.recuento_pendiente_id
        self.assertIsNotNone(rid)
        stock0 = float(
            next(l for l in store.get().lotes if l.id == "bl_leche").cantidad_restante
        )
        n_aj = len(store.get().ajustes)
        n_mov = len(store.get().movimientos)
        with patch.object(
            recuento_service,
            "confirmar_recuento",
            return_value=recuento_service.ResultadoRecuento(False, "fallo confirm"),
        ):
            s2 = p.confirmar_borrador_pendiente()
        self.assertFalse(s2.feedback.ok)
        self.assertEqual(s2.recuento_pendiente_id, rid)
        data2 = store.get()
        self.assertEqual(
            next(r for r in data2.recuentos if r.id == rid).estado,
            EstadoRecuento.BORRADOR,
        )
        self.assertAlmostEqual(
            float(next(l for l in data2.lotes if l.id == "bl_leche").cantidad_restante),
            stock0,
        )
        self.assertEqual(len(data2.ajustes), n_aj)
        self.assertEqual(len(data2.movimientos), n_mov)
        # Rollback dominio (sin cambios parciales) sobre el mismo borrador
        data3 = store.get()
        ses = next(r for r in data3.recuentos if r.id == rid)
        self.assertNotAlmostEqual(float(ses.lineas[0].diferencia), 0.0)
        orig_lote = ses.lineas[0].lote_id
        ses.lineas[0].lote_id = "lot_fantasma"
        store.persist(data3)
        data3b = store.get()
        stock_b = float(
            next(l for l in data3b.lotes if l.id == "bl_leche").cantidad_restante
        )
        n_aj_b = len(data3b.ajustes)
        n_mov_b = len(data3b.movimientos)
        dom = recuento_service.confirmar_recuento(recuento_id=rid)
        self.assertFalse(dom.ok)
        data4 = store.get()
        self.assertEqual(
            next(r for r in data4.recuentos if r.id == rid).estado,
            EstadoRecuento.BORRADOR,
        )
        self.assertAlmostEqual(
            float(next(l for l in data4.lotes if l.id == "bl_leche").cantidad_restante),
            stock_b,
        )
        self.assertEqual(len(data4.ajustes), n_aj_b)
        self.assertEqual(len(data4.movimientos), n_mov_b)
        ses = next(r for r in data4.recuentos if r.id == rid)
        ses.lineas[0].lote_id = orig_lote
        store.persist(data4)
        s3 = p.confirmar_borrador_pendiente()
        self.assertTrue(s3.feedback.ok, s3.feedback.mensaje if s3.feedback else "")

    def test_29_descartar_borrador(self) -> None:
        p = self._prep_lineas("19")
        p.previsualizar_recuento()
        from app.core.services import traslado_service

        traslado_service.confirmar_traslado(
            lote_id="bl_leche",
            ubicacion_origen_id="ubi_cam",
            ubicacion_destino_id="ubi_bar",
            cantidad=1.0,
            fecha=date.today(),
        )
        s = p.confirmar_recuento(fecha=date.today())
        rid = s.recuento_pendiente_id
        self.assertIsNotNone(rid)
        s2 = p.descartar_borrador_pendiente()
        self.assertTrue(s2.feedback.ok, s2.feedback.mensaje if s2.feedback else "")
        self.assertIsNone(s2.recuento_pendiente_id)
        data = get_container().app_data_store.get()
        ses = next(r for r in data.recuentos if r.id == rid)
        self.assertEqual(ses.estado, EstadoRecuento.ANULADO)

    def test_30_fallo_descartar_conserva_estado(self) -> None:
        p = self._prep_lineas("19")
        p.previsualizar_recuento()
        from app.core.services import traslado_service

        traslado_service.confirmar_traslado(
            lote_id="bl_leche",
            ubicacion_origen_id="ubi_cam",
            ubicacion_destino_id="ubi_bar",
            cantidad=1.0,
            fecha=date.today(),
        )
        s = p.confirmar_recuento(fecha=date.today())
        rid = s.recuento_pendiente_id
        with patch.object(
            recuento_service,
            "anular_recuento",
            return_value=recuento_service.ResultadoRecuento(False, "fallo anular"),
        ):
            s2 = p.descartar_borrador_pendiente()
        self.assertFalse(s2.feedback.ok)
        self.assertEqual(s2.recuento_pendiente_id, rid)
        self.assertIn(rid, s2.recuento_aviso_borrador)


class TestRecuentosDobleEnvio(_Harness):
    def test_31_confirmando_bloquea(self) -> None:
        p = self._prep_lineas("19")
        p.previsualizar_recuento()
        p._confirmando = True  # noqa: SLF001
        s = p.confirmar_recuento(fecha=date.today())
        self.assertFalse(s.feedback.ok)
        self.assertEqual(s.feedback.codigo, "CONFIRMANDO")
        self.assertEqual(
            len(getattr(get_container().app_data_store.get(), "recuentos", None) or []),
            0,
        )

    def test_32_segundo_intento_tras_exito(self) -> None:
        p = self._prep_lineas("19")
        p.previsualizar_recuento()
        s1 = p.confirmar_recuento(fecha=date.today())
        self.assertTrue(s1.feedback.ok, s1.feedback.mensaje if s1.feedback else "")
        n = len(get_container().app_data_store.get().recuentos)
        s2 = p.confirmar_recuento(fecha=date.today())
        self.assertFalse(s2.feedback.ok)
        self.assertEqual(len(get_container().app_data_store.get().recuentos), n)


class TestRecuentosListados(_Harness):
    def test_33_34_35_pendientes_recientes_refresco(self) -> None:
        p = self._prep_lineas("18")
        p.previsualizar_recuento()
        # Crear borrador vía ruta stale sin confirmar
        from app.core.services import traslado_service

        traslado_service.confirmar_traslado(
            lote_id="bl_leche",
            ubicacion_origen_id="ubi_cam",
            ubicacion_destino_id="ubi_bar",
            cantidad=1.0,
            fecha=date.today(),
        )
        s = p.confirmar_recuento(fecha=date.today())
        self.assertTrue(s.recuentos_pendientes)
        rid = s.recuento_pendiente_id
        # Confirmar
        s2 = p.confirmar_recuento(fecha=date.today())
        self.assertTrue(s2.feedback.ok, s2.feedback.mensaje if s2.feedback else "")
        self.assertFalse(any(b.recuento_id == rid for b in s2.recuentos_pendientes))
        self.assertTrue(any(r.recuento_id == rid for r in s2.recuentos_recientes))
        # Stock space refreshes via same store
        s3 = p.seleccionar_espacio("stock")
        self.assertTrue(any(f.lote_id == "bl_leche" for f in s3.stock_filas))


class TestRecuentosRegresion(_Harness):
    def test_36_sin_regresion_ajustes_stock_traslados(self) -> None:
        self._seed()
        p = self._p()
        p.seleccionar_espacio("stock")
        self.assertIsNotNone(p.screen().stock_filas)
        p.seleccionar_espacio("traslados")
        p.set_traslado_producto("bp_leche")
        p.set_traslado_lote("bl_leche")
        p.set_traslado_origen("ubi_cam")
        p.set_traslado_destino("ubi_bar")
        p.set_traslado_cantidad("1")
        s = p.previsualizar_traslado()
        self.assertTrue(s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        p.seleccionar_espacio("ajustes")
        self.assertTrue(p.screen().lotes_ajuste)

    def test_37_entrypoint_y_launcher(self) -> None:
        from app.presentation.flet.main_inventario import build_app_handler
        from app.presentation.flet.main_launcher import build_app_handler as build_launcher

        self.assertTrue(callable(build_app_handler()))
        self.assertTrue(callable(build_launcher()))

    def test_38_permisos_terminal(self) -> None:
        p = self._p()
        self.assertEqual(p.screen().session.actor_id, "terminal_inventario")
        self.assertTrue(p.screen().session.authenticated)
        # Views no importan AppDataStore / JSON
        for path in (
            FLET_ROOT / "views" / "inventario_shell_view.py",
            FLET_ROOT / "app_shell_inventario.py",
        ):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn("app_data_store", node.module)
                    self.assertNotIn("recuento_service", node.module)
                    self.assertFalse(node.module.endswith(".json"))

    def test_abandonar_con_borrador_no_anula(self) -> None:
        p = self._prep_lineas("19")
        p.previsualizar_recuento()
        from app.core.services import traslado_service

        traslado_service.confirmar_traslado(
            lote_id="bl_leche",
            ubicacion_origen_id="ubi_cam",
            ubicacion_destino_id="ubi_bar",
            cantidad=1.0,
            fecha=date.today(),
        )
        s = p.confirmar_recuento(fecha=date.today())
        rid = s.recuento_pendiente_id
        s2 = p.seleccionar_espacio("stock")
        self.assertIn("pendiente", (s2.feedback.mensaje or "").lower())
        data = get_container().app_data_store.get()
        ses = next(r for r in data.recuentos if r.id == rid)
        self.assertEqual(ses.estado, EstadoRecuento.BORRADOR)
        p.seleccionar_espacio("recuentos")
        self.assertTrue(any(b.recuento_id == rid for b in p.screen().recuentos_pendientes))


if __name__ == "__main__":
    unittest.main()
