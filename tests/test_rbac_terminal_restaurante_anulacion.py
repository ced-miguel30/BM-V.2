"""RBAC — anulación de registros desde Terminal Restaurante (excepción acotada).

Contrato:
- deny_terminal=True se conserva en anular_registro.
- Solo se admite terminal_id == TERMINAL_ID_DEFAULT vía allowed_terminals.
- ACCEDER_REGISTRO sigue siendo obligatorio.
- Otros casos deny_terminal=True no se ven afectados.

Ejecutar:

    py -m unittest tests.test_rbac_terminal_restaurante_anulacion -v
"""

from __future__ import annotations

import os
import unittest
from datetime import date
from unittest import mock

os.environ["BM_TEST_ISOLATION"] = "1"

from app.core.auth.permissions import AuthorizationError, Permiso
from app.core.auth.roles import ROL_ADMINISTRACION, ROL_RECEPCION, ROL_RESTAURANTE
from app.core.auth.session import (
    TERMINAL_ID_DEFAULT,
    AuthSession,
    clear_test_session,
    iniciar_terminal_inventario,
    iniciar_terminal_restaurante,
    set_test_session,
)
from app.core.auth.usecase_guard import (
    UseCaseDenied,
    require_usecase,
    usecase_deny_message,
)
from app.core.models import (
    AppData,
    LineaDetalleOrigen,
    LoteStock,
    Producto,
    RegistroDesayuno,
    RegistroServicio,
    RolUsuario,
    UnidadProducto,
    Usuario,
)
from app.core.models.enums import OrigenConsumo, TipoMovimiento
from app.core.models.registro_servicio import ConsumoLoteDetalle
from app.core.services import anulacion_registro_service as anul
from tests.auth_harness import HARNESS_SESSION, restore_harness_session


