"""F20 — cierre definitivo de superficie de autorización restante.

    python -m unittest tests.test_f20_complete_auth -v
"""

from __future__ import annotations

import hashlib
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
from app.core.auth.session import (
    AuthSession,
    clear_test_session,
    set_test_session,
)
from app.core.models import (
    AppData,
    ArchivoDocumental,
    Documento,
    EstadoDocumento,
    LoteStock,
    Producto,
    Proveedor,
    TipoDocumento,
    UnidadProducto,
)
from app.core.services import (
    alert_service,
    albaran_service,
    anulacion_documento_service as anul_doc,
    archivo_documental_service as ads,
    compra_registro_service as compra,
    desayuno_service,
    documento_consulta_service as docq,
    export_service,
    exportacion_semanal_service as exp_sem,
    factura_service,
    historial_compras_service as hist,
    merma_service,
    rectificativa_service,
    restore_backup_service as rst,
    settings_service,
)
from app.core.services import destructive_ops_service as dop
from app.core.services.cesta_service import LineaCesta
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    sha256_demo_file,
)
from app.data.serializers import appdata_to_dict, dict_to_appdata
from tests.auth_harness import restore_harness_session


def _sess(
    role: str,
    *,
    actor_type: str = "usuario",
    actor_id: str = "u1",
    authenticated: bool = True,
) -> AuthSession:
    return AuthSession(
        authenticated=authenticated,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=f"label-{role}",
        role=role,
        session_id=f"f20-{role}" if authenticated else "",
        login_at="2026-01-01T00:00:00" if authenticated else "",
        terminal_id="terminal_restaurante" if actor_type == "terminal" else None,
        login=f"login-{role}",
    )


