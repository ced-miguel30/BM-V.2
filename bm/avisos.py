"""Avisos: lo que cada persona tiene pendiente hoy. BM los calcula solo; el personal solo actúa."""

from __future__ import annotations

import sqlite3
import time
from datetime import date, datetime, timedelta

from bm import analisis, cierre, inventario, pedidos, prevision, tpv

GESTION = ("direccion", "administracion")
_cache: dict = {}
TTL = 120  # ponytail: caché de 2 min; los cálculos de pedidos tardan ~1 s


def _version(con) -> tuple:
    return tuple(con.execute("""SELECT (SELECT MAX(n_mov) FROM bc_movs), (SELECT MAX(id) FROM consumos),
        (SELECT COUNT(*) FROM tpv_ventas), (SELECT MAX(id) FROM recuentos), (SELECT MAX(id) FROM caducidades),
        (SELECT COUNT(*) FROM buffet_diario), (SELECT COUNT(*) FROM tpv_articulos WHERE receta_id IS NULL AND producto IS NULL),
        (SELECT MAX(id) || COUNT(*) FROM pedidos WHERE estado IN ('enviado','incompleto'))""").fetchone())


def _f(iso: str | None) -> str | None:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else None


def avisos(con: sqlite3.Connection, rol: str) -> list[dict]:
    clave = (rol, date.today(), _version(con))
    if clave in _cache and time.time() - _cache[clave][0] < TTL:
        return _cache[clave][1]
    hoy = date.today()
    out = []

    def aviso(nivel, titulo, detalle, ruta):
        out.append({"nivel": nivel, "titulo": titulo, "detalle": detalle, "ruta": ruta})

    gestion = rol in GESTION
    if not con.execute("SELECT 1 FROM consumos WHERE fecha=? AND servicio='desayuno' AND anulado=0 LIMIT 1", (hoy.isoformat(),)).fetchone() \
            and datetime.now().hour >= 11:
        aviso("alta", "Desayuno de hoy sin registrar", "Apúntalo en Comandas de desayuno (con los comensales) o importa el Excel", "/comandas")
    if not con.execute("SELECT 1 FROM buffet_diario WHERE fecha=? LIMIT 1", (hoy.isoformat(),)).fetchone():
        aviso("media", "Buffet de hoy sin confirmar", "BM propone las cantidades según los comensales", "/buffet")
    ayer = (hoy - timedelta(days=1)).isoformat()
    if gestion and not con.execute("SELECT 1 FROM tpv_ventas WHERE fecha>=? LIMIT 1", (ayer,)).fetchone():
        aviso("media", "Ventas TPV de ayer sin subir", "Sube el PDF de 'Ventas TPV por categoría' de BC", "/tpv")
    caducan = con.execute("SELECT COUNT(*) FROM caducidades WHERE estado='activa' AND caduca<=?", ((hoy + timedelta(days=2)).isoformat(),)).fetchone()[0]
    if caducan:
        aviso("alta", f"{caducan} productos caducan en 2 días o menos", "Úsalos primero o márcalos como tirados", "/caducidades")
    rep = [x for x in prevision.reposicion(con) if x["fiable"]]
    if rep:
        aviso("media", f"Reponer {len(rep)} productos en el restaurante", "La lista de lo que hay que subir del economato está preparada", "/reponer")
    if gestion:
        fallo = con.execute("""SELECT fichero, detalle FROM entrada_log WHERE ok=0 AND cuando >= datetime('now', 'localtime', '-3 days')
                               ORDER BY id DESC LIMIT 1""").fetchone()
        if fallo:
            aviso("alta", f"No se pudo importar {fallo['fichero']}", f"{fallo['detalle']}. Está en la carpeta con_error.", "/bc")
        error_copia = inventario.ajuste(con, "copias_extra_error")
        if error_copia:
            aviso("alta", "La copia de seguridad externa ha fallado", error_copia, "/configuracion")
        ultimo_bc = con.execute("SELECT MAX(fecha) FROM bc_movs WHERE fecha<=?", (hoy.isoformat(),)).fetchone()[0]
        if not ultimo_bc or ultimo_bc < (hoy - timedelta(days=7)).isoformat():
            aviso("alta", "Movimientos de BC sin importar desde hace más de una semana",
                  f"Último movimiento: {_f(ultimo_bc) or 'ninguno'}. Sin esto los costes y el stock se quedan atrás", "/bc")
        pedidos.conciliar(con)
        lista = pedidos.listar(con, 30)
        incompletos = [x for x in lista if x["estado"] == "incompleto"]
        if incompletos:
            aviso("alta", f"{len(incompletos)} pedidos llegaron incompletos",
                  ", ".join(f"{x['proveedor']} (faltan {x['faltan']})" for x in incompletos[:3]) + ". Reclamar o cerrar", "/pedidos?vista=enviados")
        retrasados = [x for x in lista if x["retrasado"]]
        if retrasados:
            aviso("media", f"{len(retrasados)} pedidos sin albarán en BC", ", ".join(x["proveedor"] for x in retrasados[:3])
                  + ". ¿Llegaron? Si es así, falta registrarlos en BC", "/pedidos?vista=enviados")
        p = prevision.pedidos(con)
        if p["urgentes"]:
            aviso("alta", f"Comprar por fuera: {len(p['urgentes'])} productos", "Se acaban antes del próximo reparto", "/pedidos")
        hoy_pedir = [x for x in p["pedidos"] if x["llega"] <= (hoy + timedelta(days=2)).isoformat()]
        if hoy_pedir:
            aviso("media", f"Pedidos para {len(hoy_pedir)} proveedores", ", ".join(x["proveedor"] for x in hoy_pedir[:4]), "/pedidos")
        pend = tpv.pendientes(con)
        if pend:
            aviso("media", f"{len(pend)} artículos del TPV sin asignar", "No descuentan stock ni coste hasta asignarlos", "/tpv")
        subidas = analisis.subidas_en_carta(con)
        if subidas:
            aviso("media", f"{len(subidas)} ingredientes de la carta han subido más de un 10 %",
                  ", ".join(f"{x['nombre']} (+{x['variacion']} %)" for x in subidas[:3]) + ". Revisa sus platos en Rentabilidad", "/precios")
        fichas = [f for f in analisis.revision_fichas(con) if f["problemas"]]
        if fichas:
            aviso("info", f"{len(fichas)} fichas de receta a revisar", "Sus costes pueden no ser reales", "/recetas")
        mes = (hoy - timedelta(days=30)).isoformat()
        dudosos = [x for x in analisis.precios_dudosos(con) if x["fecha"] >= mes]
        if dudosos:
            aviso("info", f"{len(dudosos)} precios de compra a revisar en BC", "Probables errores de unidad o importe", "/precios")
        raros = analisis.anomalias(con)
        if raros:
            aviso("info", f"{len(raros)} productos con consumo o recuento raro", ", ".join(x["nombre"] for x in raros[:3])
                  + ". Contarlos y revisar su receta", "/cierre?vista=revisar")
    # Ya no se cuenta todo a fin de mes: solo lo fresco y lo caro, en recuentos pequeños durante el mes.
    if hoy.day >= 10:
        for ub in prevision.FB:
            n = len(cierre.recomendados(con, ub, hoy.replace(day=1).isoformat()))
            if n:
                nombre = con.execute("SELECT nombre FROM ubicaciones WHERE codigo=?", (ub,)).fetchone()[0]
                aviso("media", f"Contar {n} productos frescos o caros en {nombre}", "Poco a poco antes del cierre del mes; lo demás lo calcula BM",
                      f"/recuento?ubicacion={ub}&recomendados=1")
    if rol == "cocina":  # solo ve sus recuentos
        out = [x for x in out if x["ruta"].startswith("/recuento")]
    orden = {"alta": 0, "media": 1, "info": 2}
    out.sort(key=lambda a: orden[a["nivel"]])
    for k in [k for k in _cache if k[0] == rol]:  # una entrada por perfil
        del _cache[k]
    _cache[clave] = (time.time(), out)
    return out
