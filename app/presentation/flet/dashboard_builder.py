"""Construye el panel ejecutivo del Dashboard Admin (vía servicios)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.auth.permissions import AuthorizationError, Permiso
from app.core.auth.session import session_tiene_permiso
from app.core.models import EstadoAlerta
from app.core.services import analitica_consumo_service as analitica
from app.core.services import costes_service
from app.core.services import dashboard_service as dash
from app.core.services import merma_analisis_service as merma_an
from app.core.services.alert_service import alertas_operativas_abiertas, sincronizar_alertas
from app.core.services.data_service import get_repository
from app.presentation.flet.analisis_viewmodels import (
    BarItemVM,
    ChartSeriesVM,
    MetricVM,
    RankingBlockVM,
    RankingRowVM,
)


@dataclass(frozen=True)
class DashboardAlertaVM:
    titulo: str
    detalle: str
    severidad: str  # info|warning|error|success
    destino: str = ""


@dataclass(frozen=True)
class DashboardPanelVM:
    """Panel de inicio. Valores económicos ya formateados (strings)."""

    saludo: str = ""
    periodo_label: str = ""
    metrics: tuple[MetricVM, ...] = ()
    por_servicio: tuple[MetricVM, ...] = ()
    chart_naturaleza: tuple[BarItemVM, ...] = ()
    chart_evolucion: ChartSeriesVM | None = None
    rankings: tuple[RankingBlockVM, ...] = ()
    alertas: tuple[DashboardAlertaVM, ...] = ()
    puede_ver_economia: bool = False
    aviso: str = ""


def _fmt_var(pct: float | None) -> str:
    if pct is None:
        return "Sin periodo anterior"
    signo = "+" if pct > 0 else ""
    return f"{signo}{pct:.1f}% vs periodo anterior"


def _bars_nat(dist: list[dict], repo) -> tuple[BarItemVM, ...]:
    out: list[BarItemVM] = []
    for d in dist:
        imp = float(d.get("importe") or 0)
        out.append(
            BarItemVM(
                categoria=str(d.get("categoria") or ""),
                importe=imp,
                porcentaje=float(d.get("porcentaje") or 0),
                importe_fmt=repo.formato_precio(imp),
            )
        )
    return tuple(out)


def build_dashboard_panel(
    *,
    nombre_usuario: str,
    periodo_op: str = "Este mes",
) -> DashboardPanelVM:
    saludo = f"Bienvenido, {nombre_usuario or 'Usuario'}"
    puede = session_tiene_permiso(Permiso.CONSULTAR_COSTES)
    try:
        periodo = dash.resolver_periodo(periodo_op)
    except Exception:  # noqa: BLE001
        return DashboardPanelVM(
            saludo=saludo,
            periodo_label=periodo_op,
            aviso="No se pudo resolver el periodo.",
        )

    desde, hasta = periodo.desde, periodo.hasta
    label = f"{periodo.etiqueta} · {desde.isoformat()} — {hasta.isoformat()}"

    try:
        sincronizar_alertas()
    except Exception:  # noqa: BLE001
        pass

    repo = get_repository()
    data = repo.data
    alertas_vm: list[DashboardAlertaVM] = []

    if repo.desayuno_registrado_hoy():
        alertas_vm.append(
            DashboardAlertaVM(
                "Desayuno de hoy registrado",
                "El servicio de desayuno ya tiene registro hoy.",
                "success",
            )
        )
    else:
        alertas_vm.append(
            DashboardAlertaVM(
                "Falta registro de desayuno",
                "No hay desayuno registrado para hoy.",
                "warning",
                destino="analisis",
            )
        )

    try:
        abiertas = alertas_operativas_abiertas(data)
        n_pend = sum(
            1
            for a in abiertas
            if (getattr(a, "estado", None) or EstadoAlerta.PENDIENTE.value)
            == EstadoAlerta.PENDIENTE.value
        )
        if abiertas:
            alertas_vm.append(
                DashboardAlertaVM(
                    f"{len(abiertas)} alertas operativas",
                    f"{n_pend} pendiente(s). Revise stock y caducidades.",
                    "warning" if n_pend else "info",
                    destino="productos",
                )
            )
    except Exception:  # noqa: BLE001
        pass

    if not puede:
        n_reg = dash.total_registros(desde, hasta, data=data)
        return DashboardPanelVM(
            saludo=saludo,
            periodo_label=label,
            metrics=(
                MetricVM("Servicios registrados", str(n_reg), periodo.etiqueta),
            ),
            alertas=tuple(alertas_vm),
            puede_ver_economia=False,
            aviso="Sin permiso CONSULTAR_COSTES: métricas económicas ocultas.",
        )

    try:
        res = costes_service.resumen_ejecutivo_costes(desde, hasta)
        nat = res["naturaleza"]
        total = float(res["total"] or 0)
        merma_t = float(nat.get("Merma", 0) + nat.get("Expiración", 0))
        pct_merma = round((merma_t / total) * 100, 1) if total > 0 else 0.0
        metrics = (
            MetricVM("Coste total", res["total_fmt"], _fmt_var(res.get("variacion_pct"))),
            MetricVM(
                "Consumo",
                res["consumo_fmt"],
                f"{res['n_registros']} registros · media {res['coste_medio_registro_fmt']}",
            ),
            MetricVM(
                "Merma + expiración",
                repo.formato_precio(merma_t),
                f"{pct_merma}% del coste total",
            ),
            MetricVM(
                "Mayor servicio",
                str(res.get("categoria_mayor") or "—"),
                repo.formato_precio(res.get("categoria_mayor_importe") or 0),
            ),
        )

        serv = res.get("servicios_consumo") or {}
        por_servicio = tuple(
            MetricVM(k, repo.formato_precio(v), "Consumo del periodo")
            for k, v in serv.items()
            if k != "Total"
        )

        tot_nat = total or 1.0
        dist = [
            {
                "categoria": k,
                "importe": v,
                "porcentaje": round((v / tot_nat) * 100, 1) if total else 0,
            }
            for k, v in nat.items()
        ]
        chart_nat = _bars_nat(dist, repo)

        evo = dash.evolucion_por_categoria(desde, hasta)
        puntos = []
        series = ("Desayuno", "Comida", "Cena", "Bebidas")
        for row in evo:
            f = row.get("fecha")
            if isinstance(f, date):
                fecha_s = f.strftime("%d/%m")
            else:
                fecha_s = str(f or "")
            pts: dict = {"fecha": fecha_s}
            any_v = False
            for key in series:
                val = float(row.get(key, 0) or 0)
                pts[key] = val
                if val > 0:
                    any_v = True
            if any_v:
                puntos.append(pts)
        chart_evo = None
        if puntos:
            chart_evo = ChartSeriesVM(
                titulo="Evolución de coste por servicio",
                series=series,
                puntos=tuple(puntos),
            )

        top_prod = costes_service.top_generadores_coste(desde, hasta, limite=8)
        top_rec = costes_service.top_recetas_coste(desde, hasta, limite=8)
        rankings = [
            RankingBlockVM(
                "Productos con mayor coste",
                tuple(
                    RankingRowVM(
                        nombre=str(f.get("nombre") or ""),
                        coste_fmt=str(f.get("coste_fmt") or ""),
                        cantidad_fmt=str(f.get("cantidad_fmt") or ""),
                        usos=f.get("usos", ""),
                    )
                    for f in top_prod
                ),
            ),
            RankingBlockVM(
                "Recetas con mayor coste",
                tuple(
                    RankingRowVM(
                        nombre=str(f.get("nombre") or ""),
                        coste_fmt=str(f.get("coste_fmt") or ""),
                        usos=f.get("usos", ""),
                        extra=str(f.get("porciones", "") or ""),
                    )
                    for f in top_rec
                ),
            ),
        ]
        try:
            top_merma = merma_an.ranking_productos_merma(
                desde, hasta, ambito=merma_an.AMBITO_TODO, limite=5
            )
            rankings.append(
                RankingBlockVM(
                    "Mayor merma (productos)",
                    tuple(
                        RankingRowVM(
                            nombre=str(f.get("nombre") or ""),
                            coste_fmt=str(f.get("coste_fmt") or ""),
                            cantidad_fmt=str(f.get("cantidad_fmt") or ""),
                        )
                        for f in top_merma
                    ),
                )
            )
        except Exception:  # noqa: BLE001
            pass

        return DashboardPanelVM(
            saludo=saludo,
            periodo_label=label,
            metrics=metrics,
            por_servicio=por_servicio,
            chart_naturaleza=chart_nat,
            chart_evolucion=chart_evo,
            rankings=tuple(rankings),
            alertas=tuple(alertas_vm),
            puede_ver_economia=True,
        )
    except AuthorizationError as exc:
        return DashboardPanelVM(
            saludo=saludo,
            periodo_label=label,
            alertas=tuple(alertas_vm),
            puede_ver_economia=False,
            aviso=str(exc) or "Acceso denegado a costes.",
        )
    except Exception as exc:  # noqa: BLE001
        return DashboardPanelVM(
            saludo=saludo,
            periodo_label=label,
            alertas=tuple(alertas_vm),
            puede_ver_economia=puede,
            aviso=f"No se pudo cargar el dashboard ({type(exc).__name__}).",
        )
