"""Servicio de análisis de costes — naturaleza × servicio (Fase 4).

Ejes independientes:
- Naturaleza: Consumo | Merma | Expiración
- Servicio (solo en Consumo): Desayuno total | Comida | Cena | Bebidas independientes
  (+ desglose interno de desayuno). Merma/Expiración no se atribuyen a servicio
  sin vínculo fiable.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO

import pandas as pd

from app.core.services import analitica_consumo_service as analitica
from app.core.services.data_service import get_repository
from app.core.services.excel_format import formatear_libro
from app.core.services.formatting import formato_fecha

CATEGORIAS = ["Consumo", "Merma", "Expiración"]  # naturaleza (compat)
NATURALEZAS = CATEGORIAS
SERVICIOS_CONSUMO = ["Desayuno", "Comida", "Cena", "Bebidas"]


def _costes_naturaleza(
    inicio: date,
    fin: date,
    naturalezas: list[str] | None = None,
) -> dict[str, float]:
    repo = get_repository()
    data = repo.data
    naturalezas = naturalezas or NATURALEZAS
    resultado = {
        "Consumo": 0.0,
        "Merma": 0.0,
        "Expiración": 0.0,
    }
    if "Consumo" in naturalezas:
        # Consumo multi-servicio (no solo desayuno).
        resultado["Consumo"] = analitica.coste_servicios_excluyentes(
            inicio, fin, data=data,
        ).coste_general
    if "Merma" in naturalezas:
        resultado["Merma"] = repo.coste_merma_periodo(inicio, fin)
    if "Expiración" in naturalezas:
        resultado["Expiración"] = repo.coste_expiracion_periodo(inicio, fin)
    return {k: v for k, v in resultado.items() if k in naturalezas}


def _costes_categoria(repo, inicio: date, fin: date, categorias: list[str]) -> dict[str, float]:
    """Compatibilidad con API previa (categorías = naturalezas)."""
    return _costes_naturaleza(inicio, fin, categorias)


def resumen_periodo(inicio: date, fin: date, categorias: list[str]) -> dict:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    repo = get_repository()
    costes = _costes_naturaleza(inicio, fin, categorias)
    total = sum(costes.values())
    return {
        "costes": costes,
        "total": total,
        "total_fmt": repo.formato_precio(total),
        "desde": inicio,
        "hasta": fin,
    }


def comparar_periodos(
    a_desde: date,
    a_hasta: date,
    b_desde: date,
    b_hasta: date,
    categorias: list[str],
) -> dict:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    periodo_a = resumen_periodo(a_desde, a_hasta, categorias)
    periodo_b = resumen_periodo(b_desde, b_hasta, categorias)

    variaciones = {}
    for cat in categorias:
        va = periodo_a["costes"].get(cat, 0)
        vb = periodo_b["costes"].get(cat, 0)
        if vb > 0:
            variaciones[cat] = round(((va - vb) / vb) * 100, 1)
        elif va > 0:
            variaciones[cat] = 100.0
        else:
            variaciones[cat] = 0.0

    ta, tb = periodo_a["total"], periodo_b["total"]
    if tb > 0:
        var_total = round(((ta - tb) / tb) * 100, 1)
    elif ta > 0:
        var_total = 100.0
    else:
        var_total = 0.0

    return {
        "periodo_a": periodo_a,
        "periodo_b": periodo_b,
        "variaciones": variaciones,
        "variacion_total": var_total,
        "variacion_total_fmt": f"{var_total:+.1f}%",
    }


def datos_grafico_comparacion(comparacion: dict) -> list[dict]:
    filas = []
    for cat, valor_a in comparacion["periodo_a"]["costes"].items():
        filas.append({"periodo": "Periodo A", "categoria": cat, "coste": valor_a})
    for cat, valor_b in comparacion["periodo_b"]["costes"].items():
        filas.append({"periodo": "Periodo B", "categoria": cat, "coste": valor_b})
    return filas


def costes_consumo_por_servicio(inicio: date, fin: date) -> dict[str, float]:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    data = get_repository().data
    c = analitica.coste_servicios_excluyentes(inicio, fin, data=data)
    return {
        "Desayuno": c.desayuno_total,
        "Comida": c.comida_total,
        "Cena": c.cena_total,
        "Bebidas": c.bebidas_independientes,
        "Total": c.coste_general,
    }


def desglose_costes_desayuno(inicio: date, fin: date) -> dict[str, float]:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    data = get_repository().data
    d = analitica.desglose_desayuno(inicio, fin, data=data)
    return {
        "Desayuno": d.desayuno,
        "Bebidas en desayuno": d.bebida_en_desayuno,
        "Sin desglose histórico": d.sin_desglose_historico,
        "Desayuno total": d.desayuno_total,
    }


def resumen_ejecutivo_costes(inicio: date, fin: date) -> dict:
    """Indicadores generales del gestor de costes."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase
    from app.core.services import dashboard_service as dash
    from app.core.services import analitica_consumo_service as anal

    require_usecase(Permiso.CONSULTAR_COSTES)
    repo = get_repository()
    nat = _costes_naturaleza(inicio, fin)
    serv = costes_consumo_por_servicio(inicio, fin)
    n_reg = dash.total_registros(inicio, fin)
    consumo = nat["Consumo"]
    medio = consumo / n_reg if n_reg > 0 else 0.0
    huespedes = dash.huespedes_desayuno(inicio, fin)
    # Coste/huésped solo informativo para Desayuno, no como KPI general.
    coste_huesped_desayuno = None
    des = desglose_costes_desayuno(inicio, fin)["Desayuno total"]
    if huespedes > 0 and des > 0:
        coste_huesped_desayuno = des / huespedes

    ant_d, ant_h = anal.periodo_anterior(inicio, fin)
    nat_ant = _costes_naturaleza(ant_d, ant_h)
    var = None
    if nat_ant["Consumo"] + nat_ant["Merma"] + nat_ant["Expiración"] > 0:
        tot = sum(nat.values())
        tot_ant = sum(nat_ant.values())
        var = round(((tot - tot_ant) / tot_ant) * 100, 1) if tot_ant else (100.0 if tot else 0.0)
    elif sum(nat.values()) > 0:
        var = 100.0

    mayor = max(
        ((k, v) for k, v in serv.items() if k != "Total"),
        key=lambda x: x[1],
        default=("—", 0.0),
    )
    return {
        "naturaleza": nat,
        "servicios_consumo": serv,
        "total": sum(nat.values()),
        "total_fmt": repo.formato_precio(sum(nat.values())),
        "consumo": consumo,
        "consumo_fmt": repo.formato_precio(consumo),
        "n_registros": n_reg,
        "coste_medio_registro": medio,
        "coste_medio_registro_fmt": repo.formato_precio(medio),
        "coste_huesped_desayuno": coste_huesped_desayuno,
        "coste_huesped_desayuno_fmt": (
            repo.formato_precio(coste_huesped_desayuno)
            if coste_huesped_desayuno is not None
            else None
        ),
        "variacion_pct": var,
        "categoria_mayor": mayor[0],
        "categoria_mayor_importe": mayor[1],
        "desglose_desayuno": desglose_costes_desayuno(inicio, fin),
    }


