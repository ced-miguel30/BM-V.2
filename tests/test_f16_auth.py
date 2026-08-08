"""F16 — autenticación, sesiones, roles y autorización efectiva.

    python -m unittest tests.test_f16_auth -v
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["BM_TEST_ISOLATION"] = "1"

from app.core.auth import (
    MSG_LOGIN_FALLIDO,
    Permiso,
    ROLES_CANONICOS,
    autenticar_usuario,
    hash_password,
    identify_hash_format,
    iniciar_terminal_restaurante,
    matriz_permisos,
    necesita_bootstrap,
    puede_ver_seccion,
    rol_canonico,
    tiene_permiso,
    verify_password,
)
from app.core.auth.passwords import LEGACY_PLAIN_PREFIX, migrate_legacy_if_needed
from tests.auth_harness import restore_harness_session
from app.core.auth.session import (
    AuthSession,
    clear_test_session,
    get_auth_session,
    logout,
    save_auth_session,
    set_test_session,
)
from app.core.models import AppData, Producto, RolUsuario, UnidadProducto, Usuario
from app.core.services import backup_service as bak
from app.core.services import destructive_ops_service as dop
from app.core.services import restore_backup_service as rst
from app.core.services import settings_service as sett
from app.core.storage.demo_files import (
    DEMO_CONTENT_SHA256_CANONICO,
    DEMO_FILE,
    set_demo_file_override,
    sha256_demo_file,
)
from app.core.storage.json_atomic import atomic_write_json
from app.data.serializers import appdata_to_dict, dict_to_appdata
from app.pages import settings as settings_page
from app.pages import stock


def _dir_session(**kw) -> AuthSession:
    base = dict(
        authenticated=True,
        actor_type="usuario",
        actor_id="u_dir",
        actor_label="Dir",
        role="direccion",
        session_id="s1",
        login_at="2026-01-01T00:00:00",
        login="dir",
    )
    base.update(kw)
    return AuthSession(**base)


class TestF16Passwords(unittest.TestCase):
    def test_01_hash_y_verificacion(self) -> None:
        h = hash_password("secreto-seguro-1")
        self.assertTrue(verify_password("secreto-seguro-1", h))
        self.assertEqual(identify_hash_format(h), "pbkdf2_sha256")

    def test_02_salts_distintos(self) -> None:
        a = hash_password("misma")
        b = hash_password("misma")
        self.assertNotEqual(a, b)

    def test_03_incorrecta_rechazada(self) -> None:
        h = hash_password("ok-password")
        self.assertFalse(verify_password("otra", h))


class TestF16Login(unittest.TestCase):
    def setUp(self) -> None:
        clear_test_session()
        self.users = [
            Usuario(
                "u1",
                "Ana",
                RolUsuario.DIRECCION,
                True,
                login="ana",
                password_hash=hash_password("clave-ana-99"),
            ),
            Usuario(
                "u2",
                "Bob",
                RolUsuario.ADMINISTRACION,
                False,
                login="bob",
                password_hash=hash_password("clave-bob-99"),
            ),
        ]

    def tearDown(self) -> None:
        restore_harness_session()

    def test_04_usuario_inexistente_y_mala_clave_mismo_mensaje(self) -> None:
        a = autenticar_usuario(self.users, "nadie", "x")
        b = autenticar_usuario(self.users, "ana", "mala")
        self.assertFalse(a.ok)
        self.assertFalse(b.ok)
        self.assertEqual(a.mensaje, b.mensaje)
        self.assertEqual(a.mensaje, MSG_LOGIN_FALLIDO)

    def test_05_inactivo_no_autentica(self) -> None:
        r = autenticar_usuario(self.users, "bob", "clave-bob-99")
        self.assertFalse(r.ok)

    def test_06_sesion_identidad_rol(self) -> None:
        r = autenticar_usuario(self.users, "ana", "clave-ana-99")
        self.assertTrue(r.ok)
        self.assertEqual(r.session.actor_id, "u1")
        self.assertEqual(r.session.role, "direccion")
        self.assertTrue(r.session.session_id)

    def test_07_logout_limpia(self) -> None:
        r = autenticar_usuario(self.users, "ana", "clave-ana-99")
        set_test_session(r.session)
        self.assertTrue(get_auth_session().authenticated)
        logout()
        self.assertIsNone(get_auth_session())

    def test_08_no_password_en_sesion(self) -> None:
        r = autenticar_usuario(self.users, "ana", "clave-ana-99")
        d = r.session.to_dict()
        self.assertNotIn("password", d)
        self.assertNotIn("password_hash", d)
        blob = json.dumps(d)
        self.assertNotIn("clave-ana", blob)


class TestF16RolesPermisos(unittest.TestCase):
    def test_09_roles_canonicos(self) -> None:
        self.assertEqual(
            set(ROLES_CANONICOS),
            {"direccion", "administracion", "recepcion", "restaurante"},
        )
        self.assertEqual(rol_canonico(RolUsuario.OWNER), "direccion")
        self.assertEqual(rol_canonico(RolUsuario.ADMIN), "administracion")

    def test_10_matriz_completa(self) -> None:
        m = matriz_permisos()
        self.assertIn(Permiso.RESTAURAR_BACKUP, m["direccion"])
        self.assertNotIn(Permiso.RESTAURAR_BACKUP, m["administracion"])
        self.assertNotIn(Permiso.EJECUTAR_OPERACION_DESTRUCTIVA, m["administracion"])
        self.assertIn(Permiso.ACCEDER_CONFIGURACION, m["administracion"])
        self.assertEqual(m["recepcion"], frozenset())
        self.assertIn(Permiso.REGISTRAR_CONSUMO_TERMINAL, m["restaurante"])
        self.assertNotIn(Permiso.CONSULTAR_COSTES, m["restaurante"])
        self.assertNotIn(Permiso.ACCEDER_INVENTARIO, m["restaurante"])

    def test_11_12_13_14_navegacion(self) -> None:
        self.assertTrue(puede_ver_seccion("direccion", "Configuración"))
        self.assertTrue(puede_ver_seccion("direccion", "Stock"))
        self.assertTrue(puede_ver_seccion("administracion", "Stock"))
        self.assertTrue(puede_ver_seccion("administracion", "Configuración"))
        self.assertFalse(puede_ver_seccion("recepcion", "Stock"))
        self.assertFalse(puede_ver_seccion("recepcion", "Configuración"))
        self.assertTrue(puede_ver_seccion("restaurante", "Registros"))
        self.assertFalse(puede_ver_seccion("restaurante", "Configuración"))
        self.assertFalse(puede_ver_seccion("restaurante", "Stock"))
        self.assertFalse(puede_ver_seccion("restaurante", "Análisis"))


class TestF16AuthzServices(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.json_path = self.root / "datos.json"
        data = AppData()
        data.productos.append(Producto("p1", "A", UnidadProducto.UD, codigo="P1"))
        data.usuarios = [
            Usuario(
                "u_dir",
                "Dir",
                RolUsuario.DIRECCION,
                True,
                login="dir",
                password_hash=hash_password("dir-pass-99"),
            ),
            Usuario(
                "u_adm",
                "Adm",
                RolUsuario.ADMINISTRACION,
                True,
                login="adm",
                password_hash=hash_password("adm-pass-99"),
            ),
        ]
        data.usuario_actual_id = "u_dir"
        atomic_write_json(self.json_path, appdata_to_dict(data))
        set_demo_file_override(self.json_path)
        clear_test_session()
        self.addCleanup(restore_harness_session)
        self.addCleanup(set_demo_file_override, None)
        self.addCleanup(self._tmp.cleanup)

    def test_15_16_acceso_directo_y_manipulacion(self) -> None:
        # Sin sesión
        res = rst.restaurar_desde_bytes(b"x", destino_json=self.json_path)
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "no_autorizado")
        # Manipular "rol" en dict sin sesión válida
        set_test_session(
            AuthSession(
                authenticated=False,
                actor_type="usuario",
                actor_id="x",
                actor_label="x",
                role="direccion",
                session_id="x",
                login_at="",
            )
        )
        # from_dict con authenticated False → None
        self.assertIsNone(get_auth_session())

    def test_17_18_restaurar_por_rol(self) -> None:
        set_test_session(_dir_session())
        zip_bytes = bak.generar_backup_zip(
            dict_to_appdata(json.loads(self.json_path.read_text(encoding="utf-8")))
        ).contenido
        set_test_session(_dir_session(role="administracion", actor_id="u_adm"))
        bad = rst.restaurar_desde_bytes(
            zip_bytes, destino_json=self.json_path, project_root=self.root
        )
        self.assertFalse(bad.ok)
        set_test_session(_dir_session())
        good = rst.restaurar_desde_bytes(
            zip_bytes, destino_json=self.json_path, project_root=self.root
        )
        self.assertTrue(good.ok, good.mensaje)

    def test_19_20_zona_peligro_por_rol(self) -> None:
        set_test_session(_dir_session(role="administracion"))
        bad = dop.restablecer_a_datos_mock(
            confirmacion_escrita=dop.FRASE_RESET_TOTAL,
            checkbox_aceptado=True,
            destino_json=self.json_path,
            operation_token="t-adm",
        )
        self.assertFalse(bad.ok)
        self.assertEqual(bad.error, "no_autorizado")
        set_test_session(_dir_session())
        dop.clear_consumed_tokens()
        good = dop.restablecer_a_datos_mock(
            confirmacion_escrita=dop.FRASE_RESET_TOTAL,
            checkbox_aceptado=True,
            destino_json=self.json_path,
            operation_token="t-dir",
        )
        self.assertTrue(good.ok, good.mensaje)

    def test_21_22_restaurante_costes_inventario(self) -> None:
        self.assertFalse(tiene_permiso("restaurante", Permiso.CONSULTAR_COSTES))
        self.assertFalse(tiene_permiso("restaurante", Permiso.ACCEDER_INVENTARIO))
        self.assertFalse(puede_ver_seccion("restaurante", "Stock"))

    def test_23_24_terminal_actor(self) -> None:
        s = iniciar_terminal_restaurante()
        self.assertEqual(s.actor_type, "terminal")
        self.assertEqual(s.actor_label, "Restaurante")
        self.assertEqual(s.role, "restaurante")
        self.assertTrue(tiene_permiso(s.role, Permiso.REGISTRAR_CONSUMO_TERMINAL))
        set_test_session(s)
        from app.core.application.actor import actor_desde_auth_session

        act = actor_desde_auth_session()
        self.assertEqual(act.nombre, "Restaurante")
        self.assertEqual(act.actor_type, "terminal")


class TestF16UsuariosReglas(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.json_path = Path(self._tmp.name) / "datos.json"
        data = AppData()
        data.usuarios = [
            Usuario(
                "u_dir",
                "Dir",
                RolUsuario.DIRECCION,
                True,
                login="dir",
                password_hash=hash_password("dir-pass-99"),
            ),
            Usuario(
                "u_adm",
                "Adm",
                RolUsuario.ADMINISTRACION,
                True,
                login="adm",
                password_hash=hash_password("adm-pass-99"),
            ),
        ]
        data.usuario_actual_id = "u_dir"
        atomic_write_json(self.json_path, appdata_to_dict(data))
        set_demo_file_override(self.json_path)
        clear_test_session()
        self._data = dict_to_appdata(json.loads(self.json_path.read_text(encoding="utf-8")))

        def _get():
            return self._data

        def _persist(d):
            self._data = d
            atomic_write_json(self.json_path, appdata_to_dict(d))
            return d

        self._p_get = patch("app.core.services.settings_service.get_data", side_effect=_get)
        self._p_persist = patch(
            "app.core.services.settings_service.persist_data", side_effect=_persist
        )
        self._p_get.start()
        self._p_persist.start()
        self.addCleanup(self._p_persist.stop)
        self.addCleanup(self._p_get.stop)
        self.addCleanup(restore_harness_session)
        self.addCleanup(set_demo_file_override, None)
        self.addCleanup(self._tmp.cleanup)

    def test_25_historicos_sin_actor(self) -> None:
        from app.data.serializers import _usuario_from_dict

        hist = _usuario_from_dict(
            {"id": "u9", "nombre": "Viejo", "rol": "Owner", "activo": True}
        )
        self.assertEqual(rol_canonico(hist.rol), "direccion")
        self.assertEqual(hist.login, "")
        self.assertEqual(hist.password_hash, "")

    def test_26_admin_no_crea_direccion(self) -> None:
        set_test_session(_dir_session(role="administracion", actor_id="u_adm"))
        r = sett.crear_usuario(
            "X", "direccion", login="xdir", password="password99"
        )
        self.assertFalse(r.ok)

    def test_27_28_29_ultimo_direccion(self) -> None:
        set_test_session(_dir_session())
        r = sett.set_usuario_activo("u_dir", False)
        self.assertFalse(r.ok)
        r2 = sett.eliminar_usuario("u_dir")
        self.assertFalse(r2.ok)
        r3 = sett.cambiar_rol_usuario("u_dir", "administracion")
        self.assertFalse(r3.ok)

    def test_30_no_autoeliminar(self) -> None:
        set_test_session(_dir_session(actor_id="u_dir"))
        sett.crear_usuario(
            "Otra", "direccion", login="otra", password="password99"
        )
        r = sett.eliminar_usuario("u_dir")
        self.assertFalse(r.ok)
        self.assertIn("sí mismo", r.mensaje.lower())

    def test_32_cambio_password_invalida_anterior(self) -> None:
        set_test_session(_dir_session())
        sett.restablecer_password("u_adm", "nueva-clave-88")
        adm = next(u for u in self._data.usuarios if u.id == "u_adm")
        self.assertFalse(verify_password("adm-pass-99", adm.password_hash))
        self.assertTrue(verify_password("nueva-clave-88", adm.password_hash))


class TestF16BootstrapLegacyUI(unittest.TestCase):
    def test_33_hash_no_en_ui_source(self) -> None:
        src = Path(settings_page.__file__).read_text(encoding="utf-8")
        self.assertNotIn("password_hash", src)
        self.assertIn("Nunca se muestran contraseñas", src)

    def test_34_legacy_migra(self) -> None:
        stored = LEGACY_PLAIN_PREFIX + "vieja-clave"
        new_h = migrate_legacy_if_needed("vieja-clave", stored)
        self.assertIsNotNone(new_h)
        self.assertTrue(new_h.startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password("vieja-clave", new_h))
        users = [
            Usuario(
                "u1",
                "L",
                RolUsuario.DIRECCION,
                True,
                login="leg",
                password_hash=stored,
            )
        ]
        r = autenticar_usuario(users, "leg", "vieja-clave")
        self.assertTrue(r.ok)
        self.assertTrue(r.password_migrated)
        self.assertTrue(users[0].password_hash.startswith("pbkdf2_sha256$"))

    def test_35_36_bootstrap(self) -> None:
        users = [
            Usuario("u1", "M", RolUsuario.DIRECCION, True, login="", password_hash="")
        ]
        self.assertTrue(necesita_bootstrap(users))
        users[0].password_hash = hash_password("ya-tiene-99")
        users[0].login = "m"
        self.assertFalse(necesita_bootstrap(users))
        # No default password constant in bootstrap module
        from app.core.services import settings_service as ss

        src = Path(ss.__file__).read_text(encoding="utf-8")
        self.assertNotIn("changeme", src.lower())
        self.assertNotIn("default_password", src.lower())

    def test_37_38_tokens_c2_c3_actor(self) -> None:
        from app.core.auth.session import invalidate_destructive_ui_tokens

        # Sin streamlit: no rompe
        invalidate_destructive_ui_tokens()
        set_test_session(_dir_session(session_id="a"))
        set_test_session(_dir_session(session_id="b", actor_id="other"))
        self.assertEqual(get_auth_session().actor_id, "other")

    def test_39_deeplink_permiso(self) -> None:
        self.assertFalse(puede_ver_seccion("restaurante", "Configuración"))
        self.assertFalse(puede_ver_seccion("recepcion", "Dashboard"))


class TestF16Regresion(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.json_path = self.root / "datos.json"
        data = AppData()
        data.productos.append(Producto("p1", "A", UnidadProducto.UD, codigo="P1"))
        atomic_write_json(self.json_path, appdata_to_dict(data))
        set_demo_file_override(self.json_path)
        set_test_session(_dir_session())
        dop.clear_consumed_tokens()
        self.addCleanup(restore_harness_session)
        self.addCleanup(set_demo_file_override, None)
        self.addCleanup(self._tmp.cleanup)

    def test_40_c1_compras(self) -> None:
        self.assertIn(stock.TAB_COMPRAS_DOCUMENTOS, stock._SUBTABS)
        self.assertNotIn("Albaranes", stock._SUBTABS)

    def test_41_c2_dir(self) -> None:
        z = bak.generar_backup_zip(
            dict_to_appdata(json.loads(self.json_path.read_text(encoding="utf-8")))
        ).contenido
        r = rst.restaurar_desde_bytes(
            z, destino_json=self.json_path, project_root=self.root
        )
        self.assertTrue(r.ok, r.mensaje)

    def test_42_c3_frase(self) -> None:
        self.assertFalse(
            dop.boton_destructivo_habilitado(dop.FRASE_RESET_TOTAL, "MAL", True)
        )
        self.assertTrue(
            dop.boton_destructivo_habilitado(
                dop.FRASE_RESET_TOTAL, dop.FRASE_RESET_TOTAL, True
            )
        )

    def test_43_demo_rechazado(self) -> None:
        self.assertTrue(rst.destino_es_demo_protegido(DEMO_FILE))
        r = dop.restablecer_a_datos_mock(
            confirmacion_escrita=dop.FRASE_RESET_TOTAL,
            checkbox_aceptado=True,
            destino_json=DEMO_FILE,
            operation_token="demo",
        )
        self.assertFalse(r.ok)

    def test_44_45_isolation_hash(self) -> None:
        self.assertEqual(os.environ.get("BM_TEST_ISOLATION"), "1")
        self.assertEqual(sha256_demo_file(DEMO_FILE), DEMO_CONTENT_SHA256_CANONICO)

    def test_46_47_serializers_usuarios(self) -> None:
        payload = {
            "id": "ux",
            "nombre": "Hist",
            "rol": "Admin",
            "activo": True,
        }
        from app.data.serializers import _usuario_from_dict, _usuario_to_dict

        u = _usuario_from_dict(payload)
        self.assertEqual(rol_canonico(u.rol), "administracion")
        d = _usuario_to_dict(u)
        self.assertEqual(d["rol"], "administracion")
        self.assertIn("login", d)
        self.assertIn("password_hash", d)

    def test_48_sin_tmp(self) -> None:
        self.assertEqual(list(self.root.rglob("*.tmp.*")), [])


if __name__ == "__main__":
    unittest.main()
