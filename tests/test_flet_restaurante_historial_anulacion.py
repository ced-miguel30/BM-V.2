"""Tests Flet — Historial + anulación Terminal Restaurante.

Cubre presentación, sanitización económica e integración con binds productivos.
No sustituye las suites productivas de anulación/RBAC.

Ejecutar:

    py -m unittest tests.test_flet_restaurante_historial_anulacion -v
"""

from __future__ import annotations

import ast
import os
import tempfile
import unittest
from dataclasses import asdict, fields
from datetime import date, time
from pathlib import Path
from unittest import mock

os.environ["BM_TEST_ISOLATION"] = "1"

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.session import (
    clear_test_session,
    get_auth_session,
    iniciar_terminal_inventario,
    set_test_session,
)
from app.core.models import (
    LineaDetalleOrigen,
    RegistroDesayuno,
)
from app.core.models.enums import OrigenConsumo, TipoMovimiento
from app.core.services import anulacion_registro_service as anul
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    set_demo_file_override,
    sha256_demo_file,
)
from app.presentation.flet.presenters.terminal_restaurante_presenter import (
    TerminalRestaurantePresenter,
    _HISTORIAL_LIMITE,
)
from app.presentation.flet.viewmodels import (
    CAMPOS_ECONOMICOS_PROHIBIDOS,
    AnulacionPendienteVM,
    HistorialRegistroVM,
    TerminalScreenVM,
)
from app.presentation.flet.views import registro_servicio_view
from tests.auth_harness import restore_harness_session
from tests.browser.fixtures_minimos import write_browser_fixture

ROOT = Path(__file__).resolve().parent.parent
FLET_ROOT = ROOT / "app" / "presentation" / "flet"
VIEW_PATH = FLET_ROOT / "views" / "registro_servicio_view.py"


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

    def _presenter(self) -> TerminalRestaurantePresenter:
        p = TerminalRestaurantePresenter()
        p.entrar()
        return p

    def _registrar(
        self,
        p: TerminalRestaurantePresenter,
        servicio: str,
        producto_id: str,
        qty: float = 1.0,
        *,
        huespedes: int | None = None,
    ) -> TerminalScreenVM:
        p.seleccionar_servicio(servicio)
        if huespedes is not None:
            p.set_num_huespedes(huespedes)
        elif servicio == "desayuno":
            p.set_num_huespedes(8)
        p.anadir_producto_directo(producto_id, qty)
        screen = p.confirmar(fecha=date.today())
        self.assertTrue(
            screen.feedback and screen.feedback.ok,
            screen.feedback.mensaje if screen.feedback else "sin feedback",
        )
        return screen