def top_generadores_coste(
    inicio: date,
    fin: date,
    *,
    tipo_servicio: str | None = None,
    bucket: str | None = None,
    limite: int = 10,
) -> list[dict]:
    """Productos con mayor coste monetario (no ranking físico global)."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    repo = get_repository()
    filas = analitica.ranking_productos(
        inicio, fin,
        tipo_servicio=tipo_servicio,
        bucket=bucket,
        limite=limite,
        ascendente=False,
    )
    return [
        {
            "nombre": f["nombre"],
            "coste": f["coste"],
            "coste_fmt": repo.formato_precio(f["coste"]),
            "usos": f["usos"],
            "cantidad_fmt": f"{f['cantidad_normalizada']:g} {f['unidad_normalizada']}",
        }
        for f in filas
    ]


def top_recetas_coste(
    inicio: date,
    fin: date,
    *,
    tipo_servicio: str | None = None,
    categoria_receta: str | None = None,
    limite: int = 10,
) -> list[dict]:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    repo = get_repository()
    filas = analitica.ranking_recetas(
        inicio, fin,
        tipo_servicio=tipo_servicio,
        categoria_receta=categoria_receta,
        limite=limite,
        ascendente=False,
    )
    # Ordenar por coste acumulado de ingredientes (métrica monetaria).
    filas = sorted(filas, key=lambda x: x.get("coste", 0), reverse=True)[:limite]
    return [
        {
            "nombre": f["nombre"],
            "porciones": f["porciones"],
            "usos": f["usos"],
            "coste": f.get("coste", 0),
            "coste_fmt": repo.formato_precio(f.get("coste", 0)),
        }
        for f in filas
    ]


def pareto_generadores_coste(
    inicio: date,
    fin: date,
    *,
    limite: int = 12,
    umbral: float = 80.0,
) -> list[dict]:
    """Top productos por coste con % y % acumulado hasta el umbral Pareto."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    repo = get_repository()
    filas = top_generadores_coste(inicio, fin, limite=max(limite * 2, 20))
    total = sum(float(f.get("coste") or 0) for f in filas)
    if total <= 0:
        return []
    out: list[dict] = []
    acum = 0.0
    for f in filas:
        coste = float(f.get("coste") or 0)
        if coste <= 0:
            continue
        pct = round(100.0 * coste / total, 1)
        acum = round(acum + pct, 1)
        out.append(
            {
                "nombre": f.get("nombre") or "",
                "coste": coste,
                "coste_fmt": repo.formato_precio(coste),
                "pct": pct,
                "pct_acum": min(acum, 100.0),
                "usos": f.get("usos", ""),
                "cantidad_fmt": f.get("cantidad_fmt", ""),
            }
        )
        if acum >= umbral or len(out) >= limite:
            break
    return out


