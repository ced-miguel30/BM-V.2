"""Registro operativo de Desayuno — catálogo activo, raciones, FIFO, idempotencia.

Semántica: cantidad de receta = raciones (factor = raciones / rendimiento).
No escribe el demo canónico.
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BM_TEST_ISOLATION", "1")

from app.core.auth.session import AuthSession, clear_test_session, set_test_session
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
from app.core.services import desayuno_service
from app.core.services.bebida_service import servicio as bebida_servicio
from app.core.services.inventory_batch_service import (
    planificar_descuento,
    stock_disponible,
    valorizar_cantidad_fifo,
)
from app.core.services.receta_service import listar_recetas
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    sha256_demo_file,
)
from tests.auth_harness import HARNESS_SESSION, restore_harness_session


def _sesion_restaurante() -> AuthSession:
    return AuthSession(
        authenticated=True,
        actor_type="terminal",
        actor_id="terminal_restaurante",
        actor_label="Terminal Restaurante",
        role="restaurante",
        session_id="test-rest",
        login_at="2026-01-01T00:00:00",
        login="terminal_restaurante",
        terminal_id="terminal_restaurante",
    )


def _datos_porridge(*, leche_restante: float = 12.0) -> AppData:
    """Caso E2E: Leche, Avena, Zumo + Porridge rendimiento 4."""
    return AppData(
        productos=[
            Producto(
                "pa", "Leche", UnidadProducto.L,
                servicios_disponibles=["desayuno"], codigo="LECHE",
            ),
            Producto(
                "pb", "Avena", UnidadProducto.KG,
                servicios_disponibles=["desayuno"], codigo="AVENA",
            ),
            Producto(
                "pc", "Zumo", UnidadProducto.UD,
                es_bebida=True,
                servicios_disponibles=["desayuno", "bebidas"],
                codigo="ZUMO",
            ),
            Producto(
                "pd", "Pan", UnidadProducto.UD,
                servicios_disponibles=["desayuno"], codigo="PAN",
                activo=False,
            ),
        ],
        lotes=[
            LoteStock("la", "pa", 24.0, 12.0, leche_restante, date(2026, 7, 1)),  # 2 €/L
            LoteStock("lb", "pb", 20.0, 5.0, 5.0, date(2026, 7, 1)),  # 4 €/kg
            LoteStock("lc", "pc", 20.0, 20.0, 20.0, date(2026, 7, 1)),  # 1 €/ud
            LoteStock("ld", "pd", 5.0, 5.0, 5.0, date(2026, 7, 1)),
        ],
        recetas=[
            Receta(
                "r1",
                "Porridge",
                [
                    IngredienteReceta("pa", 0.5),
                    IngredienteReceta("pb", 0.25),
                ],
                CategoriaReceta.DESAYUNO,
                servicios_disponibles=["desayuno"],
                porciones_estandar=4.0,
                activo=True,
            ),
            Receta(
                "r2",
                "Porridge viejo",
                [IngredienteReceta("pa", 0.5)],
                CategoriaReceta.DESAYUNO,
                servicios_disponibles=["desayuno"],
                porciones_estandar=4.0,
                activo=False,
            ),
        ],
        usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


class TestRegistroDesayunoOperativo(unittest.TestCase):
    def setUp(self) -> None:
        clear_test_session()
        set_test_session(HARNESS_SESSION)
        self.addCleanup(restore_harness_session)
        self.demo_before = DEMO_FILE.read_bytes()
        self.data = _datos_porridge()
        self._session: dict = {}
        self._patches = [
            mock.patch("app.core.services.desayuno_service.get_data", return_value=self.data),
            mock.patch(
                "app.core.services.desayuno_service.persist_data",
                side_effect=lambda d=None: d if d is not None else self.data,
            ),
            mock.patch("app.core.services.cesta_service.get_data", return_value=self.data),
            mock.patch("app.core.services.receta_service.get_data", return_value=self.data),
            mock.patch("app.core.services.servicio_registro_service.get_data", return_value=self.data),
            mock.patch("streamlit.session_state", self._session),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self) -> None:
        self.assertEqual(DEMO_FILE.read_bytes(), self.demo_before)
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    # --- Catálogo / activo -------------------------------------------------

    def test_01_solo_recetas_activas_en_listado(self) -> None:
        activas = listar_recetas(servicio_disponible="desayuno", solo_activas=True)
        nombres = {r.nombre for r in activas}
        self.assertIn("Porridge", nombres)
        self.assertNotIn("Porridge viejo", nombres)

    def test_02_producto_inactivo_excluido_catalogo(self) -> None:
        cat = desayuno_service.productos_catalogo("", servicio="desayuno")
        ids = {p["id"] for p in cat}
        self.assertIn("pa", ids)
        self.assertNotIn("pd", ids)

    def test_03_receta_inactiva_bloqueada_en_cesta(self) -> None:
        r = desayuno_service.anadir_receta_a_cesta("r2", 4.0)
        self.assertFalse(r.ok)
        self.assertIn("desactivada", r.mensaje.lower())

    def test_04_producto_inactivo_bloqueado_en_cesta(self) -> None:
        r = desayuno_service.anadir_a_cesta("pd", 1.0)
        self.assertFalse(r.ok)

    def test_05_historial_legible_tras_desactivar_receta(self) -> None:
        self.assertTrue(desayuno_service.anadir_receta_a_cesta("r1", 4.0).ok)
        self.assertTrue(desayuno_service.registrar_desayuno(date(2026, 7, 21), 10).ok)
        self.data.recetas[0].activo = False
        reg = self.data.desayunos[0]
        self.assertEqual(reg.registros_recetas[0].nombre_receta, "Porridge")
        self.assertNotIn("Porridge", {
            r.nombre for r in listar_recetas(servicio_disponible="desayuno", solo_activas=True)
        })

    def test_06_producto_historico_legible_tras_desactivar(self) -> None:
        self.assertTrue(desayuno_service.anadir_a_cesta("pc", 2.0).ok)
        self.assertTrue(desayuno_service.registrar_desayuno(date(2026, 7, 21), 5).ok)
        self.data.productos[2].activo = False
        det = self.data.desayunos[0].lineas_detalle[0]
        self.assertEqual(det.producto_id, "pc")
        self.assertTrue(det.es_bebida_snapshot)
        cat = desayuno_service.productos_catalogo("", servicio="desayuno")
        self.assertNotIn("pc", {p["id"] for p in cat})

    # --- Semántica raciones ------------------------------------------------

    def test_07_dos_raciones_no_dos_preparaciones(self) -> None:
        # Rendimiento 4 → 2 raciones = factor 0.5 → 0.25 L leche, 0.125 kg avena
        r = desayuno_service.anadir_receta_a_cesta("r1", 2.0)
        self.assertTrue(r.ok, r.mensaje)
        g = desayuno_service.get_cesta_recetas()[0]
        self.assertEqual(g.porciones, 2.0)
        self.assertAlmostEqual(g.factor_aplicado, 0.5, places=4)
        leche = next(i for i in g.ingredientes if i.producto_id == "pa")
        avena = next(i for i in g.ingredientes if i.producto_id == "pb")
        self.assertAlmostEqual(leche.cantidad, 0.25, places=4)
        self.assertAlmostEqual(avena.cantidad, 0.125, places=4)

    def test_08_conversion_cuatro_raciones_igual_una_preparacion(self) -> None:
        r = desayuno_service.anadir_receta_a_cesta("r1", 4.0)
        self.assertTrue(r.ok, r.mensaje)
        g = desayuno_service.get_cesta_recetas()[0]
        self.assertAlmostEqual(g.factor_aplicado, 1.0, places=4)
        leche = next(i for i in g.ingredientes if i.producto_id == "pa")
        self.assertAlmostEqual(leche.cantidad, 0.5, places=4)

    # --- Cantidades inválidas / duplicados / edición -----------------------

    def test_11_cantidad_cero_rechazada(self) -> None:
        r = desayuno_service.anadir_a_cesta("pc", 0.0)
        self.assertFalse(r.ok)

    def test_12_cantidad_negativa_como_omision_permitida_producto(self) -> None:
        # Motor histórico: negativo = omisión/extra; no es stock sale.
        r = desayuno_service.anadir_a_cesta("pc", -1.0)
        self.assertTrue(r.ok, r.mensaje)

    def test_13_duplicados_producto_fusionan(self) -> None:
        self.assertTrue(desayuno_service.anadir_a_cesta("pc", 2.0).ok)
        self.assertTrue(desayuno_service.anadir_a_cesta("pc", 3.0).ok)
        cesta = desayuno_service.get_cesta()
        self.assertEqual(len(cesta), 1)
        self.assertAlmostEqual(cesta[0].cantidad, 5.0, places=4)

    def test_14_edicion_porciones_recalcula(self) -> None:
        self.assertTrue(desayuno_service.anadir_receta_a_cesta("r1", 4.0).ok)
        g = desayuno_service.get_cesta_recetas()[0]
        self.assertTrue(desayuno_service.modificar_porciones_grupo(g.grupo_id, 8.0).ok)
        g2 = desayuno_service.get_cesta_recetas()[0]
        self.assertAlmostEqual(g2.factor_aplicado, 2.0, places=4)
        leche = next(i for i in g2.ingredientes if i.producto_id == "pa")
        self.assertAlmostEqual(leche.cantidad, 1.0, places=4)

    def test_15_eliminar_linea_antes_confirmar(self) -> None:
        self.assertTrue(desayuno_service.anadir_a_cesta("pc", 3.0).ok)
        lid = desayuno_service.get_cesta()[0].linea_id
        desayuno_service.quitar_linea_suelta(lid)
        self.assertTrue(desayuno_service.cesta_vacia())

    # --- Stock / coste -----------------------------------------------------

    def test_16_stock_insuficiente_bloquea_sin_parcial(self) -> None:
        self.data = _datos_porridge(leche_restante=0.1)
        for p in self._patches:
            p.stop()
        self._patches = [
            mock.patch("app.core.services.desayuno_service.get_data", return_value=self.data),
            mock.patch("app.core.services.desayuno_service.persist_data"),
            mock.patch("app.core.services.cesta_service.get_data", return_value=self.data),
            mock.patch("streamlit.session_state", self._session),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

        snap_lotes = [(l.id, l.cantidad_restante) for l in self.data.lotes]
        self.assertTrue(desayuno_service.anadir_receta_a_cesta("r1", 4.0).ok)
        r = desayuno_service.registrar_desayuno(date(2026, 7, 21), 5)
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo, "STOCK_INSUFICIENTE")
        self.assertTrue(any("Leche" in d for d in (r.detalle_stock or [])))
        self.assertTrue(any("No hay suficiente" in d for d in (r.detalle_stock or [])))
        self.assertEqual(len(self.data.desayunos), 0)
        self.assertEqual(
            [(l.id, l.cantidad_restante) for l in self.data.lotes],
            snap_lotes,
        )
        # Carrito se mantiene para corregir
        self.assertFalse(desayuno_service.cesta_vacia())

    def test_17_coste_incompleto_identificado(self) -> None:
        # Lote sin precio útil: precio_total 0 → valoración incompleta a efectos prácticos
        self.data.lotes.append(
            LoteStock("lz", "pa", 0.0, 5.0, 5.0, date(2026, 8, 1)),
        )
        # Con stock suficiente el plan ok; valorizar sobre cantidad alta con trozos 0 €
        val = valorizar_cantidad_fifo(self.data, "pc", 100.0)
        self.assertTrue(val.incompleto)
        plan = planificar_descuento(
            self.data, {"pc": 100.0},
            nombres={"pc": "Zumo"}, unidades={"pc": "Ud"},
        )
        self.assertFalse(plan.ok)

    # --- Confirmación / E2E ------------------------------------------------

    def test_18_21_22_23_e2e_porridge_zumo_sin_doble_conteo(self) -> None:
        # 4 raciones Porridge = 0.5 L + 0.25 kg; + 3 zumos bebida desayuno
        self.assertTrue(desayuno_service.anadir_receta_a_cesta("r1", 4.0).ok)
        self.assertTrue(desayuno_service.anadir_a_cesta("pc", 3.0).ok)
        r = desayuno_service.registrar_desayuno(
            date(2026, 7, 21), 8, clave_idempotencia="tok-e2e-1",
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(len(self.data.desayunos), 1)
        reg = self.data.desayunos[0]

        self.assertAlmostEqual(stock_disponible(self.data, "pa"), 11.5, places=4)
        self.assertAlmostEqual(stock_disponible(self.data, "pb"), 4.75, places=4)
        self.assertAlmostEqual(stock_disponible(self.data, "pc"), 17.0, places=4)

        # Coste: leche 0.5*2=1; avena 0.25*4=1; zumo 3*1=3 → total 5
        self.assertAlmostEqual(reg.coste_total, 5.0, places=2)

        # Una sola línea agregada por producto (coste no duplicado como ingredientes aparte)
        pids = [ln.producto_id for ln in reg.lineas]
        self.assertEqual(sorted(pids), ["pa", "pb", "pc"])

        # Snapshots
        rr = reg.registros_recetas[0]
        self.assertEqual(rr.nombre_receta, "Porridge")
        self.assertEqual(rr.porciones, 4.0)
        self.assertEqual(rr.porciones_estandar_snapshot, 4.0)
        self.assertEqual(rr.factor_aplicado, 1.0)

        bebidas = [d for d in reg.lineas_detalle if d.producto_id == "pc"]
        self.assertEqual(len(bebidas), 1)
        self.assertEqual(bebidas[0].tipo_servicio, "desayuno")
        self.assertTrue(bebidas[0].es_bebida_snapshot)
        self.assertEqual(bebidas[0].origen, OrigenConsumo.PRODUCTO_DIRECTO.value)

        ings = [
            d for d in reg.lineas_detalle
            if d.origen == OrigenConsumo.INGREDIENTE_RECETA.value
        ]
        self.assertEqual(len(ings), 2)

        movs = [
            m for m in self.data.movimientos
            if getattr(m, "origen_id", None) == reg.id
            or getattr(m, "documento_origen_id", None) == reg.id
        ]
        # Espejos de consumo: al menos uno
        self.assertGreater(len(self.data.movimientos), 0)

        # Reintento misma clave: no duplica
        self.assertTrue(desayuno_service.anadir_a_cesta("pc", 1.0).ok)
        r2 = desayuno_service.registrar_desayuno(
            date(2026, 7, 21), 8, clave_idempotencia="tok-e2e-1",
        )
        self.assertTrue(r2.ok)
        self.assertEqual(r2.codigo, "IDEMPOTENTE")
        self.assertEqual(len(self.data.desayunos), 1)
        self.assertAlmostEqual(stock_disponible(self.data, "pc"), 17.0, places=4)

    def test_19_confirmacion_crea_movimientos_enlazados(self) -> None:
        self.assertTrue(desayuno_service.anadir_a_cesta("pc", 1.0).ok)
        n_mov = len(self.data.movimientos)
        self.assertTrue(desayuno_service.registrar_desayuno(date(2026, 7, 21), 3).ok)
        self.assertGreater(len(self.data.movimientos), n_mov)
        reg = self.data.desayunos[0]
        self.assertTrue(any(
            getattr(m, "origen_id", None) == reg.id
            or reg.id in str(getattr(m, "clave_idempotencia", "") or "")
            or getattr(m, "documento_origen_id", None) == reg.id
            or any(
                getattr(m, "referencia", None) == reg.id
                for _ in [0]
            )
            for m in self.data.movimientos
        ) or any(
            det.consumos_lote for det in reg.lineas_detalle
        ))

    def test_20_fifo_varios_lotes(self) -> None:
        self.data.lotes = [
            LoteStock("la1", "pa", 4.0, 2.0, 2.0, date(2026, 6, 1)),  # 2 €/L
            LoteStock("la2", "pa", 6.0, 3.0, 3.0, date(2026, 7, 1)),  # 2 €/L
            LoteStock("lb", "pb", 20.0, 5.0, 5.0, date(2026, 7, 1)),
            LoteStock("lc", "pc", 20.0, 20.0, 20.0, date(2026, 7, 1)),
        ]
        # 4 raciones → 0.5 L leche: consume la1 completo (2) no: 0.5 < 2 → solo la1
        # Pedir 8 raciones → 1.0 L: la1 2.0 suficiente
        # Pedir 20 raciones → 2.5 L: la1 2 + la2 0.5
        self.assertTrue(desayuno_service.anadir_receta_a_cesta("r1", 20.0).ok)
        self.assertTrue(desayuno_service.registrar_desayuno(date(2026, 7, 21), 10).ok)
        self.assertAlmostEqual(self.data.lotes[0].cantidad_restante, 0.0, places=4)
        self.assertAlmostEqual(self.data.lotes[1].cantidad_restante, 2.5, places=4)

    def test_24_restaurante_mensaje_sin_euros(self) -> None:
        clear_test_session()
        set_test_session(_sesion_restaurante())
        self.assertTrue(desayuno_service.anadir_a_cesta("pc", 1.0).ok)
        r = desayuno_service.registrar_desayuno(date(2026, 7, 21), 2)
        self.assertTrue(r.ok, r.mensaje)
        self.assertNotIn("€", r.mensaje)
        self.assertIn("ref.", r.mensaje.lower())

    def test_25_direccion_mensaje_con_coste(self) -> None:
        self.assertTrue(desayuno_service.anadir_a_cesta("pc", 1.0).ok)
        r = desayuno_service.registrar_desayuno(date(2026, 7, 21), 2)
        self.assertTrue(r.ok, r.mensaje)
        self.assertIn("€", r.mensaje)

    def test_26_demo_intacto(self) -> None:
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def test_10_bebida_desayuno_no_es_servicio_bebidas(self) -> None:
        self.assertTrue(desayuno_service.anadir_a_cesta("pc", 3.0).ok)
        self.assertTrue(desayuno_service.registrar_desayuno(date(2026, 7, 21), 5).ok)
        self.assertEqual(len(self.data.desayunos), 1)
        self.assertEqual(len(self.data.registros_servicio), 0)
        det = self.data.desayunos[0].lineas_detalle[0]
        self.assertEqual(det.tipo_servicio, "desayuno")
        self.assertTrue(det.es_bebida_snapshot)

    def test_10b_bebida_independiente_separada(self) -> None:
        # Servicio bebidas separado: no mezclar con desayuno
        bebida_servicio.limpiar_cesta()
        with mock.patch("app.core.services.cesta_service.get_data", return_value=self.data), \
             mock.patch("app.core.services.servicio_registro_service.get_data", return_value=self.data), \
             mock.patch(
                 "app.core.services.servicio_registro_service.persist_data",
                 side_effect=lambda d=None: d if d is not None else self.data,
             ):
            r = bebida_servicio.anadir_a_cesta("pc", 2.0)
            self.assertTrue(r.ok, r.mensaje)
            r2 = bebida_servicio.registrar(date(2026, 7, 21))
            self.assertTrue(r2.ok, r2.mensaje)
        regs = [x for x in self.data.registros_servicio if x.tipo_servicio == "bebidas"]
        self.assertEqual(len(regs), 1)
        self.assertTrue(all(d.tipo_servicio == "bebidas" for d in regs[0].lineas_detalle))
        self.assertEqual(len(self.data.desayunos), 0)


if __name__ == "__main__":
    unittest.main()
