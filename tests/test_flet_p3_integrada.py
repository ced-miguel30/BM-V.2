"""P3 — cadena operativa integrada Flet (sin Streamlit).

Flujo aislado: admin maestros → compra → receta → registro restaurante →
anulación → inventario smoke → backup → integridad demo.

Documentos admin (listar vía documento_consulta_service) omitido a propósito:
añadir sección/VM rompería ADMIN_SECCIONES y tests maestros/compras existentes.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import fields
from datetime import date
from pathlib import Path

os.environ["BM_TEST_ISOLATION"] = "1"

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.session import clear_test_session
from app.core.models import UnidadProducto
from app.core.models.enums import TipoMovimiento
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    set_demo_file_override,
    sha256_demo_file,
)
from app.presentation.flet.presenters.terminal_administracion_presenter import (
    TerminalAdministracionPresenter,
    _backups_dir,
)
from app.presentation.flet.presenters.terminal_inventario_presenter import (
    TerminalInventarioPresenter,
)
from app.presentation.flet.presenters.terminal_restaurante_presenter import (
    TerminalRestaurantePresenter,
)
from app.presentation.flet.viewmodels import (
    AnulacionPendienteVM,
    BasketLineVM,
    BasketVM,
    CatalogItemVM,
    FeedbackVM,
    HistorialRegistroVM,
    SessionVM,
    TerminalScreenVM,
)
from tests.auth_harness import restore_harness_session
from tests.browser.fixtures_minimos import LOGIN_DIR, PASS_DIR, write_browser_fixture


def _stock_producto(producto_id: str) -> float:
    data = get_container().app_data_store.get()
    return sum(
        float(l.cantidad_restante)
        for l in data.lotes
        if l.producto_id == producto_id
    )


class TestFletP3Integrada(unittest.TestCase):
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

    def test_cadena_operativa_producto_compra_receta_consumo_anulacion(self) -> None:
        # 1) Login Administración (Dirección)
        admin = TerminalAdministracionPresenter()
        s = admin.login(LOGIN_DIR, PASS_DIR)
        self.assertTrue(s.session.authenticated, s.feedback.mensaje if s.feedback else "")

        # 2) Crear producto
        s = admin.crear_producto(
            "Ingrediente P3",
            UnidadProducto.KG.value,
            1.0,
            "P3-ING-01",
            "consumible",
            es_bebida=False,
            servicios_disponibles=["desayuno", "comida"],
        )
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        prod = next(x for x in s.productos if x.nombre == "Ingrediente P3")

        # 3) Crear proveedor
        s = admin.crear_proveedor(
            "Proveedor P3",
            "PRV-P3-01",
            nombre_comercial="Prov P3",
            nif_cif="B30990001",
        )
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        prov = next(x for x in s.proveedores if x.codigo == "PRV-P3-01")

        # 4) Confirmar compra → stock aumenta
        stock0 = _stock_producto(prod.id)
        admin.set_compra_cabecera(prov.id, "ALB-P3-1")
        admin.añadir_linea_compra(prod.id, 10.0, 2.0)
        s = admin.confirmar_compra_borrador()
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        stock_tras_compra = _stock_producto(prod.id)
        self.assertAlmostEqual(stock_tras_compra, stock0 + 10.0, places=4)

        # 5) Crear receta con ese producto
        s = admin.crear_receta(
            "Receta P3 Integrada",
            [(prod.id, 1.0)],
            "desayuno",
            1.0,
            servicios_disponibles=["desayuno"],
        )
        self.assertTrue(s.feedback and s.feedback.ok, s.feedback.mensaje if s.feedback else "")
        receta = next(r for r in s.recetas if r.nombre == "Receta P3 Integrada")

        # 6) Terminal Restaurante: servicio + receta + confirmar
        clear_test_session()
        rest = TerminalRestaurantePresenter()
        rs = rest.entrar()
        self.assertTrue(rs.session.authenticated, rs.feedback.mensaje if rs.feedback else "")
        rest.seleccionar_servicio("desayuno")
        rest.set_num_huespedes(8)
        nombres = {c.nombre for c in rest.screen().catalogo}
        self.assertIn("Receta P3 Integrada", nombres)
        add = rest.anadir_receta(receta.id, 1.0)
        self.assertTrue(add.feedback and add.feedback.ok, add.feedback.mensaje if add.feedback else "")
        conf = rest.confirmar(fecha=date.today())
        self.assertTrue(
            conf.feedback and conf.feedback.ok,
            conf.feedback.mensaje if conf.feedback else "",
        )

        # 7) Stock disminuyó
        stock_tras_consumo = _stock_producto(prod.id)
        self.assertAlmostEqual(stock_tras_consumo, stock_tras_compra - 1.0, places=4)

        # 8) Anular vía historial
        hist = rest.seleccionar_servicio("desayuno").historial
        self.assertGreaterEqual(len(hist), 1)
        rid = hist[0].registro_id
        rest.iniciar_anulacion(rid)
        rest.set_motivo_anulacion("P3 reverso stock")
        anul = rest.confirmar_anulacion()
        self.assertTrue(
            anul.feedback and anul.feedback.ok,
            anul.feedback.mensaje if anul.feedback else "",
        )

        # 9) Stock restaurado
        stock_tras_anul = _stock_producto(prod.id)
        self.assertAlmostEqual(stock_tras_anul, stock_tras_compra, places=4)

        # 10) Movimiento REVERSION_CONSUMO
        tipos = {
            getattr(m.tipo, "value", str(m.tipo))
            for m in get_container().app_data_store.get().movimientos
        }
        self.assertIn(TipoMovimiento.REVERSION_CONSUMO.value, tipos)

        # 11) Inventario — smoke auth
        clear_test_session()
        inv = TerminalInventarioPresenter()
        iscreen = inv.entrar()
        self.assertTrue(
            iscreen.session.authenticated,
            iscreen.feedback.mensaje if iscreen.feedback else "",
        )

        # 12) Admin backup → zip existe
        clear_test_session()
        admin2 = TerminalAdministracionPresenter()
        s2 = admin2.login(LOGIN_DIR, PASS_DIR)
        self.assertTrue(s2.session.authenticated)
        sb = admin2.generar_backup()
        self.assertTrue(sb.feedback and sb.feedback.ok, sb.feedback.mensaje if sb.feedback else "")
        zips = list(_backups_dir().glob("*.zip"))
        self.assertTrue(zips)
        self.assertGreater(zips[0].stat().st_size, 0)

        # 13) Demo SHA canónico
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

        # 14) VMs restaurante sin coste_total
        for cls in (
            SessionVM,
            CatalogItemVM,
            BasketLineVM,
            BasketVM,
            FeedbackVM,
            HistorialRegistroVM,
            AnulacionPendienteVM,
            TerminalScreenVM,
        ):
            names = {f.name for f in fields(cls)}
            self.assertNotIn("coste_total", names, msg=cls.__name__)


if __name__ == "__main__":
    unittest.main()
