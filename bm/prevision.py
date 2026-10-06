"""Previsión de consumo, stock estimado, propuestas de pedido y de reposición.

Para cada producto y ubicación (o grupo de ubicaciones):
  ritmo real     = lo que salió entre los dos últimos inventarios / días (incluye lo no registrado en BM)
  ritmo BM       = consumo registrado en BM los últimos 28 días / 28
  ritmo          = el mayor de los dos (no quedarse corto si no se registra todo)
  stock estimado = último inventario + entradas − max(consumo registrado, ritmo real × días) desde entonces
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import date, timedelta

from bm import compras, consumos, inventario

FB = ("ECONOMATO", "RESTAURANTE")  # ubicaciones físicas de alimentación y bebida


def _num(con, clave, defecto):
    try:
        return float(inventario.ajuste(con, clave, str(defecto)))
    except (TypeError, ValueError):
        return defecto


def analizar(con: sqlite3.Connection, grupos: dict[str, tuple], hoy: date | None = None) -> dict:
    """grupos: {"HOTEL": ("ECONOMATO","RESTAURANTE"), "RESTAURANTE": ("RESTAURANTE",)} -> {(producto, grupo): datos}"""
    hoy = hoy or date.today()
    hace28 = (hoy - timedelta(days=28)).isoformat()
    evs = inventario._eventos(con, hasta=hoy.isoformat())
    por_producto = defaultdict(dict)
    for (p, u), e in evs.items():
        por_producto[p][u] = e
    out = {}
    for p, locs in por_producto.items():
        for g, ubs in grupos.items():
            fusion = sorted(((f, o, t, v, u) for u in ubs for (f, o, t, v) in locs.get(u, [])), key=lambda x: (x[0], x[1]))
            if not fusion:
                continue
            s = defaultdict(float)
            ancla = None              # (fecha, total)
            seg_in = seg_bm = 0.0     # desde el último inventario
            ritmo_real, reg28 = None, 0.0
            i = 0
            while i < len(fusion):
                fecha = fusion[i][0]
                hubo_ancla = False
                while i < len(fusion) and fusion[i][0] == fecha:
                    _, o, _, v, u = fusion[i]
                    if o >= 2:
                        s[u], hubo_ancla = v, True
                    else:
                        s[u] += v
                        if o == 0:
                            seg_in += v
                        else:
                            seg_bm += -v
                            if fecha >= hace28:
                                reg28 += -v
                    i += 1
                if hubo_ancla:
                    total = sum(s.values())
                    if ancla:
                        dias = (date.fromisoformat(fecha) - date.fromisoformat(ancla[0])).days
                        salida = ancla[1] + seg_in - total
                        if dias >= 7 and salida > 0:
                            ritmo_real = salida / dias
                    ancla, seg_in, seg_bm = (fecha, total), 0.0, 0.0
            ritmo = max(ritmo_real or 0.0, reg28 / 28)
            teorico = sum(s.values())
            estimado = teorico
            if ancla:
                dias_desde = (hoy - date.fromisoformat(ancla[0])).days
                estimado = ancla[1] + seg_in - max(seg_bm, (ritmo_real or 0.0) * dias_desde)
            out[(p, g)] = {"teorico": round(teorico, 3), "estimado": round(max(estimado, 0.0), 3), "ritmo": round(ritmo, 4),
                           "ritmo_real": None if ritmo_real is None else round(ritmo_real, 4), "ritmo_bm": round(reg28 / 28, 4),
                           "ultimo_inventario": ancla[0] if ancla else None}
    return out


def _compras_recientes(con) -> dict:
    """Por producto, en una sola consulta: proveedor habitual (el último), lote habitual (mediana) y última compra."""
    out = {}
    for r in con.execute(
        """SELECT producto, proveedor, cantidad, fecha FROM bc_movs WHERE tipo='Compra' AND cantidad>0
           AND fecha>=date('now','-365 days') AND fecha<=date('now') ORDER BY producto, fecha, n_mov"""
    ):
        d = out.setdefault(r["producto"], {"cantidades": [], "proveedor": None, "ultima": None})
        d["cantidades"].append(r["cantidad"])
        if r["proveedor"]:
            d["proveedor"] = r["proveedor"]
        d["ultima"] = r["fecha"]
    for d in out.values():
        qs = sorted(d.pop("cantidades"))
        d["lote"] = qs[len(qs) // 2]
    return out


def _redondear(q: float, lote: float | None, unidad: str | None) -> float:
    if q <= 0:
        return 0.0
    if lote and lote > 0:
        return math.ceil(q / lote - 1e-9) * lote
    return math.ceil(q) if (unidad or "").upper() in ("UD", "PQ", "CA", "BT", "BO") else round(q, 2)


def pedidos(con: sqlite3.Connection, hoy: date | None = None) -> dict:
    """Propuesta de pedido por proveedor para cubrir hasta la entrega siguiente, y lo que hay que comprar por fuera."""
    hoy = hoy or date.today()
    seguridad = _num(con, "dias_seguridad", 2)
    datos = analizar(con, {"HOTEL": FB}, hoy)
    info = {r["codigo"]: r for r in con.execute("SELECT codigo, nombre, unidad, categoria FROM productos")}
    params = {r["producto"]: r for r in con.execute("SELECT * FROM parametros_producto")}
    recientes = _compras_recientes(con)
    hace120 = (hoy - timedelta(days=120)).isoformat()
    entregas: dict = {}

    def entrega(prov, desde):
        if (prov, desde) not in entregas:
            entregas[(prov, desde)] = compras.proxima_entrega(con, prov, desde)
        return entregas[(prov, desde)]

    por_prov, urgentes = defaultdict(list), []
    for (p, _), d in datos.items():
        prod, par, rc = info.get(p), params.get(p), recientes.get(p, {})
        if not prod or not (prod["categoria"] or "").startswith("1") or d["ritmo"] <= 0 or (par and par["no_pedir"]):
            continue
        if (rc.get("ultima") or "") < hace120 and d["ritmo_bm"] <= 0:
            continue  # ni se compra ni se consume últimamente: no se propone
        prov = rc.get("proveedor") or "Sin proveedor"
        d1 = entrega(prov, hoy) or hoy + timedelta(days=2)
        d2 = entrega(prov, d1) or d1 + timedelta(days=7)
        colchon = par["stock_minimo"] if par and par["stock_minimo"] is not None else d["ritmo"] * seguridad
        hasta_d1 = d["ritmo"] * (d1 - hoy).days
        necesario = d["ritmo"] * (d2 - hoy).days + colchon
        lote = (par["lote"] if par and par["lote"] else None) or rc.get("lote")
        pedir = _redondear(necesario - d["estimado"], lote, prod["unidad"])
        linea = {"producto": p, "nombre": prod["nombre"], "unidad": prod["unidad"], "stock": d["estimado"],
                 "ritmo": d["ritmo"], "dias_quedan": round(d["estimado"] / d["ritmo"], 1), "pedir": pedir, "lote": lote,
                 "precio": consumos.precio_actual(con, p), "llega": d1.isoformat(), "inventario": d["ultimo_inventario"]}
        if d["estimado"] < hasta_d1:
            urgentes.append({**linea, "proveedor": prov, "falta": _redondear(hasta_d1 + colchon - d["estimado"], None, prod["unidad"])})
        if pedir > 0:
            por_prov[prov].append(linea)
    provs = {r["nombre"]: r for r in con.execute("SELECT * FROM proveedores")}
    lista = []
    for prov, lineas in por_prov.items():
        importe = sum(l["pedir"] * (l["precio"] or 0) for l in lineas)
        pv = provs.get(prov)
        lista.append({"proveedor": prov, "email": pv["email"] if pv else None, "telefono": pv["telefono"] if pv else None,
                      "pedido_minimo": pv["pedido_minimo"] if pv else None, "llega": min(l["llega"] for l in lineas),
                      "importe": round(importe, 2), "lineas": sorted(lineas, key=lambda l: l["dias_quedan"])})
    return {"pedidos": sorted(lista, key=lambda x: (x["llega"], -x["importe"])),
            "urgentes": sorted(urgentes, key=lambda x: x["dias_quedan"])}


def reposicion(con: sqlite3.Connection, hoy: date | None = None) -> list[dict]:
    """Qué subir del economato a Restaurante y cocina (productos que normalmente se trasladan)."""
    hoy = hoy or date.today()
    dias = _num(con, "dias_reposicion", 3)
    subidas = defaultdict(list)  # lo que se suele subir de cada vez (unidad de reposición)
    for r in con.execute(
        """SELECT producto, -cantidad FROM bc_movs WHERE tipo='Transferencia' AND almacen='ECONOMATO' AND cantidad<0
           AND fecha>=?""", ((hoy - timedelta(days=180)).isoformat(),)):
        subidas[r[0]].append(r[1])
    trasladados = set(subidas)
    datos = analizar(con, {"RESTAURANTE": ("RESTAURANTE",), "ECONOMATO": ("ECONOMATO",)}, hoy)
    info = {r["codigo"]: r for r in con.execute("SELECT codigo, nombre, unidad FROM productos")}
    params = {r["producto"]: r for r in con.execute("SELECT * FROM parametros_producto")}
    out = []
    for p in trasladados:
        r, e = datos.get((p, "RESTAURANTE")), datos.get((p, "ECONOMATO"))
        if not r or not e or e["estimado"] <= 0:
            continue
        par = params.get(p)
        minimo = par["minimo_restaurante"] if par and par["minimo_restaurante"] is not None else r["ritmo"] * 1
        if r["ritmo"] <= 0 and minimo <= 0:
            continue
        if r["estimado"] >= max(minimo, 1e-9):
            continue
        objetivo = max(r["ritmo"] * dias, minimo)
        qs = sorted(subidas[p])
        paso = qs[len(qs) // 2]  # p. ej. una garrafa de 5 L, una caja de 12
        subir = min(e["estimado"], _redondear(objetivo - r["estimado"], paso, info[p]["unidad"]))
        if (info[p]["unidad"] or "").upper() in ("UD", "PQ", "CA", "BT", "BO"):
            subir = math.floor(subir)  # no se sube media botella
        if subir > 0:
            out.append({"producto": p, "nombre": info[p]["nombre"], "unidad": info[p]["unidad"], "restaurante": r["estimado"], "paso": paso,
                        "minimo": round(minimo, 2), "economato": e["estimado"], "ritmo": r["ritmo"], "subir": subir})
    return sorted(out, key=lambda x: x["restaurante"] / max(x["minimo"], 1e-9))


def favoritos(con: sqlite3.Connection, hoy: date | None = None) -> dict:
    """Lo más vendido en TPV (unidades/día, tendencia) y comensales de desayuno previstos por día de la semana."""
    hoy = hoy or date.today()
    h28, h56 = (hoy - timedelta(days=28)).isoformat(), (hoy - timedelta(days=56)).isoformat()
    ventas = defaultdict(lambda: [0.0, 0.0])
    for v in con.execute(
        """SELECT a.codigo, a.nombre, a.servicio, a.precio, v.fecha, v.importe FROM tpv_ventas v JOIN tpv_articulos a ON a.codigo=v.codigo
           WHERE v.fecha>=? AND a.precio>0 AND a.ignorar=0""", (h56,)
    ):
        ventas[(v["codigo"], v["nombre"], v["servicio"])][0 if v["fecha"] >= h28 else 1] += round(v["importe"] / v["precio"])
    top = [{"codigo": c, "nombre": n, "servicio": s, "uds_28d": int(a), "por_dia": round(a / 28, 1),
            "tendencia": None if not b else round(100 * (a - b) / b)} for (c, n, s), (a, b) in ventas.items() if a > 0]
    com = defaultdict(list)
    for r in con.execute(
        """SELECT fecha, SUM(comensales) n FROM consumos WHERE anulado=0 AND servicio='desayuno' AND comensales>0
           AND fecha>=? GROUP BY fecha""", (h56,)
    ):
        com[date.fromisoformat(r["fecha"]).weekday()].append(r["n"])
    prevision = []
    for i in range(1, 8):
        d = hoy + timedelta(days=i)
        xs = com.get(d.weekday()) or [n for v in com.values() for n in v]
        prevision.append({"fecha": d.isoformat(), "comensales": round(sum(xs) / len(xs)) if xs else None})
    return {"top": sorted(top, key=lambda x: -x["uds_28d"]), "comensales": prevision}
