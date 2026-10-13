"""Cierre de mes guiado: qué falta para que los números del mes sean definitivos, e informe del mes."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from bm import analisis, consumos, inventario, prevision, tpv

CARO = 0.5        # caro = los pocos productos que juntos suman la mitad del valor de la ubicación (análisis ABC)
FRESCO = 4        # compras en 60 días: se compra casi cada semana → perecedero


def _limites(mes: str) -> tuple[date, date]:
    y, m = map(int, mes.split("-"))
    ini = date(y, m, 1)
    return ini, (ini + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def _f(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else ""


def _dias(fechas: list[str]) -> str:
    if not fechas:
        return "Todos los días"
    return f"Faltan {len(fechas)} días" + (f": {', '.join(_f(d)[:5] for d in fechas[:8])}{'…' if len(fechas) > 8 else ''}" if fechas else "")


def recomendados(con: sqlite3.Connection, ubicacion: str, desde: str, hasta: str | None = None) -> list[dict]:
    """Lo que conviene contar a mano porque la estimación de BM no basta: fresco (se compra casi cada semana) o caro,
    y sin contar desde `desde`. El resto puede ir a Noray con lo que calcula BM."""
    hasta = hasta or date.today().isoformat()
    ini60 = (date.fromisoformat(hasta) - timedelta(days=60)).isoformat()
    compras = dict(con.execute("SELECT producto, COUNT(DISTINCT fecha) FROM bc_movs WHERE tipo='Compra' AND fecha>? AND fecha<=? GROUP BY 1",
                               (ini60, hasta)).fetchall())
    caduca = {r[0] for r in con.execute("SELECT DISTINCT producto FROM caducidades WHERE estado='activa'")}
    # Lo que no sale en 60 días (estanterías, menaje guardado...) no cambia: BM ya sabe cuánto hay.
    movidos = {r[0] for r in con.execute(
        """SELECT m.producto FROM bc_movs m JOIN almacenes_bc a ON a.codigo=m.almacen
           WHERE a.ubicacion=? AND m.cantidad<0 AND m.fecha>? AND m.fecha<=?
           UNION SELECT l.producto FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id
           WHERE c.anulado=0 AND c.fecha>? AND c.fecha<=?""", (ubicacion, ini60, hasta, ini60, hasta))}
    info = {r["codigo"]: r for r in con.execute("SELECT codigo, nombre, unidad FROM productos")}
    filas = [s for s in inventario.stock(con, ubicacion, hasta=hasta) if s["stock"] > 1e-6]
    for s in filas:
        pu = consumos.precio_actual(con, s["producto"], hasta)
        s["valor"] = None if pu is None else round(s["stock"] * pu, 2)
    caros, acumulado = set(), 0.0
    total = sum(s["valor"] or 0 for s in filas)
    for s in sorted(filas, key=lambda s: -(s["valor"] or 0)):
        if acumulado >= CARO * total:
            break
        caros.add(s["producto"])
        acumulado += s["valor"] or 0
    out = []
    for s in filas:
        if (s["ultimo_recuento"] or "") >= desde or s["producto"] not in movidos:
            continue
        valor = s["valor"]
        motivos = []
        if compras.get(s["producto"], 0) >= FRESCO or s["producto"] in caduca:
            motivos.append("fresco")
        if s["producto"] in caros:
            motivos.append("caro")
        if motivos:
            p = info.get(s["producto"])
            out.append({"producto": s["producto"], "nombre": p["nombre"] if p else s["producto"], "unidad": p["unidad"] if p else None,
                        "stock": s["stock"], "valor": valor, "motivos": motivos, "ultimo_recuento": s["ultimo_recuento"]})
    return sorted(out, key=lambda x: -(x["valor"] or 0))


def estado(con: sqlite3.Connection, mes: str) -> dict:
    ini, fin = _limites(mes)
    corte = min(fin, date.today() - timedelta(days=1))
    dias = [ini + timedelta(days=i) for i in range((corte - ini).days + 1)]
    pasos = []

    def paso(clave, titulo, ok, detalle, ruta, obligatorio=True):
        pasos.append({"clave": clave, "titulo": titulo, "ok": bool(ok), "detalle": detalle, "ruta": ruta, "obligatorio": obligatorio})

    ultimo_bc = con.execute("SELECT MAX(fecha) FROM bc_movs WHERE fecha<=?", (date.today().isoformat(),)).fetchone()[0] or ""
    paso("bc", "Movimientos de BC importados hasta fin de mes", ultimo_bc >= corte.isoformat(),
         f"Último movimiento importado: {_f(ultimo_bc) or 'ninguno'}", "/bc")
    # Ya no hace falta contarlo todo: basta con lo fresco y lo caro; el resto lo calcula BM (ver bm/noray.py).
    faltan = {ub: len(recomendados(con, ub, ini.isoformat(), corte.isoformat())) for ub in prevision.FB}
    paso("inventario", "Productos frescos y caros contados este mes", not any(faltan.values()),
         " · ".join(f"{ub.title()}: {f'faltan {n}' if n else 'hecho'}" for ub, n in faltan.items()), "/cierre?vista=contar")
    con_tpv = {r[0] for r in con.execute("SELECT DISTINCT fecha FROM tpv_ventas WHERE fecha>=? AND fecha<=?", (ini.isoformat(), corte.isoformat()))}
    sin_tpv = [d.isoformat() for d in dias if d.isoformat() not in con_tpv]
    paso("tpv", "Ventas TPV de todos los días", not sin_tpv, _dias(sin_tpv), "/tpv")
    con_des = {r[0] for r in con.execute(
        "SELECT DISTINCT fecha FROM consumos WHERE anulado=0 AND servicio='desayuno' AND fecha>=? AND fecha<=?", (ini.isoformat(), corte.isoformat()))}
    sin_des = [d.isoformat() for d in dias if d.isoformat() not in con_des]
    paso("desayuno", "Desayuno registrado todos los días", not sin_des, _dias(sin_des), "/comandas")
    vendidos = {r[0] for r in con.execute("SELECT DISTINCT codigo FROM tpv_ventas WHERE fecha>=? AND fecha<=?", (ini.isoformat(), fin.isoformat()))}
    pend = [p for p in tpv.pendientes(con) if p["codigo"] in vendidos]  # solo lo vendido este mes afecta a sus números
    paso("asignar", "Artículos del TPV vendidos este mes asignados", not pend, f"{len(pend)} sin asignar", "/tpv")
    malos = [x for x in analisis.precios_dudosos(con) if ini.isoformat() <= x["fecha"] <= fin.isoformat()]
    paso("precios", "Precios de compra del mes revisados en BC", not malos, f"{len(malos)} precios sospechosos", "/precios", obligatorio=False)
    fichas = [f for f in analisis.revision_fichas(con) if f["problemas"]]
    paso("fichas", "Fichas de receta coherentes", not fichas, f"{len(fichas)} fichas con errores", "/recetas", obligatorio=False)
    listos = all(p["ok"] for p in pasos if p["obligatorio"])
    return {"mes": mes, "desde": ini.isoformat(), "hasta": fin.isoformat(), "pasos": pasos, "listo": listos}
