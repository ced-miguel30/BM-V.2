"""Tests de la API: permisos por rol y flujos principales, sobre una base temporal (nunca la real)."""

import tempfile
import unittest
from pathlib import Path

from bm import db

_tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
db.DB_PATH = Path(_tmp.name) / "test.sqlite"  # antes de importar bm.app, que abre la base al importarse

from fastapi.testclient import TestClient  # noqa: E402

from bm import app as A, usuarios  # noqa: E402

con = A.con
con.executemany("INSERT INTO productos(codigo, nombre, unidad, categoria) VALUES(?,?,?,'101')",
                [("HUEVO", "HUEVO CASCARA", "UD"), ("PAN", "PAN MOLDE", "UD")])
con.executemany("INSERT INTO bc_movs(n_mov, fecha, tipo, almacen, producto, cantidad, coste_total) VALUES(?,?,?,?,?,?,?)", [
    (1, "2026-09-01", "Compra", "DESAYUNO", "HUEVO", 100, 30.0),
    (2, "2026-09-01", "Compra", "DESAYUNO", "PAN", 10, 20.0),
])
con.execute("UPDATE bc_movs SET documento='AL0001', proveedor='GRANJA SL', tipo_doc='Albarán compra'")
con.execute("INSERT INTO recetas(id, nombre, servicio, porciones) VALUES('r1', 'Huevos con tostada', 'desayuno', 1)")
con.executemany("INSERT INTO receta_lineas VALUES('r1', ?, ?)", [("HUEVO", 2), ("PAN", 0.1)])
con.commit()
from bm import inventario  # noqa: E402
inventario.sembrar(con)  # proveedores y almacenes de los movimientos de prueba
for login, rol in (("dir", "direccion"), ("adm", "administracion"), ("rest", "restaurante")):
    usuarios.guardar(con, login, login.upper(), rol, "clave-segura")


def tearDownModule():
    con.close()  # Windows no deja borrar la carpeta temporal con la base abierta


def cliente(login=None):
    c = TestClient(A.app)
    if login:
        r = c.post("/api/login", json={"login": login, "password": "clave-segura"})
        assert r.status_code == 200, r.text
    return c


class TestPermisos(unittest.TestCase):
    def test_sin_sesion_401(self):
        for ruta in ("/api/panel", "/api/catalogo", "/api/stock", "/api/config"):
            self.assertEqual(cliente().get(ruta).status_code, 401, ruta)

    def test_restaurante_no_ve_costes_ni_gestion(self):
        c = cliente("rest")
        for ruta in ("/api/panel", "/api/consumos?desde=2026-01-01&hasta=2026-12-31", "/api/config", "/api/analisis/precios"):
            self.assertEqual(c.get(ruta).status_code, 403, ruta)
        self.assertEqual(c.get("/api/catalogo").status_code, 200)
        fila = c.get("/api/stock?ubicacion=RESTAURANTE").json()[0]
        self.assertNotIn("valor", fila)
        self.assertNotIn("precio", fila)

    def test_solo_direccion_gestiona_usuarios(self):
        body = {"login": "nuevo", "nombre": "Nuevo", "rol": "restaurante", "password": "clave-segura"}
        self.assertEqual(cliente("adm").post("/api/config/usuarios", json=body).status_code, 403)
        self.assertEqual(cliente("dir").post("/api/config/usuarios", json=body).status_code, 200)

    def test_login_incorrecto(self):
        self.assertEqual(cliente().post("/api/login", json={"login": "dir", "password": "mal"}).status_code, 401)