def _data() -> AppData:
    return AppData(
        productos=[
            Producto("p1", "Pan", UnidadProducto.UD, servicios_disponibles=["desayuno"])
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
        proveedores=[
            Proveedor(id="prov1", nombre_fiscal="Prov SA", codigo="PROV1", activo=True)
        ],
        documentos=[
            Documento(
                id="doc1",
                tipo=TipoDocumento.ALBARAN,
                estado=EstadoDocumento.BORRADOR,
                fecha_documento=date(2026, 7, 1),
                proveedor_id="prov1",
            )
        ],
        archivos_documentales=[
            ArchivoDocumental(
                id="adoc1",
                nombre_original="x.pdf",
                mime_type="application/pdf",
                tamanio_bytes=3,
                sha256="abc",
                ruta_relativa="adoc1/x.pdf",
                creado_en=datetime(2026, 7, 1),
                activo=True,
            )
        ],
    )


class TestF20CompleteAuth(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _data()
        self._session: dict = {}
        self._st = patch("streamlit.session_state", self._session)
        self._st.start()
        clear_test_session()
        self.addCleanup(self._st.stop)
        self.addCleanup(restore_harness_session)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base_docs = Path(self.tmp.name) / "documentos"
        self.base_docs.mkdir()
        self.json_path = Path(self.tmp.name) / "datos.json"

    def _ctx(self, label: str = "Actor"):
        return build_app_context(
            uow=InMemoryUnitOfWork(self.data),
            clock=FixedClock(datetime(2026, 7, 30, 8, 0, 0)),
            actor=Actor(id="a1", nombre=label, rol="x"),
        )

    def _snap(self) -> dict:
        return {
            "json": appdata_to_dict(self.data),
            "lote": self.data.lotes[0].cantidad_restante,
            "docs": len(self.data.documentos),
            "alertas": len(getattr(self.data, "alertas", []) or []),
            "resp": len(getattr(self.data, "responsables_merma", []) or []),
            "archivos": [
                (a.id, a.activo, a.documento_id)
                for a in (getattr(self.data, "archivos_documentales", []) or [])
            ],
            "disk": sorted(p.name for p in self.base_docs.rglob("*") if p.is_file()),
        }

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

    # --- 1–2 Dirección / Administración ---

    def test_01_direccion_familias(self) -> None:
        set_test_session(_sess("direccion"))
        ctx = self._ctx("Dir")
        self.assertTrue(
            alert_service.crear_alerta_manual("T", "M", ctx=ctx).ok
        )
        self.assertTrue(
            merma_service.crear_responsable_merma("Resp F20", ctx=ctx).ok
        )
        r = ads.registrar_archivo(
            b"abc", "f20.pdf", ctx=ctx, base_dir=self.base_docs
        )
        self.assertTrue(r.ok, r.mensaje)
        self.assertTrue(
            compra.guardar_borrador(
                self.data, proveedor_id="prov1", referencia_externa="R1"
            ).ok
        )
        docs = docq.buscar_documentos(data=self.data)
        self.assertGreaterEqual(len(docs), 1)
        albs = albaran_service.listar_albaranes(ctx=ctx)
        self.assertIsInstance(albs, list)
        settings_service.guardar_configuracion  # noqa: B018 — reachable
        with patch("app.core.services.settings_service.get_data", return_value=self.data), patch(
            "app.core.services.settings_service.persist_data"
        ):
            self.assertTrue(settings_service.guardar_configuracion("Hotel F20", "EUR").ok)

    def test_02_admin_ordinario_sin_c2_c3(self) -> None:
        set_test_session(_sess("administracion"))
        ctx = self._ctx("Adm")
        self.assertTrue(alert_service.crear_alerta_manual("A", "B", ctx=ctx).ok)
        self.assertTrue(merma_service.crear_responsable_merma("AdmResp", ctx=ctx).ok)
        self.assertTrue(
            compra.guardar_borrador(self.data, proveedor_id="prov1").ok
        )
        docq.buscar_documentos(data=self.data)
        with self.assertRaises(AuthorizationError):
            rst.inspeccionar_backup(b"PK\x03\x04fake")
        self.assertFalse(
            rst.restaurar_desde_bytes(b"x", destino_json=self.json_path).ok
        )
        self.assertFalse(
            dop.restablecer_a_datos_mock(
                confirmacion_escrita=dop.FRASE_RESET_TOTAL,
                checkbox_aceptado=True,
                destino_json=self.json_path,
            ).ok
        )

    # --- 4–6 Recepción / Terminal ---

    def test_04_05_recepcion_y_terminal_rechazados(self) -> None:
        ctx = self._ctx()
        for role, kwargs in (
            ("recepcion", {}),
            ("restaurante", {"actor_type": "terminal", "actor_id": "terminal_restaurante"}),
        ):
            set_test_session(_sess(role, **kwargs))
            before = self._snap()
            self.assertFalse(alert_service.crear_alerta_manual("x", "y", ctx=ctx).ok)
            self.assertFalse(
                merma_service.crear_responsable_merma("Hack", ctx=ctx).ok
            )
            self.assertFalse(
                ads.registrar_archivo(b"x", "h.pdf", ctx=ctx, base_dir=self.base_docs).ok
            )
            bruto, err = ads.leer_bytes("adoc1", ctx=ctx)
            self.assertIsNone(bruto)
            self.assertTrue(err)
            self.assertNotIn("\\", err.replace("/", ""))
            self.assertFalse(compra.guardar_borrador(self.data).ok)
            with self.assertRaises(AuthorizationError):
                docq.buscar_documentos(data=self.data)
            with self.assertRaises(AuthorizationError):
                albaran_service.listar_albaranes(ctx=ctx)
            with self.assertRaises(AuthorizationError):
                factura_service.listar_facturas(ctx=ctx)
            with self.assertRaises(AuthorizationError):
                rectificativa_service.listar_rectificativas(ctx=ctx)
            self.assertFalse(
                docq.exportar_documentos_csv(ctx=ctx).ok
            )
            with self.assertRaises(AuthorizationError):
                export_service.exportar_informe_cliente(
                    date(2026, 7, 1), date(2026, 7, 31)
                )
            self.assertFalse(
                anul_doc.anular_conciliacion(
                    "c1", motivo="x", json_path=self.json_path
                ).ok
            )
            self.assertEqual(self._snap()["lote"], before["lote"])
            self.assertEqual(self._snap()["docs"], before["docs"])
            self.assertEqual(self._snap()["disk"], before["disk"])
            self.assertEqual(self._snap()["archivos"], before["archivos"])

    def test_06_terminal_conserva_registro(self) -> None:
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

    # --- 7–12 sesión ---

    def test_07_12_sesion_ausente_invalida_manipulada(self) -> None:
        ctx = self._ctx()
        clear_test_session()
        before = self._snap()
        self.assertFalse(alert_service.crear_alerta_manual("t", "m", ctx=ctx).ok)
        self.assertFalse(
            ads.registrar_archivo(b"z", "z.pdf", ctx=ctx, base_dir=self.base_docs).ok
        )
        self.assertEqual(self._snap()["disk"], before["disk"])

        # authenticated=False con role dirección
        set_test_session(_sess("direccion", authenticated=False))
        self.assertFalse(compra.guardar_borrador(self.data).ok)

        # rol manipulado en objeto no autenticado no concede
        set_test_session(
            AuthSession(
                authenticated=False,
                actor_type="usuario",
                actor_id="direccion",
                actor_label="Dirección",
                role="direccion",
                session_id="hack",
                login_at="",
            )
        )
        with self.assertRaises(AuthorizationError):
            docq.buscar_documentos(data=self.data)

        # actor_id / label no sustituyen AuthSession válida
        set_test_session(
            AuthSession(
                authenticated=True,
                actor_type="usuario",
                actor_id="direccion",
                actor_label="Dirección",
                role="recepcion",
                session_id="f20-fake",
                login_at="2026-01-01T00:00:00",
            )
        )
        self.assertFalse(
            merma_service.crear_responsable_merma("No", ctx=ctx).ok
        )

    # --- 13–19 alertas y archivos ---

    def test_13_19_alertas_archivos_antes_de_escribir(self) -> None:
        ctx = self._ctx()
        set_test_session(_sess("recepcion"))
        before = self._snap()
        self.assertFalse(
            alert_service.cambiar_estado_alerta("nope", "resuelta", ctx=ctx).ok
        )
        self.assertEqual(len(self.data.alertas), before["alertas"])

        # descarga no autorizada
        bruto, err = ads.leer_bytes("adoc1", ctx=ctx)
        self.assertIsNone(bruto)
        self.assertTrue(err)
        for bad in ("C:\\", "/home/", "password", "sha256"):
            self.assertNotIn(bad.lower(), err.lower())

        # eliminación / enlace no autorizados
        self.assertFalse(ads.desactivar_archivo("adoc1", ctx=ctx).ok)
        self.assertTrue(self.data.archivos_documentales[0].activo)
        self.assertFalse(ads.enlazar_documento("adoc1", "doc1", ctx=ctx).ok)
        self.assertIsNone(self.data.archivos_documentales[0].documento_id)

        # subida no crea staging
        self.assertFalse(
            ads.registrar_archivo(b"SECRET", "s.pdf", ctx=ctx, base_dir=self.base_docs).ok
        )
        self.assertEqual(list(self.base_docs.rglob("*")), [])
        self.assertEqual(appdata_to_dict(self.data)["archivos_documentales"][0]["id"], "adoc1")

        # autorizado sí escribe
        set_test_session(_sess("administracion"))
        r = ads.registrar_archivo(b"ok", "ok.pdf", ctx=ctx, base_dir=self.base_docs)
        self.assertTrue(r.ok, r.mensaje)
        self.assertTrue(any(self.base_docs.rglob("*.pdf")))

    # --- 20–21 responsables ---

    def test_20_21_responsables_matriz_e_historico(self) -> None:
        ctx = self._ctx()
        set_test_session(_sess("administracion"))
        self.assertTrue(merma_service.crear_responsable_merma("Ana", ctx=ctx).ok)
        rid = self.data.responsables_merma[0].id
        self.assertTrue(
            merma_service.renombrar_responsable_merma(rid, "Ana 2", ctx=ctx).ok
        )
        # histórico sin campo carga
        raw = {"productos": [], "responsables_merma": [{"id": "rm9", "nombre": "Old", "activo": True}]}
        loaded = dict_to_appdata(raw)
        self.assertEqual(loaded.responsables_merma[0].nombre, "Old")
        # listar puro sin auth
        clear_test_session()
        names = merma_service.listar_responsables_merma(ctx=self._ctx())
        self.assertTrue(any(r.nombre == "Ana 2" for r in names))

    # --- 22–25 borradores ---

    def test_22_25_borrador_rechazo_antes_escritura(self) -> None:
        set_test_session(_sess("recepcion"))
        before = appdata_to_dict(self.data)
        r = compra.guardar_borrador(self.data, proveedor_id="prov1")
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo, "no_autorizado")
        self.assertEqual(appdata_to_dict(self.data), before)

        r2 = compra.guardar_borrador_persistente(
            json_path=self.json_path, proveedor_id="prov1"
        )
        self.assertFalse(r2.ok)
        self.assertFalse(self.json_path.exists())

        set_test_session(_sess("restaurante", actor_type="terminal"))
        conf = compra.confirmar_compra(
            "doc1",
            confirmacion_id="00000000-0000-4000-8000-000000000001",
            contenido_hash="x",
            json_path=self.json_path,
        )
        self.assertFalse(conf.ok)
        self.assertEqual(conf.codigo, "no_autorizado")
        self.assertIsNone(conf.adjuntos_publicados)

    # --- 26–30 documentos ---

    def test_26_30_consulta_export_legacy(self) -> None:
        ctx = self._ctx()
        set_test_session(_sess("direccion"))
        self.assertGreaterEqual(len(docq.buscar_documentos(data=self.data)), 1)
        self.assertIsInstance(docq.resumen_documento(self.data.documentos[0]), dict)
        # puro sin auth
        clear_test_session()
        preview = albaran_service.preview_confirmacion(self.data.documentos[0])
        self.assertIsInstance(preview, list)

        set_test_session(_sess("recepcion"))
        with self.assertRaises(AuthorizationError):
            ads.listar_archivos(ctx=ctx)
        with self.assertRaises(AuthorizationError):
            hist.exportar_historial_hasta(date(2026, 7, 1), "fecha")

    # --- helpers puros / autorizado conserva ---

    def test_31_32_helpers_y_autorizado(self) -> None:
        clear_test_session()
        self.assertEqual(ads.sha256_bytes(b"abc")[:8], hashlib.sha256(b"abc").hexdigest()[:8])
        self.assertTrue(exp_sem.limite_semana(date(2026, 7, 27)))

        set_test_session(_sess("direccion"))
        ctx = self._ctx("Dir")
        n_before = len(self.data.alertas)
        self.assertTrue(alert_service.crear_alerta_manual("OK", "msg", ctx=ctx).ok)
        self.assertEqual(len(self.data.alertas), n_before + 1)

    def test_42_demo_hash(self) -> None:
        self.assertEqual(os.environ.get("BM_TEST_ISOLATION"), "1")
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def test_48_errores_no_filtran_rutas(self) -> None:
        set_test_session(_sess("recepcion"))
        _, err = ads.leer_bytes("adoc1", ctx=self._ctx())
        self.assertNotRegex(err, r"[A-Za-z]:\\")
        self.assertNotIn(str(DEMO_FILE), err)


if __name__ == "__main__":
    unittest.main()
