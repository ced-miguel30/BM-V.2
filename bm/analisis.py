"""Análisis para dirección: rentabilidad por plato, control real vs teórico y variación de precios."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, timedelta

from bm import consumos, costing, inventario


def _num(con, clave: str, defecto: float) -> float:
    try:
        return float(inventario.ajuste(con, clave, str(defecto)))
    except (TypeError, ValueError):
        return defecto


# Ventas que cuentan para el food cost: las de artículos asignados (o marcados "no descuenta"). Un artículo sin asignar
# vende pero no descuenta coste; si entrara, el food cost saldría más bajo de lo real.
VENTA_ASIGNADA = """SELECT v.fecha, v.importe FROM tpv_ventas v JOIN tpv_articulos a ON a.codigo=v.codigo
                    WHERE a.ignorar=1 OR a.receta_id IS NOT NULL OR a.producto IS NOT NULL"""


def igic(con) -> float:
    """IGIC incluido en los importes del TPV (Canarias, 7 % por defecto)."""
    return _num(con, "igic_ventas", 7.0) / 100


def _coste_unidad(con, a, cache: dict) -> float | None:
    """Coste teórico de UNA venta del artículo, al precio de la última compra."""
    if a["producto"]:
        pu = consumos.precio_actual(con, a["producto"])
        return None if pu is None else pu * (a["factor"] or 1)
    rid = a["receta_id"]
    if rid not in cache:
        del_dia = [r[0] for r in con.execute(
            """SELECT d.receta_id FROM recetas_dia d JOIN recetas r ON lower(r.nombre)=lower(d.etiqueta) WHERE r.id=?""", (rid,))]
        ids = del_dia or [rid]  # "Coctel del dia": media de los 7 cócteles
        costes = [consumos.coste_receta(con, i)["coste_racion"] for i in ids]
        cache[rid] = sum(costes) / len(costes) if costes else None
    return cache[rid]


def rentabilidad(con: sqlite3.Connection, desde: str, hasta: str) -> list[dict]:
    """Ingeniería de menú (Kasavana-Smith) por servicio: popularidad x margen."""
    imp = igic(con)
    cache: dict = {}
    filas = []
    for a in con.execute(
        """SELECT a.*, SUM(v.importe) importe, COUNT(DISTINCT v.fecha) dias FROM tpv_ventas v JOIN tpv_articulos a ON a.codigo=v.codigo
           WHERE v.fecha>=? AND v.fecha<=? AND a.ignorar=0 AND a.precio>0 GROUP BY a.codigo HAVING SUM(v.importe)>0""", (desde, hasta)
    ):
        uds = round(a["importe"] / a["precio"])
        if uds <= 0:
            continue
        asignado = bool(a["receta_id"] or a["producto"])
        coste = _coste_unidad(con, a, cache) if asignado else None
        pvp_neto = a["precio"] / (1 + imp)
        filas.append({
            "codigo": a["codigo"], "nombre": a["nombre"], "servicio": a["servicio"], "unidades": uds, "dias": a["dias"],
            "pvp": a["precio"], "pvp_neto": round(pvp_neto, 4), "ventas_netas": round(a["importe"] / (1 + imp), 2),
            "coste_unidad": None if coste is None else round(coste, 4),
            "margen_unidad": None if coste is None else round(pvp_neto - coste, 4),
            "food_cost": None if coste is None or not pvp_neto else round(100 * coste / pvp_neto, 1),
            "margen_total": None if coste is None else round((pvp_neto - coste) * uds, 2),
            "asignado": asignado,
        })
    # Clasificación por servicio, solo con platos que tienen coste
    por_servicio = defaultdict(list)
    for f in filas:
        if f["margen_unidad"] is not None:
            por_servicio[f["servicio"]].append(f)
    for grupo in por_servicio.values():
        total_uds = sum(f["unidades"] for f in grupo)
        umbral_pop = 0.7 / len(grupo)  # regla del 70 %
        margen_medio = sum(f["margen_unidad"] * f["unidades"] for f in grupo) / total_uds
        for f in grupo:
            popular = f["unidades"] / total_uds >= umbral_pop
            rentable = f["margen_unidad"] >= margen_medio
            f["clase"] = {(True, True): "estrella", (True, False): "caballo", (False, True): "enigma", (False, False): "perro"}[(popular, rentable)]
            f["mix"] = round(100 * f["unidades"] / total_uds, 1)
    return sorted(filas, key=lambda f: -(f["margen_total"] or 0))


def desviaciones(con: sqlite3.Connection, desde: str, hasta: str, ubicacion: str | None = None) -> list[dict]:
    """Cada recuento (de BC o BM) del periodo: lo esperado según BM vs lo contado.
    Diferencia negativa = salió más de lo registrado (consumo sin registrar, merma no anotada, robo, error)."""
    out, precios = [], {}
    for (p, u), evs in inventario._eventos(con, ubicacion=ubicacion, hasta=hasta).items():
        evs.sort(key=lambda e: (e[0], e[1]))
        s = 0.0
        for fecha, orden, tipo, v in evs:
            if orden >= 2:
                dif = v - s
                if fecha >= desde and abs(dif) > 1e-6:
                    pu = precios.setdefault((p, fecha[:7]), consumos.precio_actual(con, p, fecha))
                    out.append({"producto": p, "ubicacion": u, "fecha": fecha, "fuente": "BM" if tipo == "recuento" else "BC",
                                "esperado": round(s, 4), "contado": round(v, 4), "diferencia": round(dif, 4),
                                "valor": None if pu is None else round(dif * pu, 2)})
                s = v
            else:
                s += v
    return out


def variacion_precios(con: sqlite3.Connection, dias: int = 90) -> list[dict]:
    """Última compra frente a la media de los 90 días anteriores, con impacto mensual según el consumo de BM."""
    hoy = date.today()
    desde = (hoy - timedelta(days=dias)).isoformat()
    compras = defaultdict(list)
    for m in con.execute(
        """SELECT m.*, ABS(m.coste_total/m.cantidad) precio FROM bc_movs m
           JOIN productos p ON p.codigo=m.producto WHERE m.tipo='Compra' AND m.cantidad>0 AND m.coste_total>0
           AND p.categoria LIKE '1%' AND m.fecha<=? ORDER BY m.fecha""", (hoy.isoformat(),)
    ):
        compras[m["producto"]].append(m)
    consumo_30 = dict(con.execute(
        """SELECT l.producto, SUM(l.cantidad) FROM consumo_lineas l JOIN consumos c ON c.id=l.consumo_id
           WHERE c.anulado=0 AND c.fecha>=? GROUP BY 1""", ((hoy - timedelta(days=30)).isoformat(),)).fetchall())
    nombres = dict(con.execute("SELECT codigo, nombre FROM productos").fetchall())
    out = []
    for p, cs in compras.items():
        malos = costing.dudosos(cs)
        cs = [c for c in cs if c["n_mov"] not in malos]
        if not cs:
            continue
        ultima = cs[-1]
        if ultima["fecha"] < desde:
            continue
        ref_desde = (date.fromisoformat(ultima["fecha"]) - timedelta(days=90)).isoformat()
        previas = [c for c in cs if ref_desde <= c["fecha"] < ultima["fecha"]]
        if not previas:
            continue
        ref = sum(c["precio"] * c["cantidad"] for c in previas) / sum(c["cantidad"] for c in previas)
        if ref <= 0 or abs(ultima["precio"] - ref) / ref < 0.005:
            continue
        uso = consumo_30.get(p, 0.0)
        out.append({"producto": p, "nombre": nombres.get(p, p), "proveedor": ultima["proveedor"], "fecha": ultima["fecha"],
                    "precio": round(ultima["precio"], 4), "referencia": round(ref, 4),
                    "variacion": round(100 * (ultima["precio"] - ref) / ref, 1),
                    "consumo_30d": round(uso, 3), "impacto_mes": round((ultima["precio"] - ref) * uso, 2)})
    return sorted(out, key=lambda x: (-abs(x["impacto_mes"]), -abs(x["variacion"])))


def tendencia(con: sqlite3.Connection, meses: int = 12) -> list[dict]:
    """Coste por mes y centro, ventas TPV netas y food cost, para el panel."""
    hoy = date.today().replace(day=1)
    ini = hoy
    for _ in range(meses - 1):
        ini = (ini - timedelta(days=1)).replace(day=1)
    imp = igic(con)
    filas = defaultdict(lambda: defaultdict(float))
    for r in con.execute(
        """SELECT substr(c.fecha,1,7) mes, CASE WHEN c.tipo='merma' THEN 'mermas' ELSE c.servicio END grupo, SUM(l.coste) coste
           FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id WHERE c.anulado=0 AND c.fecha>=? GROUP BY 1,2""",
        (ini.isoformat(),)
    ):
        filas[r["mes"]][r["grupo"] or "sin_centro"] += r["coste"] or 0
    for r in con.execute(f"SELECT substr(fecha,1,7) mes, SUM(importe) FROM ({VENTA_ASIGNADA}) WHERE fecha>=? GROUP BY 1", (ini.isoformat(),)):
        filas[r[0]]["ventas_netas"] = r[1] / (1 + imp)
    for r in con.execute(
        """SELECT substr(c.fecha,1,7) mes, SUM(l.coste) FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id
           WHERE c.origen='tpv' AND c.fecha>=? GROUP BY 1""", (ini.isoformat(),)
    ):
        filas[r[0]]["coste_tpv"] = r[1] or 0
    out = []
    m = ini
    while m <= hoy:
        k = m.strftime("%Y-%m")
        f = {g: round(v, 2) for g, v in filas[k].items()}
        f["food_cost"] = round(100 * f["coste_tpv"] / f["ventas_netas"], 1) if f.get("ventas_netas") and f.get("coste_tpv") else None
        out.append({"mes": k, **f})
        m = (m + timedelta(days=32)).replace(day=1)
    while len(out) > 1 and len(out[0]) <= 2:  # sin datos todavía: no se pintan meses vacíos al principio
        out.pop(0)
    return out


def precios_dudosos(con: sqlite3.Connection) -> list[dict]:
    """Compras de BC con precio disparatado (probable error de unidad o importe). BM no las usa para costes."""
    compras = defaultdict(list)
    for m in con.execute(
        """SELECT m.*, p.nombre, p.unidad FROM bc_movs m JOIN productos p ON p.codigo=m.producto
           WHERE m.tipo='Compra' AND m.cantidad>0 AND m.coste_total>0 AND p.categoria LIKE '1%'
           ORDER BY m.producto, m.fecha"""
    ):
        compras[m["producto"]].append(m)
    out = []
    for p, cs in compras.items():
        malos = costing.dudosos(cs)
        if not malos:
            continue
        precios = sorted(abs(c["coste_total"] / c["cantidad"]) for c in cs)
        med = precios[len(precios) // 2]
        hace_un_ano = (date.today() - timedelta(days=365)).isoformat()
        for c in cs:
            if c["n_mov"] in malos and c["fecha"] >= hace_un_ano:
                out.append({"producto": p, "nombre": c["nombre"], "unidad": c["unidad"], "documento": c["documento"],
                            "fecha": c["fecha"], "proveedor": c["proveedor"], "cantidad": c["cantidad"],
                            "importe": c["coste_total"], "precio": round(abs(c["coste_total"] / c["cantidad"]), 4),
                            "precio_habitual": round(med, 4)})
    return sorted(out, key=lambda x: x["fecha"], reverse=True)


def perdidas(con: sqlite3.Connection, desde: str, hasta: str) -> dict:
    """A dónde se va el dinero que no se vende: personal, mermas por motivo, diferencias de inventario y platos que no salen."""
    def suma(sql, *a):
        return round(con.execute(sql, a).fetchone()[0] or 0.0, 2)
    base = """SELECT SUM(l.coste) FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id
              WHERE c.anulado=0 AND c.fecha>=? AND c.fecha<=?"""
    personal = suma(base + " AND c.tipo='consumo' AND c.servicio='personal'", desde, hasta)
    mermas = [{"motivo": r["motivo"] or "sin_motivo", "coste": round(r["coste"] or 0, 2), "registros": r["n"]} for r in con.execute(
        """SELECT c.motivo, SUM(l.coste) coste, COUNT(DISTINCT c.id) n FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id
           WHERE c.anulado=0 AND c.tipo='merma' AND c.fecha>=? AND c.fecha<=? GROUP BY 1 ORDER BY 2 DESC""", (desde, hasta))]
    top_mermas = [dict(r) for r in con.execute(
        """SELECT l.producto, p.nombre, p.unidad, c.motivo, ROUND(SUM(l.cantidad), 3) cantidad, ROUND(SUM(l.coste), 2) coste
           FROM consumos c JOIN consumo_lineas l ON l.consumo_id=c.id JOIN productos p ON p.codigo=l.producto
           WHERE c.anulado=0 AND c.tipo='merma' AND c.fecha>=? AND c.fecha<=? GROUP BY 1, 4 ORDER BY coste DESC LIMIT 20""", (desde, hasta))]
    dif = desviaciones(con, desde, hasta)
    no_registrado = round(sum(d["valor"] or 0 for d in dif if (d["valor"] or 0) < 0), 2)
    platos = rentabilidad(con, desde, hasta)
    perros = [p for p in platos if p.get("clase") == "perro"]
    return {"personal": personal, "mermas": mermas, "mermas_total": round(sum(m["coste"] for m in mermas), 2),
            "top_mermas": top_mermas, "diferencias_inventario": no_registrado,
            "platos_que_no_salen": sorted(perros, key=lambda p: p["unidades"])}


def revision_fichas(con: sqlite3.Connection) -> list[dict]:
    """Recetas que no tienen sentido y por qué (para revisarlas antes de fiarse de sus costes)."""
    imp = igic(con)
    pvp = {r["receta_id"]: r["precio"] for r in con.execute(
        "SELECT receta_id, MAX(precio) precio FROM tpv_articulos WHERE receta_id IS NOT NULL AND precio>0 GROUP BY receta_id")}
    usadas = {r[0] for r in con.execute(
        """SELECT DISTINCT l.receta_id FROM consumo_lineas l JOIN consumos c ON c.id=l.consumo_id
           WHERE c.anulado=0 AND l.receta_id IS NOT NULL AND c.fecha>=date('now','-90 days')""")}
    del_dia = {r[0] for r in con.execute("SELECT DISTINCT r.id FROM recetas r JOIN recetas_dia d ON lower(d.etiqueta)=lower(r.nombre)")}
    ultima_compra = dict(con.execute("SELECT producto, MAX(fecha) FROM bc_movs WHERE tipo='Compra' AND cantidad>0 GROUP BY producto").fetchall())
    hace_6m = (date.today() - timedelta(days=180)).isoformat()
    out = []
    for r in con.execute("SELECT id FROM recetas WHERE activo=1"):
        if r["id"] in del_dia:
            continue  # "Tostada/Cóctel del día": se resuelve por día, no tiene ingredientes propios
        c = consumos.coste_receta(con, r["id"])
        problemas, avisos = [], []
        if not c["lineas"]:
            problemas.append("Sin ingredientes")
        for l in c["lineas"]:
            racion = l["cantidad"] / (c["porciones"] or 1)
            u = (l["unidad"] or "").upper()
            if l["precio"] is None:
                problemas.append(f"{l['nombre']}: sin precio de compra")
            if (u in ("KG", "LT") and racion > 1.5) or (u == "UD" and racion > 12):
                problemas.append(f"{l['nombre']}: {racion:g} {u} por ración parece demasiado")
            if u in ("KG", "LT") and 0 < racion < 0.0005:
                problemas.append(f"{l['nombre']}: {racion:g} {u} por ración parece muy poco")
            uc = ultima_compra.get(l["producto"])
            if uc and uc < hace_6m and sum(x["stock"] for x in inventario.stock(con, producto=l["producto"])) <= 0:
                avisos.append(f"{l['nombre']}: no se compra desde {uc[8:10]}/{uc[5:7]}/{uc[:4]} y no queda stock; "
                              "¿la ficha usa un producto antiguo?")
        precio = pvp.get(r["id"])
        if precio and c["lineas"] and c["completo"]:
            fc = 100 * c["coste_racion"] / (precio / (1 + imp))
            minimo = 4 if c["servicio"] == "bebidas" else 12  # una copa puede estar al 6 %; un plato casi nunca
            if fc < minimo:
                problemas.append(f"Food cost {fc:.1f} % sobre un PVP de {precio:.2f} €: ¿faltan ingredientes?")
            elif fc > 60:
                problemas.append(f"Food cost {fc:.1f} % sobre un PVP de {precio:.2f} €: ¿cantidades altas o precio bajo?")
        if r["id"] not in usadas and not precio:
            avisos.append("No se ha usado en 90 días ni se vende en el TPV")
        if problemas or avisos:
            out.append({"id": r["id"], "nombre": c["nombre"], "servicio": c["servicio"], "coste_racion": c["coste_racion"],
                        "pvp": precio, "problemas": problemas, "avisos": avisos})
    return sorted(out, key=lambda x: (-len(x["problemas"]), x["nombre"]))