def _data() -> AppData:
    return AppData(
        productos=[Producto("p1", "Harina", UnidadProducto.KG)],
        lotes=[
            LoteStock(
                "l1",
                "p1",
                precio_total=20.0,
                cantidad=10.0,
                cantidad_restante=7.0,
                fecha_compra=date(2026, 7, 1),
            ),
        ],
        usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


def _desayuno(reg_id: str = "d01", qty: float = 3.0) -> RegistroDesayuno:
    return RegistroDesayuno(
        id=reg_id,
        fecha=date(2026, 7, 20),
        coste_total=qty * 2.0,
        registrado_por="Ana",
        lineas_detalle=[
            LineaDetalleOrigen(
                origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                producto_id="p1",
                cantidad=qty,
                coste=qty * 2.0,
                tipo_servicio="desayuno",
                consumos_lote=[ConsumoLoteDetalle("l1", "p1", qty, qty * 2.0)],
            ),
        ],
    )


def _servicio(tipo: str, reg_id: str, qty: float = 2.0) -> RegistroServicio:
    return RegistroServicio(
        id=reg_id,
        tipo_servicio=tipo,
        fecha=date(2026, 7, 21),
        coste_total=qty * 2.0,
        registrado_por="Ana",
        lineas_detalle=[
            LineaDetalleOrigen(
                origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                producto_id="p1",
                cantidad=qty,
                coste=qty * 2.0,
                tipo_servicio=tipo,
                consumos_lote=[ConsumoLoteDetalle("l1", "p1", qty, qty * 2.0)],
            ),
        ],
    )


def _sess_restaurante_sin_permiso() -> AuthSession:
    return AuthSession(
        authenticated=True,
        actor_type="terminal",
        actor_id="terminal_restaurante",
        actor_label="Restaurante",
        role=ROL_RECEPCION,  # sin ACCEDER_REGISTRO
        session_id="t-rest-noperm",
        login_at="2026-01-01T00:00:00",
        terminal_id=TERMINAL_ID_DEFAULT,
        login=None,
    )


def _sess_otro_terminal_con_registro() -> AuthSession:
    return AuthSession(
        authenticated=True,
        actor_type="terminal",
        actor_id="terminal_otro",
        actor_label="Otro",
        role=ROL_RESTAURANTE,  # tiene ACCEDER_REGISTRO
        session_id="t-otro",
        login_at="2026-01-01T00:00:00",
        terminal_id="terminal_desconocido",
        login=None,
    )


class _AnulacionHarness(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _data()
        self._patches = [
            mock.patch(
                "app.core.services.anulacion_registro_service.get_data",
                return_value=self.data,
            ),
            mock.patch("app.core.services.anulacion_registro_service.persist_data"),
            mock.patch("app.core.services.alert_service.sincronizar_alertas"),
        ]
        for p in self._patches:
            p.start()
        clear_test_session()
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        for p in reversed(self._patches):
            p.stop()
        restore_harness_session()


class TestUsuarioSiguePuediendo(_AnulacionHarness):
    def test_01_usuario_anula_desayuno(self) -> None:
        set_test_session(HARNESS_SESSION)
        self.data.desayunos.append(_desayuno())
        r = anul.anular_desayuno("d01", "error carga")
        self.assertTrue(r.ok, r.mensaje)
        self.assertTrue(self.data.desayunos[0].anulado)
        self.assertAlmostEqual(self.data.lotes[0].cantidad_restante, 10.0)

    def test_02_usuario_anula_servicio(self) -> None:
        set_test_session(HARNESS_SESSION)
        self.data.registros_servicio.append(_servicio("comida", "co01"))
        self.data.lotes[0].cantidad_restante = 5.0
        r = anul.anular_servicio("co01", "equivocación")
        self.assertTrue(r.ok, r.mensaje)
        self.assertTrue(self.data.registros_servicio[0].anulado)
        self.assertAlmostEqual(self.data.lotes[0].cantidad_restante, 7.0)

    def test_03_usuario_sin_acceder_registro_bloqueado(self) -> None:
        set_test_session(
            AuthSession(
                authenticated=True,
                actor_type="usuario",
                actor_id="rec1",
                actor_label="Recepción",
                role=ROL_RECEPCION,
                session_id="rec",
                login_at="2026-01-01T00:00:00",
                login="rec",
            )
        )
        self.data.desayunos.append(_desayuno())
        r = anul.anular_desayuno("d01", "motivo")
        self.assertFalse(r.ok)
        self.assertFalse(self.data.desayunos[0].anulado)
        self.assertAlmostEqual(self.data.lotes[0].cantidad_restante, 7.0)


class TestTerminalRestauranteAnulacion(_AnulacionHarness):
    def test_04_restaurante_anula_desayuno(self) -> None:
        set_test_session(iniciar_terminal_restaurante())
        self.data.desayunos.append(_desayuno())
        r = anul.anular_desayuno("d01", "carga duplicada")
        self.assertTrue(r.ok, r.mensaje)
        self.assertTrue(self.data.desayunos[0].anulado)

    def test_05_06_07_restaurante_anula_comida_cena_bebidas(self) -> None:
        set_test_session(iniciar_terminal_restaurante())
        cases = (
            ("comida", "co01"),
            ("cena", "ce01"),
            ("bebidas", "be01"),
        )
        self.data.lotes[0].cantidad_restante = 4.0
        for tipo, rid in cases:
            self.data.registros_servicio.append(_servicio(tipo, rid, qty=1.0))
            r = anul.anular_servicio(rid, f"anular {tipo}")
            self.assertTrue(r.ok, f"{tipo}: {r.mensaje}")
        self.assertEqual(sum(1 for x in self.data.registros_servicio if x.anulado), 3)
        self.assertAlmostEqual(self.data.lotes[0].cantidad_restante, 7.0)

    def test_08_restaurante_sin_permiso_bloqueado(self) -> None:
        set_test_session(_sess_restaurante_sin_permiso())
        self.data.desayunos.append(_desayuno())
        r = anul.anular_desayuno("d01", "motivo")
        self.assertFalse(r.ok)
        self.assertFalse(self.data.desayunos[0].anulado)

    def test_09_otro_terminal_con_registro_bloqueado(self) -> None:
        set_test_session(_sess_otro_terminal_con_registro())
        self.data.desayunos.append(_desayuno())
        r = anul.anular_desayuno("d01", "motivo")
        self.assertFalse(r.ok)
        self.assertIn("Terminal", r.mensaje)
        self.assertFalse(self.data.desayunos[0].anulado)

    def test_10_inventario_no_anula_restaurante(self) -> None:
        set_test_session(iniciar_terminal_inventario())
        # Inventario usa rol administración → tiene ACCEDER_REGISTRO, pero
        # terminal_id no está en allowed_terminals de anulación.
        self.assertTrue(
            Permiso.ACCEDER_REGISTRO
            in __import__("app.core.auth.permissions", fromlist=["permisos_de_rol"]).permisos_de_rol(
                ROL_ADMINISTRACION
            )
        )
        self.data.desayunos.append(_desayuno())
        r = anul.anular_desayuno("d01", "motivo")
        self.assertFalse(r.ok)
        self.assertFalse(self.data.desayunos[0].anulado)


class TestExcepcionAcotada(unittest.TestCase):
    def tearDown(self) -> None:
        restore_harness_session()

    def test_11_12_restaurante_no_abre_otros_deny_terminal(self) -> None:
        clear_test_session()
        set_test_session(iniciar_terminal_restaurante())
        # Sin allowed_terminals: comportamiento histórico
        self.assertIsNotNone(
            usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
        )
        # Restaurante no tiene ACCEDER_INVENTARIO → AuthorizationError (permiso);
        # si lo tuviera, deny_terminal seguiría bloqueando sin allowlist.
        with self.assertRaises(AuthorizationError):
            require_usecase(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
        self.assertIsNotNone(
            usecase_deny_message(Permiso.ACCEDER_CONFIGURACION, deny_terminal=True)
        )
        self.assertIsNotNone(
            usecase_deny_message(Permiso.ACCEDER_COMPRAS_DOCUMENTOS, deny_terminal=True)
        )
        # deny_terminal sin allowlist bloquea ACCEDER_REGISTRO en terminal
        self.assertIsNotNone(
            usecase_deny_message(Permiso.ACCEDER_REGISTRO, deny_terminal=True)
        )
        with self.assertRaises(UseCaseDenied):
            require_usecase(Permiso.ACCEDER_REGISTRO, deny_terminal=True)
        # Con allowed_terminals en ACCEDER_REGISTRO: permitido
        self.assertIsNone(
            usecase_deny_message(
                Permiso.ACCEDER_REGISTRO,
                deny_terminal=True,
                allowed_terminals=frozenset({TERMINAL_ID_DEFAULT}),
            )
        )
        # allowed_terminals no aplica si el permiso no se tiene
        clear_test_session()
        set_test_session(_sess_restaurante_sin_permiso())
        self.assertIsNotNone(
            usecase_deny_message(
                Permiso.ACCEDER_REGISTRO,
                deny_terminal=True,
                allowed_terminals=frozenset({TERMINAL_ID_DEFAULT}),
            )
        )


class TestContratoDominioConservado(_AnulacionHarness):
    def test_13_motivo_vacio(self) -> None:
        set_test_session(iniciar_terminal_restaurante())
        self.data.desayunos.append(_desayuno())
        r = anul.anular_desayuno("d01", "   ")
        self.assertFalse(r.ok)
        self.assertFalse(self.data.desayunos[0].anulado)

    def test_14_ya_anulado(self) -> None:
        set_test_session(iniciar_terminal_restaurante())
        reg = _desayuno()
        self.data.desayunos.append(reg)
        self.assertTrue(anul.anular_desayuno("d01", "uno").ok)
        r2 = anul.anular_desayuno("d01", "dos")
        self.assertFalse(r2.ok)
        self.assertAlmostEqual(self.data.lotes[0].cantidad_restante, 10.0)

    def test_15_historico_sin_consumos(self) -> None:
        set_test_session(iniciar_terminal_restaurante())
        reg = RegistroDesayuno(
            id="d_hist",
            fecha=date(2026, 1, 1),
            coste_total=5.0,
            registrado_por="Ana",
            lineas_detalle=[],
        )
        self.data.desayunos.append(reg)
        self.assertFalse(anul.puede_anular_registro(self.data, reg).ok)
        r = anul.anular_desayuno("d_hist", "intento")
        self.assertFalse(r.ok)
        self.assertFalse(reg.anulado)

    def test_16_17_18_lotes_movimiento_auditoria(self) -> None:
        set_test_session(iniciar_terminal_restaurante())
        self.data.desayunos.append(_desayuno(qty=3.0))
        n_act = len(self.data.actividades)
        n_mov = len(getattr(self.data, "movimientos", None) or [])
        r = anul.anular_desayuno("d01", "carga duplicada", "ref-1")
        self.assertTrue(r.ok, r.mensaje)
        self.assertAlmostEqual(self.data.lotes[0].cantidad_restante, 10.0)
        self.assertEqual(self.data.lotes[0].cantidad, 10.0)
        self.assertGreater(len(self.data.actividades), n_act)
        self.assertEqual(self.data.actividades[0].accion, "Anulación registro")
        movs = self.data.movimientos[n_mov:]
        self.assertTrue(movs)
        tipos = {
            (m.tipo.value if hasattr(m.tipo, "value") else str(m.tipo)) for m in movs
        }
        self.assertIn(TipoMovimiento.REVERSION_CONSUMO.value, tipos)

    def test_19_20_fallo_persistencia_rollback(self) -> None:
        set_test_session(iniciar_terminal_restaurante())
        self.data.desayunos.append(_desayuno())
        # Forzar fallo en commit del UoW de sesión
        with mock.patch(
            "app.core.services.anulacion_registro_service.persist_data",
            side_effect=RuntimeError("disco lleno"),
        ):
            # El UoW de compat llama persist_data en commit
            r = anul.anular_desayuno("d01", "motivo")
        self.assertFalse(r.ok)
        self.assertFalse(self.data.desayunos[0].anulado)
        self.assertAlmostEqual(self.data.lotes[0].cantidad_restante, 7.0)
        self.assertEqual(len(self.data.movimientos or []), 0)


class TestRegresiones(unittest.TestCase):
    def tearDown(self) -> None:
        restore_harness_session()

    def test_21_inventario_sigue_ajustando(self) -> None:
        clear_test_session()
        set_test_session(iniciar_terminal_inventario())
        self.assertIsNone(
            usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
        )
        # Ajuste sigue gated solo por ACCEDER_INVENTARIO + deny_terminal (allowlist inv)
        denied = usecase_deny_message(Permiso.ACCEDER_INVENTARIO, deny_terminal=True)
        self.assertIsNone(denied)

    def test_22_registro_restaurante_sin_deny_sigue_ok(self) -> None:
        clear_test_session()
        set_test_session(iniciar_terminal_restaurante())
        # Registrar no usa deny_terminal
        self.assertIsNone(usecase_deny_message(Permiso.ACCEDER_REGISTRO))
        # Pero con deny_terminal sin allowed_terminals sigue bloqueado
        self.assertIsNotNone(
            usecase_deny_message(Permiso.ACCEDER_REGISTRO, deny_terminal=True)
        )

    def test_23_matriz_roles_intacta(self) -> None:
        from app.core.auth.permissions import permisos_de_rol
        from app.core.auth.roles import ROL_DIRECCION

        self.assertIn(Permiso.ACCEDER_REGISTRO, permisos_de_rol(ROL_DIRECCION))
        self.assertIn(Permiso.ACCEDER_REGISTRO, permisos_de_rol(ROL_RESTAURANTE))
        self.assertNotIn(Permiso.ACCEDER_REGISTRO, permisos_de_rol(ROL_RECEPCION))
        self.assertNotIn(
            Permiso.ACCEDER_INVENTARIO, permisos_de_rol(ROL_RESTAURANTE)
        )


if __name__ == "__main__":
    unittest.main()
