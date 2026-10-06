"""Cierre de mes guiado: qué falta para que los números del mes sean definitivos, e informe del mes."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from bm import analisis, prevision, tpv


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
    inventario_ok = []
    for ub in prevision.FB:
        f = con.execute(
            """SELECT MAX(f) FROM (SELECT MAX(fecha) f FROM recuentos WHERE anulado=0 AND ubicacion=? AND fecha>=?
               UNION ALL SELECT MAX(m.fecha) FROM bc_movs m JOIN almacenes_bc a ON a.codigo=m.almacen
               WHERE a.ubicacion=? AND m.tipo LIKE 'Ajuste%' AND m.fecha>=? AND m.fecha<=?)""",
            (ub, (fin - timedelta(days=3)).isoformat(), ub, (fin - timedelta(days=3)).isoformat(), (fin + timedelta(days=3)).isoformat())).fetchone()[0]
        inventario_ok.append((ub, f))
    paso("inventario", "Inventario de fin de mes (Economato y Restaurante)", all(f for _, f in inventario_ok),
         " · ".join(f"{ub.title()}: {_f(f) or 'sin contar'}" for ub, f in inventario_ok), "/recuento")
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