def alertas_periodo_costes(
    inicio: date,
    fin: date,
    *,
    umbral_var_pct: float = 10.0,
    umbral_merma_pct: float = 15.0,
    umbral_top_pct: float = 20.0,
    max_alertas: int = 5,
) -> list[dict]:
    """Alertas accionables del periodo (variación, merma, concentración)."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    res = resumen_ejecutivo_costes(inicio, fin)
    alertas: list[dict] = []
    var = res.get("variacion_pct")
    if var is not None and var >= umbral_var_pct:
        alertas.append(
            {
                "titulo": "Coste total al alza",
                "mensaje": f"Variación {var:+.1f}% vs periodo anterior (umbral {umbral_var_pct:.0f}%).",
                "severity": "danger" if var >= umbral_var_pct * 1.5 else "warning",
            }
        )
    elif var is not None and var <= -umbral_var_pct:
        alertas.append(
            {
                "titulo": "Coste total a la baja",
                "mensaje": f"Variación {var:+.1f}% vs periodo anterior.",
                "severity": "info",
            }
        )

    total = float(res.get("total") or 0)
    merma_exp = float(res["naturaleza"].get("Merma", 0)) + float(
        res["naturaleza"].get("Expiración", 0)
    )
    if total > 0:
        merma_pct = round(100.0 * merma_exp / total, 1)
        if merma_pct >= umbral_merma_pct:
            alertas.append(
                {
                    "titulo": "Merma + expiración elevada",
                    "mensaje": (
                        f"Representa {merma_pct:.1f}% del coste total "
                        f"(umbral {umbral_merma_pct:.0f}%)."
                    ),
                    "severity": "danger" if merma_pct >= umbral_merma_pct * 1.3 else "warning",
                }
            )

    tops = top_generadores_coste(inicio, fin, limite=1)
    consumo = float(res.get("consumo") or 0)
    if tops and consumo > 0:
        top = tops[0]
        peso = round(100.0 * float(top.get("coste") or 0) / consumo, 1)
        if peso >= umbral_top_pct:
            alertas.append(
                {
                    "titulo": f"Concentración: {top.get('nombre') or 'producto'}",
                    "mensaje": (
                        f"Aporta {peso:.1f}% del coste de consumo "
                        f"({top.get('coste_fmt') or ''})."
                    ),
                    "severity": "warning",
                }
            )

    mayor = res.get("categoria_mayor") or "—"
    mayor_imp = float(res.get("categoria_mayor_importe") or 0)
    if mayor != "—" and mayor_imp > 0:
        alertas.append(
            {
                "titulo": f"Mayor servicio: {mayor}",
                "mensaje": f"Coste de consumo {get_repository().formato_precio(mayor_imp)} en el periodo.",
                "severity": "info",
            }
        )

    return alertas[:max_alertas]


def alertas_periodo_consumo(
    inicio: date,
    fin: date,
    *,
    umbral_var_pct: float = 10.0,
    umbral_cat_pct: float = 40.0,
    max_alertas: int = 5,
) -> list[dict]:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    res = analitica.resumen_consumo(inicio, fin)
    alertas: list[dict] = []
    var = res.get("variacion_pct")
    if var is not None and abs(var) >= umbral_var_pct:
        alertas.append(
            {
                "titulo": "Consumo vs periodo anterior",
                "mensaje": f"Variación {var:+.1f}%.",
                "severity": "danger"
                if var >= umbral_var_pct
                else ("info" if var < 0 else "warning"),
            }
        )
    total = float(res.get("coste_consumo") or 0)
    if total > 0:
        for cat, imp in (res.get("por_categoria") or {}).items():
            pct = round(100.0 * float(imp or 0) / total, 1)
            if pct >= umbral_cat_pct:
                alertas.append(
                    {
                        "titulo": f"Dominancia {cat}",
                        "mensaje": f"{pct:.1f}% del coste de consumo en {cat}.",
                        "severity": "warning",
                    }
                )
                break
    return alertas[:max_alertas]


def alertas_periodo_merma(
    inicio: date,
    fin: date,
    *,
    umbral_var_pct: float = 10.0,
    umbral_exp_pct: float = 35.0,
    max_alertas: int = 5,
) -> list[dict]:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase
    from app.core.services import merma_analisis_service as merma_an

    require_usecase(Permiso.CONSULTAR_COSTES)

    res = merma_an.resumen_merma(inicio, fin)
    alertas: list[dict] = []
    ant_d, ant_h = analitica.periodo_anterior(inicio, fin)
    ant = merma_an.resumen_merma(ant_d, ant_h)
    tot = float(res.get("total") or 0)
    tot_ant = float(ant.get("total") or 0)
    var = None
    if tot_ant > 0:
        var = round(((tot - tot_ant) / tot_ant) * 100.0, 1)
    elif tot > 0:
        var = 100.0
    if var is not None and abs(var) >= umbral_var_pct:
        alertas.append(
            {
                "titulo": "Merma vs periodo anterior",
                "mensaje": f"Variación {var:+.1f}%.",
                "severity": "danger" if var >= umbral_var_pct else "info",
            }
        )
    if tot > 0:
        exp_pct = round(100.0 * float(res.get("expiracion") or 0) / tot, 1)
        if exp_pct >= umbral_exp_pct:
            alertas.append(
                {
                    "titulo": "Expiración elevada",
                    "mensaje": f"La expiración es {exp_pct:.1f}% de la merma total.",
                    "severity": "warning",
                }
            )
    return alertas[:max_alertas]


def evolucion_coste_naturaleza(inicio: date, fin: date) -> list[dict]:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    from datetime import timedelta

    if inicio > fin:
        inicio, fin = fin, inicio
    filas = []
    cursor = inicio
    while cursor <= fin:
        nat = _costes_naturaleza(cursor, cursor)
        filas.append({
            "fecha": cursor,
            "Consumo": nat.get("Consumo", 0),
            "Merma": nat.get("Merma", 0),
            "Expiración": nat.get("Expiración", 0),
        })
        cursor += timedelta(days=1)
    return filas


def exportar_costes_excel(
    a_desde: date,
    a_hasta: date,
    b_desde: date,
    b_hasta: date,
    categorias: list[str],
) -> bytes:
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    comparacion = comparar_periodos(a_desde, a_hasta, b_desde, b_hasta, categorias)
    pa = comparacion["periodo_a"]
    pb = comparacion["periodo_b"]
    serv_a = costes_consumo_por_servicio(a_desde, a_hasta)
    serv_b = costes_consumo_por_servicio(b_desde, b_hasta)

    resumen_df = pd.DataFrame([
        {
            "Naturaleza": cat,
            "Periodo A": pa["costes"].get(cat, 0),
            "Periodo B": pb["costes"].get(cat, 0),
            "Variación %": comparacion["variaciones"].get(cat, 0),
        }
        for cat in categorias
    ])
    resumen_df.loc[len(resumen_df)] = {
        "Naturaleza": "TOTAL",
        "Periodo A": pa["total"],
        "Periodo B": pb["total"],
        "Variación %": comparacion["variacion_total"],
    }

    servicios_df = pd.DataFrame([
        {
            "Servicio (solo Consumo)": nombre,
            "Periodo A": serv_a.get(nombre, 0),
            "Periodo B": serv_b.get(nombre, 0),
        }
        for nombre in SERVICIOS_CONSUMO
    ])

    meta_df = pd.DataFrame([
        {"Campo": "Periodo A desde", "Valor": formato_fecha(a_desde)},
        {"Campo": "Periodo A hasta", "Valor": formato_fecha(a_hasta)},
        {"Campo": "Periodo B desde", "Valor": formato_fecha(b_desde)},
        {"Campo": "Periodo B hasta", "Valor": formato_fecha(b_hasta)},
        {"Campo": "Naturalezas", "Valor": ", ".join(categorias)},
        {
            "Campo": "Nota",
            "Valor": "Merma/Expiración no se atribuyen a servicio sin vínculo fiable.",
        },
    ])

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        meta_df.to_excel(writer, sheet_name="Periodos", index=False)
        resumen_df.to_excel(writer, sheet_name="Comparación", index=False)
        servicios_df.to_excel(writer, sheet_name="Consumo por servicio", index=False)
        formatear_libro(writer, [
            ("Periodos", "TablaCostesPeriodos", False),
            ("Comparación", "TablaCostesComparacion", True),
            ("Consumo por servicio", "TablaCostesServicios", True),
        ])

    return buffer.getvalue()


def exportar_coste_por_producto_excel(desde: date, hasta: date) -> bytes:
    """Informe completo de coste por producto en el periodo (sin límite de filas)."""
    from app.core.auth.permissions import Permiso
    from app.core.auth.usecase_guard import require_usecase

    require_usecase(Permiso.CONSULTAR_COSTES)

    filas = analitica.ranking_productos(desde, hasta, limite=None)
    total = sum(float(f.get("coste") or 0) for f in filas)
    rows: list[dict] = []
    for f in filas:
        coste = float(f.get("coste") or 0)
        rows.append(
            {
                "Producto": f.get("nombre") or "",
                "Cantidad": f.get("cantidad_normalizada") or 0,
                "Unidad": f.get("unidad_normalizada") or "",
                "Coste (€)": round(coste, 2),
                "% del total": round((coste / total) * 100, 2) if total else 0.0,
                "Usos": f.get("usos") or 0,
            }
        )

    meta_df = pd.DataFrame(
        [
            {"Campo": "Desde", "Valor": formato_fecha(desde)},
            {"Campo": "Hasta", "Valor": formato_fecha(hasta)},
            {"Campo": "Productos", "Valor": len(rows)},
            {"Campo": "Coste total (€)", "Valor": round(total, 2)},
        ]
    )
    detalle_df = pd.DataFrame(rows)

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        meta_df.to_excel(writer, sheet_name="Periodo", index=False)
        detalle_df.to_excel(writer, sheet_name="Coste por producto", index=False)
        formatear_libro(
            writer,
            [
                ("Periodo", "TablaCostesPeriodos", False),
                ("Coste por producto", "TablaCosteProducto", True),
            ],
        )
    return buffer.getvalue()