class TestFlujos(unittest.TestCase):
    def test_registrar_valorar_y_anular(self):
        rest, d = cliente("rest"), cliente("dir")
        r = rest.post("/api/consumos", json={"fecha": "2026-09-02", "servicio": "desayuno", "comensales": 5,
                                             "items": [{"receta_id": "r1", "cantidad": 5}]})
        self.assertEqual(r.status_code, 200, r.text)
        det = d.get(f"/api/consumos/{r.json()['id']}").json()
        self.assertAlmostEqual(sum(l["coste"] for l in det["lineas"]), 10 * 0.3 + 0.5 * 2.0)  # 10 huevos + 0,5 panes
        self.assertEqual(d.post(f"/api/consumos/{det['id']}/anular", json={"motivo": "prueba"}).status_code, 200)
        self.assertEqual(d.get(f"/api/consumos/{det['id']}").json()["anulado"], 1)

    def test_recuento_fija_stock(self):
        c = cliente("rest")
        self.assertEqual(c.post("/api/recuentos", json={"fecha": "2026-09-03", "ubicacion": "RESTAURANTE",
                                                         "lineas": [{"producto": "PAN", "contado": 7}]}).status_code, 200)
        pan = next(f for f in c.get("/api/stock?ubicacion=RESTAURANTE").json() if f["producto"] == "PAN")
        self.assertEqual(pan["stock"], 7)

    def test_servicio_inexistente_rechazado(self):
        r = cliente("dir").post("/api/consumos", json={"fecha": "2026-09-02", "servicio": "inventado", "items": [{"producto": "PAN", "cantidad": 1}]})
        self.assertEqual(r.status_code, 400)

    def test_sesion_sobrevive_y_logout_la_cierra(self):
        c = cliente("dir")
        token = c.cookies.get("bm_sesion")
        otro = TestClient(A.app, cookies={"bm_sesion": token})  # como tras reiniciar el servidor
        self.assertEqual(otro.get("/api/me").json()["rol"], "direccion")
        c.post("/api/logout")
        self.assertEqual(otro.get("/api/me").status_code, 401)

    def test_escrituras_quedan_auditadas(self):
        cliente("dir").post("/api/config/copias")
        ultima = con.execute("SELECT usuario, ruta, estado FROM auditoria ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(tuple(ultima), ("DIR", "/api/config/copias", 200))


class TestPerdidas(unittest.TestCase):
    def test_merma_con_motivo_y_informe(self):
        c = cliente("dir")
        base = {"fecha": "2026-09-04", "servicio": "desayuno", "tipo": "merma", "items": [{"producto": "HUEVO", "cantidad": 3}]}
        self.assertEqual(c.post("/api/consumos", json={**base, "motivo": "inventado"}).status_code, 400)
        self.assertEqual(c.post("/api/consumos", json={**base, "motivo": "error_cocina"}).status_code, 200)
        p = c.get("/api/analisis/perdidas?desde=2026-09-01&hasta=2026-09-30").json()
        self.assertEqual([(m["motivo"], m["coste"]) for m in p["mermas"]], [("error_cocina", 0.9)])
        self.assertIn("error_cocina", c.get("/api/catalogo").json()["motivos"])

    def test_revision_de_fichas(self):
        con.execute("INSERT OR IGNORE INTO recetas(id, nombre, servicio) VALUES('vacia', 'Receta vacía', 'comida')")
        con.commit()
        f = {x["id"]: x for x in cliente("dir").get("/api/analisis/fichas").json()}
        self.assertIn("Sin ingredientes", f["vacia"]["problemas"])


class TestCompras(unittest.TestCase):
    def test_documento_adjunto_y_proveedor(self):
        c = cliente("adm")
        docs = c.get("/api/compras?desde=2026-09-01&hasta=2026-09-30").json()
        self.assertEqual([(d["documento"], d["estado"], d["importe"]) for d in docs], [("AL0001", "facturado", 50.0)])
        r = c.post("/api/compras/AL0001/adjuntos", files={"archivo": ("albaran.png", b"PNG-falso", "image/png")})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(c.post("/api/compras/AL0001/adjuntos", files={"archivo": ("virus.exe", b"x")}).status_code, 400)
        det = c.get("/api/compras/AL0001").json()
        self.assertEqual(len(det["adjuntos"]), 1)
        self.assertEqual(c.get(f"/api/adjuntos/{det['adjuntos'][0]['id']}").content, b"PNG-falso")
        ficha = {"email": "pedidos@granja.es", "dias_reparto": [0, 3], "plazo_dias": 1}
        self.assertEqual(c.put("/api/proveedores/GRANJA SL", json=ficha).status_code, 200)
        p = next(x for x in c.get("/api/proveedores").json() if x["nombre"] == "GRANJA SL")
        self.assertEqual((p["email"], p["dias"]), ("pedidos@granja.es", [0, 3]))
        self.assertEqual(cliente("rest").get("/api/compras?desde=2026-09-01&hasta=2026-09-30").status_code, 403)


if __name__ == "__main__":
    unittest.main()