class TestHistorialBasico(_Harness):
    def test_01_historial_vacio(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        self.assertEqual(p.screen().historial, ())

    def test_02_historial_desayuno(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        hist = p.seleccionar_servicio("desayuno").historial
        self.assertGreaterEqual(len(hist), 1)
        self.assertEqual(hist[0].tipo_registro, anul.TIPO_DESAYUNO)
        self.assertIn("Desayuno", hist[0].etiqueta_corta)

    def test_03_historial_comida(self) -> None:
        p = self._presenter()
        self._registrar(p, "comida", "bp_pan")
        hist = p.seleccionar_servicio("comida").historial
        self.assertGreaterEqual(len(hist), 1)
        self.assertEqual(hist[0].tipo_registro, anul.TIPO_SERVICIO)
        self.assertIn("Comida", hist[0].etiqueta_corta)

    def test_04_historial_cena(self) -> None:
        p = self._presenter()
        self._registrar(p, "cena", "bp_pan")
        hist = p.seleccionar_servicio("cena").historial
        self.assertGreaterEqual(len(hist), 1)
        self.assertIn("Cena", hist[0].etiqueta_corta)

    def test_05_historial_bebidas(self) -> None:
        p = self._presenter()
        self._registrar(p, "bebidas", "bp_zumo")
        hist = p.seleccionar_servicio("bebidas").historial
        self.assertGreaterEqual(len(hist), 1)
        self.assertIn("Bebidas", hist[0].etiqueta_corta)

    def test_06_separacion_cuatro_servicios(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        self._registrar(p, "comida", "bp_pan")
        self._registrar(p, "cena", "bp_pan")
        self._registrar(p, "bebidas", "bp_zumo")
        d = {h.registro_id for h in p.seleccionar_servicio("desayuno").historial}
        c = {h.registro_id for h in p.seleccionar_servicio("comida").historial}
        n = {h.registro_id for h in p.seleccionar_servicio("cena").historial}
        b = {h.registro_id for h in p.seleccionar_servicio("bebidas").historial}
        self.assertTrue(d.isdisjoint(c | n | b))
        self.assertTrue(c.isdisjoint(n | b))
        self.assertTrue(n.isdisjoint(b))

    def test_07_orden_descendente(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo", 1.0)
        self._registrar(p, "desayuno", "bp_zumo", 1.0)
        hist = p.seleccionar_servicio("desayuno").historial
        self.assertGreaterEqual(len(hist), 2)
        keys = [(h.fecha, h.hora) for h in hist]
        self.assertEqual(keys, sorted(keys, reverse=True))

    def test_08_limite_recientes(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        data = get_container().app_data_store.get()
        for i in range(_HISTORIAL_LIMITE + 5):
            data.desayunos.append(
                RegistroDesayuno(
                    id=f"lim_{i}",
                    fecha=date(2026, 1, 1 + (i % 28)),
                    coste_total=1.0,
                    registrado_por="t",
                    lineas_detalle=[
                        LineaDetalleOrigen(
                            origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                            producto_id="bp_zumo",
                            cantidad=1.0,
                            coste=1.0,
                            tipo_servicio="desayuno",
                            consumos_lote=[],
                        )
                    ],
                )
            )
        get_container().app_data_store.persist(data)
        hist = p.screen().historial
        self.assertEqual(len(hist), _HISTORIAL_LIMITE)

    def test_09_registro_activo(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        item = p.screen().historial[0]
        self.assertEqual(item.estado, "activo")
        self.assertTrue(item.puede_anular)

    def test_10_registro_anulado(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        rid = p.screen().historial[0].registro_id
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("error de carga")
        screen = p.confirmar_anulacion()
        self.assertTrue(screen.feedback and screen.feedback.ok)
        item = next(h for h in screen.historial if h.registro_id == rid)
        self.assertEqual(item.estado, "anulado")
        self.assertFalse(item.puede_anular)

    def test_11_historico_no_anulable(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        data = get_container().app_data_store.get()
        data.desayunos.append(
            RegistroDesayuno(
                id="d_hist_inseguro",
                fecha=date(2026, 1, 1),
                coste_total=5.0,
                registrado_por="legado",
                lineas_detalle=[],
            )
        )
        get_container().app_data_store.persist(data)
        item = next(h for h in p.screen().historial if h.registro_id == "d_hist_inseguro")
        self.assertEqual(item.estado, "no_anulable")
        self.assertFalse(item.puede_anular)
        self.assertTrue(item.motivo_bloqueo)

    def test_12_anulados_permanecen_visibles(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        rid = p.screen().historial[0].registro_id
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("duplicado")
        p.confirmar_anulacion()
        ids = {h.registro_id for h in p.screen().historial}
        self.assertIn(rid, ids)

    def test_13_refresco_despues_registrar(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("comida")
        before = len(p.screen().historial)
        self._registrar(p, "comida", "bp_pan")
        self.assertEqual(len(p.screen().historial), before + 1)

    def test_14_conserva_recien_confirmado(self) -> None:
        p = self._presenter()
        screen = self._registrar(p, "desayuno", "bp_zumo")
        # Tras confirmar, historial del servicio activo incluye el nuevo
        self.assertTrue(screen.historial)
        self.assertEqual(screen.historial[0].estado, "activo")


class TestSanitizacion(_Harness):
    def test_15_vm_sin_coste_total(self) -> None:
        names = {f.name for f in fields(HistorialRegistroVM)}
        self.assertNotIn("coste_total", names)

    def test_16_vm_sin_campos_economicos(self) -> None:
        for cls in (HistorialRegistroVM, AnulacionPendienteVM, TerminalScreenVM):
            names = {f.name.lower() for f in fields(cls)}
            for bad in CAMPOS_ECONOMICOS_PROHIBIDOS:
                self.assertNotIn(bad.lower(), names)

    def test_17_sin_coste_consumos_lote_en_vm(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        item = p.screen().historial[0]
        blob = str(asdict(item)).lower()
        self.assertNotIn("consumos_lote", blob)
        self.assertNotIn("coste", blob)
        self.assertNotIn("precio", blob)

    def test_18_vista_sin_simbolos_monetarios(self) -> None:
        src = VIEW_PATH.read_text(encoding="utf-8")
        for token in ("€", "EUR", "coste_total", "precio", "importe", "margen"):
            haystack = src if token == "€" else src.lower()
            needle = token if token == "€" else token.lower()
            self.assertNotIn(needle, haystack)
        # "coste" suelto tampoco como campo/variable
        self.assertNotRegex(src, r"\bcoste\b", msg="vista no debe mencionar 'coste'")
        self.assertNotRegex(src.lower(), r"\bcoste\b")

    def test_19_vista_sin_objetos_productivos(self) -> None:
        src = VIEW_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = (
                    node.module
                    if isinstance(node, ast.ImportFrom)
                    else ".".join(a.name for a in node.names)
                ) or ""
                self.assertFalse(
                    mod.startswith("app.core.services")
                    or mod.startswith("app.core.storage")
                    or "AppData" in mod
                    or mod.endswith("json")
                )

    def test_20_vista_sin_imports_peligrosos(self) -> None:
        src = registro_servicio_view.__file__
        text = Path(src).read_text(encoding="utf-8")
        self.assertNotIn("AppData", text)
        self.assertNotIn("app_data_store", text)
        self.assertNotIn("anulacion_registro", text)
        self.assertNotIn("json.load", text)


class TestAnulacionFlujo(_Harness):
    def test_21_puede_anular_habilita(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        rid = p.screen().historial[0].registro_id
        screen = p.iniciar_anulacion(rid)
        self.assertIsNotNone(screen.anulacion_pendiente)
        self.assertEqual(screen.anulacion_pendiente.registro_id, rid)

    def test_22_no_anulable_no_abre_confirmacion(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        data = get_container().app_data_store.get()
        data.desayunos.append(
            RegistroDesayuno(
                id="d_block",
                fecha=date(2026, 2, 1),
                coste_total=1.0,
                registrado_por="x",
                lineas_detalle=[],
            )
        )
        get_container().app_data_store.persist(data)
        screen = p.iniciar_anulacion("d_block")
        self.assertIsNone(screen.anulacion_pendiente)
        self.assertFalse(screen.feedback.ok)
        self.assertEqual(screen.feedback.codigo, "NO_ANULABLE")

    def test_23_confirmacion_explicita_requerida(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        # Sin iniciar_anulacion, confirmar no muta
        before = len(
            [d for d in get_container().app_data_store.get().desayunos if not d.anulado]
        )
        screen = p.confirmar_anulacion()
        self.assertFalse(screen.feedback.ok)
        after = len(
            [d for d in get_container().app_data_store.get().desayunos if not d.anulado]
        )
        self.assertEqual(before, after)

    def test_24_cancelar_no_muta(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        rid = p.screen().historial[0].registro_id
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("voy a cancelar")
        p.cancelar_anulacion()
        data = get_container().app_data_store.get()
        reg = next(d for d in data.desayunos if d.id == rid)
        self.assertFalse(getattr(reg, "anulado", False))
        self.assertIsNone(p.screen().anulacion_pendiente)

    def test_25_motivo_vacio_rechazado(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        rid = p.screen().historial[0].registro_id
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("   ")
        screen = p.confirmar_anulacion()
        self.assertFalse(screen.feedback.ok)
        self.assertEqual(screen.feedback.codigo, "VALIDACION")
        reg = next(d for d in get_container().app_data_store.get().desayunos if d.id == rid)
        self.assertFalse(getattr(reg, "anulado", False))

    def test_26_anulacion_exitosa(self) -> None:
        p = self._presenter()
        self._registrar(p, "comida", "bp_pan")
        rid = p.screen().historial[0].registro_id
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("pedido equivocado")
        screen = p.confirmar_anulacion()
        self.assertTrue(screen.feedback.ok)
        self.assertIsNone(screen.anulacion_pendiente)

    def test_27_pasa_a_anulado(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        rid = p.screen().historial[0].registro_id
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("error")
        p.confirmar_anulacion()
        item = next(h for h in p.screen().historial if h.registro_id == rid)
        self.assertEqual(item.estado, "anulado")

    def test_28_stock_restaurado(self) -> None:
        p = self._presenter()
        data0 = get_container().app_data_store.get()
        stock0 = next(l for l in data0.lotes if l.id == "bl_zumo").cantidad_restante
        self._registrar(p, "desayuno", "bp_zumo", 2.0)
        data1 = get_container().app_data_store.get()
        stock1 = next(l for l in data1.lotes if l.id == "bl_zumo").cantidad_restante
        self.assertAlmostEqual(stock0 - stock1, 2.0, places=4)
        rid = p.screen().historial[0].registro_id
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("devolver stock")
        p.confirmar_anulacion()
        data2 = get_container().app_data_store.get()
        stock2 = next(l for l in data2.lotes if l.id == "bl_zumo").cantidad_restante
        self.assertAlmostEqual(stock2, stock0, places=4)

    def test_29_lotes_originales(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo", 1.0)
        rid = p.screen().historial[0].registro_id
        data = get_container().app_data_store.get()
        reg = next(d for d in data.desayunos if d.id == rid)
        consumos = []
        for ln in reg.lineas_detalle or []:
            consumos.extend(ln.consumos_lote or [])
        self.assertTrue(consumos)
        lote_ids = {c.lote_id for c in consumos}
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("fifo exacto")
        p.confirmar_anulacion()
        data2 = get_container().app_data_store.get()
        for lid in lote_ids:
            self.assertTrue(any(l.id == lid for l in data2.lotes))

    def test_30_movimiento_espejo(self) -> None:
        p = self._presenter()
        n0 = len(get_container().app_data_store.get().movimientos)
        self._registrar(p, "desayuno", "bp_zumo", 1.0)
        rid = p.screen().historial[0].registro_id
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("espejo")
        p.confirmar_anulacion()
        movs = get_container().app_data_store.get().movimientos[n0:]
        tipos = {getattr(m.tipo, "value", str(m.tipo)) for m in movs}
        self.assertGreaterEqual(len(movs), 2)
        self.assertIn(TipoMovimiento.REVERSION_CONSUMO.value, tipos)

    def test_31_actividad_auditoria(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        rid = p.screen().historial[0].registro_id
        n0 = len(get_container().app_data_store.get().actividades)
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("auditoría")
        p.confirmar_anulacion()
        data = get_container().app_data_store.get()
        self.assertGreater(len(data.actividades), n0)
        reg = next(d for d in data.desayunos if d.id == rid)
        self.assertTrue(reg.anulado)

    def test_32_segunda_anulacion_rechazada(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        rid = p.screen().historial[0].registro_id
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("uno")
        self.assertTrue(p.confirmar_anulacion().feedback.ok)
        screen = p.iniciar_anulacion(rid)
        self.assertIsNone(screen.anulacion_pendiente)
        self.assertFalse(screen.feedback.ok)

    def test_33_historico_inseguro_bloqueado(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        data = get_container().app_data_store.get()
        data.desayunos.append(
            RegistroDesayuno(
                id="d_inseguro2",
                fecha=date(2025, 12, 1),
                coste_total=9.0,
                registrado_por="legado",
            )
        )
        get_container().app_data_store.persist(data)
        screen = p.iniciar_anulacion("d_inseguro2")
        self.assertIsNone(screen.anulacion_pendiente)

    def test_34_fallo_productivo_sin_falso_exito(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        rid = p.screen().historial[0].registro_id
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("fallará")
        with mock.patch(
            "app.presentation.flet.presenters.terminal_restaurante_presenter.anul.anular_desayuno",
            return_value=anul.ResultadoAnulacion(False, "fallo simulado"),
        ):
            screen = p.confirmar_anulacion()
        self.assertFalse(screen.feedback.ok)
        self.assertIn("fallo", screen.feedback.mensaje.lower())
        reg = next(d for d in get_container().app_data_store.get().desayunos if d.id == rid)
        self.assertFalse(getattr(reg, "anulado", False))

    def test_35_fallo_persistencia_sin_parcial(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        rid = p.screen().historial[0].registro_id
        stock0 = next(
            l for l in get_container().app_data_store.get().lotes if l.id == "bl_zumo"
        ).cantidad_restante
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("persist fail")
        with mock.patch(
            "app.presentation.flet.presenters.terminal_restaurante_presenter.anul.anular_desayuno",
            side_effect=RuntimeError("persistencia rota"),
        ):
            screen = p.confirmar_anulacion()
        self.assertFalse(screen.feedback.ok)
        self.assertIn("persistencia", screen.feedback.mensaje.lower())
        data = get_container().app_data_store.get()
        reg = next(d for d in data.desayunos if d.id == rid)
        self.assertFalse(getattr(reg, "anulado", False))
        stock1 = next(l for l in data.lotes if l.id == "bl_zumo").cantidad_restante
        self.assertAlmostEqual(stock1, stock0, places=4)

    def test_36_doble_clic_una_sola_llamada(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        rid = p.screen().historial[0].registro_id
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("doble")
        calls: list[int] = []
        real = anul.anular_desayuno

        def _wrapped(*a, **k):
            calls.append(1)
            # Reentrada local mientras _anulando
            nested = p.confirmar_anulacion()
            self.assertFalse(nested.feedback.ok)
            self.assertEqual(nested.feedback.codigo, "ANULANDO")
            return real(*a, **k)

        with mock.patch(
            "app.presentation.flet.presenters.terminal_restaurante_presenter.anul.anular_desayuno",
            side_effect=_wrapped,
        ):
            screen = p.confirmar_anulacion()
        self.assertEqual(len(calls), 1)
        self.assertTrue(screen.feedback.ok)

    def test_37_refresco_tras_exito(self) -> None:
        p = self._presenter()
        self._registrar(p, "bebidas", "bp_zumo")
        rid = p.screen().historial[0].registro_id
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("ok")
        screen = p.confirmar_anulacion()
        self.assertTrue(any(h.registro_id == rid and h.estado == "anulado" for h in screen.historial))

    def test_38_volver_menu_no_anula(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        rid = p.screen().historial[0].registro_id
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("no aplicar")
        p.preparar_salida()
        reg = next(d for d in get_container().app_data_store.get().desayunos if d.id == rid)
        self.assertFalse(getattr(reg, "anulado", False))
        self.assertIsNone(p.screen().anulacion_pendiente)

    def test_39_logout_no_anula(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        rid = p.screen().historial[0].registro_id
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("no aplicar")
        p.logout()
        reg = next(d for d in get_container().app_data_store.get().desayunos if d.id == rid)
        self.assertFalse(getattr(reg, "anulado", False))

    def test_40_sesion_ausente_bloqueada(self) -> None:
        p = TerminalRestaurantePresenter()
        # sin entrar
        screen = p.confirmar_anulacion()
        self.assertFalse(screen.feedback.ok)
        self.assertFalse(screen.session.authenticated)

    def test_41_terminal_incorrecto_bloqueado(self) -> None:
        p = self._presenter()
        self._registrar(p, "desayuno", "bp_zumo")
        rid = p.screen().historial[0].registro_id
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("mal terminal")
        # Terminal inventario: fuera de allowlist de anulación / no es Restaurante
        set_test_session(iniciar_terminal_inventario())
        screen = p.confirmar_anulacion()
        self.assertFalse(screen.feedback.ok)
        reg = next(d for d in get_container().app_data_store.get().desayunos if d.id == rid)
        self.assertFalse(getattr(reg, "anulado", False))

    def test_42_terminal_restaurante_autorizado(self) -> None:
        p = self._presenter()
        sess = get_auth_session()
        self.assertEqual(sess.terminal_id, "terminal_restaurante")
        self._registrar(p, "desayuno", "bp_zumo")
        rid = p.screen().historial[0].registro_id
        p.iniciar_anulacion(rid)
        p.set_motivo_anulacion("autorizado")
        self.assertTrue(p.confirmar_anulacion().feedback.ok)


class TestRegresion(_Harness):
    def test_43_cesta_funciona(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        p.anadir_producto_directo("bp_zumo", 1.0)
        self.assertFalse(p.screen().cesta.vacia)

    def test_44_confirmacion_registro(self) -> None:
        p = self._presenter()
        self._registrar(p, "cena", "bp_pan")
        self.assertTrue(p.screen().cesta.vacia)

    def test_45_anti_doble_clic_registro(self) -> None:
        p = self._presenter()
        p.seleccionar_servicio("desayuno")
        p.set_num_huespedes(5)
        p.anadir_producto_directo("bp_zumo", 1.0)
        calls: list[int] = []
        bind = p._require_bind()
        real = bind.api.registrar

        def _wrap(*a, **k):
            calls.append(1)
            nested = p.confirmar(fecha=date.today())
            self.assertFalse(nested.feedback.ok)
            self.assertEqual(nested.feedback.codigo, "CONFIRMANDO")
            return real(*a, **k)

        with mock.patch.object(bind.api, "registrar", side_effect=_wrap):
            screen = p.confirmar(fecha=date.today())
        self.assertEqual(len(calls), 1)
        self.assertTrue(screen.feedback.ok)

    def test_46_shell_navegacion_intacta(self) -> None:
        src = (FLET_ROOT / "app_shell.py").read_text(encoding="utf-8")
        self.assertIn("preparar_salida", src)
        self.assertIn("on_iniciar_anulacion", src)
        self.assertIn("seleccionar_servicio", src)

    def test_47_entrypoint_launcher_intactos(self) -> None:
        for name in ("main.py", "main_launcher.py"):
            path = FLET_ROOT / name
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("anular_registro", text)

    def test_48_inventario_sin_regresion_imports(self) -> None:
        inv = FLET_ROOT / "presenters" / "terminal_inventario_presenter.py"
        self.assertTrue(inv.is_file())
        # Este módulo no debe importar historial restaurante
        text = inv.read_text(encoding="utf-8")
        self.assertNotIn("terminal_restaurante_presenter", text)

    def test_49_rbac_acotado_sin_cambio_dominio(self) -> None:
        # Solo comprueba que el contrato Flet sigue usando wrappers productivos
        src = (
            FLET_ROOT / "presenters" / "terminal_restaurante_presenter.py"
        ).read_text(encoding="utf-8")
        self.assertIn("anular_desayuno", src)
        self.assertIn("anular_servicio", src)
        self.assertIn("puede_anular_registro", src)
        self.assertIn("_HISTORIAL_LIMITE", src)


if __name__ == "__main__":
    unittest.main()
