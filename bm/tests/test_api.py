"""Tests de la API: permisos por rol y flujos principales, sobre una base temporal (nunca la real)."""

import tempfile
import unittest
from pathlib import Path

from bm import db

_tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
db.DB_PATH = Path(_tmp.name) / "test.sqlite"  # antes de importar bm.app, que abre la base al importarse

from fastapi.testclient import TestClient  # noqa: E402

from bm import app as A, tpv, usuarios  # noqa: E402

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
for login, rol in (("dir", "direccion"), ("adm", "administracion"), ("rest", "jefe"), ("coc", "cocina"), ("com", "comandero")):
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
        fila = cliente("coc").get("/api/stock?ubicacion=RESTAURANTE").json()[0]  # el personal no ve costes
        self.assertNotIn("valor", fila)
        self.assertNotIn("precio", fila)

    def test_solo_direccion_gestiona_usuarios(self):
        body = {"login": "nuevo", "nombre": "Nuevo", "rol": "jefe", "password": "clave-segura"}
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

    def test_consulta_rapida_sin_precios_para_el_personal(self):
        r = cliente("coc").get("/api/consulta/PAN").json()
        self.assertEqual(r["codigo"], "PAN")
        self.assertIsNone(r["precio"])
        self.assertTrue(all(x["valor"] is None for x in r["sitios"]))
        self.assertTrue(all(x["stock"] is None for x in cliente("coc").get("/api/consulta/PAN").json()["sitios"]))  # a ciegas

    def test_dueno_ve_como_otro_perfil(self):
        d = cliente("dir")
        self.assertEqual(d.get("/api/me", headers={"X-Ver-Como": "cocina"}).json()["rol"], "cocina")
        self.assertEqual(d.get("/api/panel", headers={"X-Ver-Como": "cocina"}).status_code, 403)  # como cocina, sin panel
        fila = d.get("/api/stock?ubicacion=RESTAURANTE", headers={"X-Ver-Como": "cocina"}).json()[0]
        self.assertNotIn("stock", fila)  # y a ciegas, igual que cocina
        self.assertEqual(d.get("/api/panel").status_code, 200)
        a = cliente("adm")  # solo el dueño puede
        self.assertEqual(a.get("/api/me", headers={"X-Ver-Como": "cocina"}).json()["rol"], "administracion")

    def test_administracion_decide_lo_confidencial(self):
        jefe, adm = cliente("rest"), cliente("adm")
        perdidas = "/api/analisis/perdidas?desde=2026-09-01&hasta=2026-09-30"
        self.assertEqual(jefe.get("/api/recetas").status_code, 403)  # por defecto, recetas no
        self.assertIn("valor", jefe.get("/api/stock?ubicacion=RESTAURANTE").json()[0])  # euros sí
        self.assertEqual(jefe.put("/api/config/permisos", json={"jefe": ["recetas"]}).status_code, 403)  # no lo decide él
        r = adm.put("/api/config/permisos", json={"jefe": ["recetas", "stock"]}).json()
        self.assertEqual(r["actual"]["jefe"], ["stock", "recetas"])
        self.assertEqual(jefe.get("/api/recetas").status_code, 200)
        self.assertNotIn("valor", jefe.get("/api/stock?ubicacion=RESTAURANTE").json()[0])  # euros, ahora confidencial
        self.assertEqual(jefe.get(perdidas).status_code, 403)
        self.assertIn("recetas", jefe.get("/api/me").json()["permisos"])
        A.con.execute("DELETE FROM ajustes WHERE clave='permisos'")  # vuelta a los permisos por defecto
        A.con.commit()

    def test_jefe_pide_a_administracion_y_solo_pide_directo_lo_autorizado(self):
        jefe, adm = cliente("rest"), cliente("adm")
        sid = jefe.post("/api/solicitudes", json={"lineas": [{"producto": "PAN", "cantidad": 20}], "nota": "fin de semana"}).json()["id"]
        self.assertEqual(adm.get("/api/solicitudes").json()[0]["lineas"][0]["cantidad"], 20)
        self.assertTrue(any("de pedido del restaurante" in a["titulo"] for a in adm.get("/api/avisos").json()))
        self.assertEqual(jefe.post(f"/api/solicitudes/{sid}/responder", json={"estado": "pedida"}).status_code, 403)
        self.assertEqual(adm.post(f"/api/solicitudes/{sid}/responder", json={"estado": "rechazada"}).status_code, 400)  # di por qué
        adm.post(f"/api/solicitudes/{sid}/responder", json={"estado": "pedida", "respuesta": "pedido para el viernes"})
        self.assertEqual(jefe.get("/api/solicitudes").json()[0]["estado"], "pedida")
        prov = A.con.execute("SELECT nombre FROM proveedores LIMIT 1").fetchone()[0]
        pedido = {"proveedor": prov, "lineas": [{"producto": "PAN", "cantidad": 5}]}
        self.assertEqual(jefe.post("/api/pedidos", json=pedido).status_code, 403)  # sin autorizar
        self.assertEqual(jefe.get("/api/pedidos/directos").json()["pedidos"], [])
        adm.put("/api/config/pedido-directo", json={"rol": "jefe", "proveedores": [prov]})
        self.assertEqual(jefe.post("/api/pedidos", json=pedido).status_code, 200)
        self.assertEqual(jefe.get("/api/pedidos/directos").json()["proveedores"], [prov])
        adm.put("/api/config/pedido-directo", json={"rol": "jefe", "proveedores": []})

    def test_cocina_avisa_al_jefe_de_lo_que_queda_poco(self):
        coc, jefe, adm = cliente("coc"), cliente("rest"), cliente("adm")
        poco = coc.post("/api/solicitudes", json={"para": "jefe", "tipo": "queda_poco", "lineas": [{"producto": "PAN", "cantidad": 0}]})
        self.assertEqual(poco.status_code, 200)  # «no queda ninguno» también vale
        coc.post("/api/solicitudes", json={"para": "jefe", "tipo": "pedido", "lineas": [{"producto": "HUEVO"}]})  # sin cantidad: no es pedido
        self.assertEqual(coc.post("/api/solicitudes", json={"lineas": [{"producto": "PAN", "cantidad": 3}]}).status_code, 403)  # a admin no
        equipo = jefe.get("/api/solicitudes?de=equipo").json()
        self.assertEqual([s["tipo"] for s in equipo], ["queda_poco"])
        self.assertTrue(any("del equipo" in a["titulo"] for a in jefe.get("/api/avisos").json()))
        self.assertEqual(coc.get("/api/solicitudes?de=equipo").status_code, 403)
        self.assertEqual(jefe.post(f"/api/solicitudes/{equipo[0]['id']}/responder", json={"estado": "pedida"}).status_code, 400)
        jefe.post(f"/api/solicitudes/{equipo[0]['id']}/responder", json={"estado": "atendida", "respuesta": "pedido a administración"})
        self.assertEqual(coc.get("/api/solicitudes").json()[0]["estado"], "atendida")  # quien avisó ve cómo quedó
        mia = jefe.post("/api/solicitudes", json={"lineas": [{"producto": "PAN", "cantidad": 3}]}).json()["id"]
        self.assertEqual(jefe.post(f"/api/solicitudes/{mia}/responder", json={"estado": "pedida"}).status_code, 403)  # no se responde a sí mismo
        self.assertEqual(adm.post(f"/api/solicitudes/{mia}/responder", json={"estado": "pedida"}).status_code, 200)

    def test_cocina_apunta_merma_desde_el_movil_sin_duplicar(self):
        coc = cliente("coc")
        merma = {"fecha": "2026-08-03", "tipo": "merma", "motivo": "rotura", "ubicacion": "RESTAURANTE", "ref": "m-55",
                 "items": [{"producto": "HUEVO", "cantidad": 6}]}
        a, b = coc.post("/api/consumos", json=merma).json(), coc.post("/api/consumos", json=merma).json()
        self.assertEqual(a["id"], b["id"])  # reenvío sin cobertura
        self.assertEqual(A.con.execute("SELECT motivo FROM consumos WHERE id=?", (a["id"],)).fetchone()[0], "rotura")

    def test_comandero_solo_comandas(self):
        c = cliente("com")
        self.assertEqual(c.get("/api/comandas").status_code, 200)
        for ruta in ("/api/stock", "/api/caducidades", "/api/recepcion/pedidos", "/api/analisis/perdidas?desde=2026-09-01&hasta=2026-09-30"):
            self.assertEqual(c.get(ruta).status_code, 403, ruta)
        self.assertEqual(cliente("rest").get("/api/analisis/perdidas?desde=2026-09-01&hasta=2026-09-30").status_code, 200)  # el jefe sí

    def test_cocina_solo_cuenta_y_a_ciegas(self):
        c = cliente("coc")
        for ruta in ("/api/consumos", "/api/comandas", "/api/traslados", "/api/recuentos", "/api/productos", "/api/analisis/perdidas?desde=2026-09-01&hasta=2026-09-30"):
            self.assertEqual(c.get(ruta).status_code, 403, ruta)
        filas = c.get("/api/stock?ubicacion=RESTAURANTE").json()
        self.assertTrue(filas and all(set(f) == {"producto", "ubicacion", "nombre", "unidad", "zona"} for f in filas))  # sin cifras
        self.assertEqual(c.post("/api/recuentos", json={"fecha": "2026-09-03", "ubicacion": "RESTAURANTE",
                                                        "lineas": [{"producto": "PAN", "contado": 4}]}).status_code, 200)
        self.assertTrue(all(a["ruta"].startswith("/recuento") for a in c.get("/api/avisos").json()))

    def test_cierre_para_noray_solo_gestion(self):
        self.assertEqual(cliente("rest").get("/api/cierre/noray?mes=2026-09").status_code, 403)
        r = cliente("dir").get("/api/cierre/noray?mes=2026-09").json()
        self.assertEqual(r["fecha"], "2026-09-30")
        self.assertTrue(all({"almacen", "fisica", "calculada", "origen"} <= set(x) for x in r["lineas"]))
        self.assertEqual(cliente("rest").get("/api/cierre/recomendados?ubicacion=RESTAURANTE").status_code, 200)

    def test_recuento_reenviado_sin_cobertura_no_se_duplica(self):
        c = cliente("rest")
        cuerpo = {"fecha": "2026-09-03", "ubicacion": "RESTAURANTE", "ref": "movil-1", "lineas": [{"producto": "PAN", "contado": 5}]}
        a, b = c.post("/api/recuentos", json=cuerpo).json(), c.post("/api/recuentos", json=cuerpo).json()
        self.assertEqual(a["id"], b["id"])

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

    def test_login_se_bloquea_tras_muchos_fallos(self):
        usuarios.guardar(con, "temp", "TEMP", "jefe", "clave-segura")
        c = TestClient(A.app)
        for _ in range(A.INTENTOS_LOGIN):
            self.assertEqual(c.post("/api/login", json={"login": "temp", "password": "mal"}).status_code, 401)
        self.assertEqual(c.post("/api/login", json={"login": "temp", "password": "clave-segura"}).status_code, 429)
        self.assertEqual(c.post("/api/login", json={"login": "dir", "password": "clave-segura"}).status_code, 200)  # otros no

    def test_escrituras_quedan_auditadas(self):
        cliente("dir").post("/api/config/copias")
        ultima = con.execute("SELECT usuario, ruta, estado FROM auditoria ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(tuple(ultima), ("DIR", "/api/config/copias", 200))

    def test_food_cost_sin_ventas_sin_asignar(self):
        con.executemany("INSERT OR IGNORE INTO tpv_articulos(codigo, nombre, receta_id, precio) VALUES(?,?,?,?)",
                        [("PV1", "HUEVOS", "r1", 10.7), ("PV2", "SIN ASIGNAR", None, 10.7)])
        con.executemany("INSERT OR IGNORE INTO tpv_ventas VALUES('2026-07-01', ?, 107)", [("PV1",), ("PV2",)])
        con.commit()
        tpv.regenerar(con, ["2026-07-01"])
        r = cliente("dir").get("/api/panel?mes=2026-07").json()["actual"]
        self.assertEqual(r["ventas_sin_asignar"], 107)
        self.assertAlmostEqual(r["food_cost_pct"], round(100 * r["coste_tpv"] / 100, 1))  # sobre 100 € netos, no 200

    def test_coste_por_comensal_solo_dias_con_comensales(self):
        from bm import consumos
        consumos.registrar(con, fecha="2026-06-01", servicio="desayuno", comensales=2, items=[{"receta_id": "r1", "cantidad": 2}])
        consumos.registrar(con, fecha="2026-06-02", servicio="desayuno", items=[{"receta_id": "r1", "cantidad": 5}])  # sin comensales
        r = cliente("dir").get("/api/panel?mes=2026-06").json()["actual"]
        self.assertAlmostEqual(r["coste_por_comensal"], round(r["desayuno"] * 2 / 7 / 2, 2), places=2)

    def test_pedido_enviado_y_cerrado(self):
        c = cliente("adm")
        pid = c.post("/api/pedidos", json={"proveedor": "GRANJA SL", "entrega": "2026-09-05",
                                           "lineas": [{"producto": "HUEVO", "cantidad": 30}]}).json()["id"]
        e = {x["id"]: x for x in c.get("/api/pedidos").json()}[pid]
        self.assertEqual(e["estado"], "enviado")
        self.assertEqual(c.post(f"/api/pedidos/{pid}/cerrar", json={"estado": "anulado", "nota": "prueba"}).status_code, 200)
        self.assertEqual(cliente("rest").get("/api/pedidos").status_code, 403)

    def test_pvp_recomendado_segun_objetivo(self):
        con.execute("INSERT OR IGNORE INTO tpv_articulos(codigo, nombre, receta_id, precio, servicio) VALUES('PV9', 'HUEVOS', 'r1', 2, 'comida')")
        con.execute("INSERT OR IGNORE INTO tpv_ventas VALUES('2026-05-01', 'PV9', 20)")
        con.commit()
        p = {x["codigo"]: x for x in cliente("dir").get("/api/analisis/rentabilidad?desde=2026-05-01&hasta=2026-05-31").json()["platos"]}["PV9"]
        # coste 0,80 € (2 huevos a 0,30 + 0,1 pan a 2 €) / 30 % objetivo × 1,07 IGIC = 2,853… -> 2,90 €
        self.assertEqual((p["coste_unidad"], p["pvp_recomendado"]), (0.8, 2.9))

    def test_codigo_de_barras_se_aprende(self):
        c = cliente("rest")
        self.assertEqual(c.put("/api/codigos", json={"codigo": "8410000000001", "producto": "HUEVO"}).status_code, 200)
        self.assertEqual(c.get("/api/codigos").json()["8410000000001"], "HUEVO")
        self.assertEqual(c.put("/api/codigos", json={"codigo": "1", "producto": "NO-EXISTE"}).status_code, 400)

    def test_estado_bc_dice_desde_cuando_exportar(self):
        e = cliente("adm").get("/api/bc/estado").json()
        self.assertEqual(e["exportar_desde"], "2026-08-25")  # una semana antes del último movimiento (01/09)
        self.assertEqual(cliente("rest").get("/api/bc/estado").status_code, 403)

    def test_segunda_carpeta_de_copias(self):
        c = cliente("dir")
        self.assertEqual(c.put("/api/config/copias_extra", json={"carpeta": str(Path(_tmp.name) / "no-existe")}).status_code, 400)
        extra = Path(_tmp.name) / "nas"
        extra.mkdir()
        self.assertEqual(c.put("/api/config/copias_extra", json={"carpeta": str(extra)}).status_code, 200)
        self.assertEqual(len(list(extra.glob("bm_*.sqlite"))), 1)
        self.assertEqual(cliente("adm").put("/api/config/copias_extra", json={"carpeta": ""}).status_code, 403)
        c.put("/api/config/copias_extra", json={"carpeta": ""})


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
        # Ingrediente que no se compra desde hace años y ya no queda: la ficha usa un producto antiguo.
        con.execute("INSERT OR IGNORE INTO productos(codigo, nombre, unidad, categoria) VALUES('VIEJO', 'VINO BRIK', 'UD', '101')")
        con.execute("""INSERT OR IGNORE INTO bc_movs(n_mov, fecha, tipo, almacen, producto, cantidad, coste_total)
                       VALUES(90, '2023-11-10', 'Compra', 'ECONOMATO', 'VIEJO', 1, 1.0)""")
        con.execute("INSERT OR IGNORE INTO recetas(id, nombre, servicio) VALUES('sangria', 'Sangría', 'bebidas')")
        con.execute("INSERT OR IGNORE INTO receta_lineas VALUES('sangria', 'VIEJO', 1)")
        con.commit()
        from bm import consumos
        consumos.registrar(con, fecha="2023-12-01", servicio="bebidas", items=[{"producto": "VIEJO", "cantidad": 1}])
        f = {x["id"]: x for x in cliente("dir").get("/api/analisis/fichas").json()}
        self.assertIn("Sin ingredientes", f["vacia"]["problemas"])
        self.assertTrue(any("no se compra desde 10/11/2023" in a for a in f["sangria"]["avisos"]))


class TestCierre(unittest.TestCase):
    def test_avisos_por_perfil_y_cierre(self):
        rutas_rest = {a["ruta"] for a in cliente("rest").get("/api/avisos").json()}
        self.assertFalse(rutas_rest & {"/pedidos", "/tpv", "/bc", "/precios"})  # el personal no ve avisos de gestión
        self.assertIn("/bc", {a["ruta"] for a in cliente("dir").get("/api/avisos").json()})  # movimientos de BC antiguos
        c = cliente("dir")
        e = c.get("/api/cierre?mes=2026-09").json()
        self.assertEqual(len(e["pasos"]), 7)
        self.assertFalse(e["listo"])
        self.assertIn("resumen", c.get("/api/cierre/informe?mes=2026-09").json())
        self.assertEqual(cliente("rest").get("/api/cierre?mes=2026-09").status_code, 403)


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
