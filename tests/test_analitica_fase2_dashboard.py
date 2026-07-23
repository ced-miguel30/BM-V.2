"""Pruebas Fase 2 — Dashboard y agregación merma/expiración.

Ejecutar:

    py -m unittest tests.test_analitica_fase2_dashboard -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import (
    AppData,
    LineaMerma,
    MotivoMerma,
    Producto,
    RegistroDesayuno,
    RegistroMerma,
    RegistroServicio,
    TipoServicio,
    UnidadProducto,
    Usuario,
)
from app.core.models.enums import RolUsuario
from app.core.models.registro_servicio import LineaDetalleOrigen
from app.core.repositories.data_repository import DataRepository
from app.core.services import analitica_consumo_service as analitica
from app.core.services import dashboard_service as dash
from app.core.models import OrigenConsumo


def _app() -> AppData:
    return AppData(
        productos=[
            Producto("p1", "Pan", UnidadProducto.KG),
            Producto("p2", "Leche", UnidadProducto.L, es_bebida=True),
        ],
        usuarios=[Usuario("u1", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u1",
    )


class TestExpiracionSinDobleConteo(unittest.TestCase):
    """Confirma que la expiración no se suma dos veces en el total del mes."""

    def _repo_con_merma_mixta(self) -> DataRepository:
        data = _app()
        # Fuerza fechas del mes en curso relativa a un día fijo del test
        # usando fechas explícitas y periodo helpers.
        hoy = date.today()
        data.mermas.append(RegistroMerma(
            "m1",
            hoy,
            [
                LineaMerma("p1", 1.0, 4.0, MotivoMerma.MERMA),
                LineaMerma("p1", 1.0, 6.0, MotivoMerma.EXPIRACION),
            ],
            coste_total=10.0,
            registrado_por="Ana",
        ))
        return DataRepository(data)

    def test_coste_merma_mes_excluye_expiracion(self) -> None:
        """Tras el arreglo: merma_mes no incluye líneas de expiración."""
        repo = self._repo_con_merma_mixta()
        self.assertEqual(repo.coste_merma_mes(), 4.0)
        self.assertEqual(repo.coste_expiracion_mes(), 6.0)

    def test_expiracion_no_se_cuenta_doble_en_total_mes(self) -> None:
        repo = self._repo_con_merma_mixta()
        # Si merma_mes incluyera coste_total (10) + expiracion (6) = 16 (doble).
        # Correcto: 4 + 6 = 10.
        self.assertEqual(repo.coste_merma_mes() + repo.coste_expiracion_mes(), 10.0)
        self.assertEqual(
            repo.coste_total_mes(),
            repo.coste_consumo_mes() + 10.0,
        )

    def test_documenta_que_coste_total_registro_incluye_ambas_lineas(self) -> None:
        """El registro histórico conserva coste_total=10; solo cambia la agregación."""
        repo = self._repo_con_merma_mixta()
        self.assertEqual(repo.data.mermas[0].coste_total, 10.0)


class TestDashboardAgregados(unittest.TestCase):
    def test_coste_general_suma_cuatro_categorias(self) -> None:
        data = _app()
        d0 = date(2026, 7, 10)
        data.desayunos.append(RegistroDesayuno(
            "d1", d0, coste_total=10.0, registrado_por="Ana",
            lineas_detalle=[
                LineaDetalleOrigen(
                    OrigenConsumo.PRODUCTO_DIRECTO.value, "p1", 0.1, 10.0,
                    tipo_servicio="desayuno", es_bebida_snapshot=False,
                ),
            ],
        ))
        data.registros_servicio.extend([
            RegistroServicio("c1", TipoServicio.COMIDA.value, d0, coste_total=20.0),
            RegistroServicio("n1", TipoServicio.CENA.value, d0, coste_total=5.0),
            RegistroServicio("b1", TipoServicio.BEBIDAS.value, d0, coste_total=3.0),
        ])
        c = analitica.coste_servicios_excluyentes(d0, d0, data=data)
        self.assertEqual(c.coste_general, 38.0)
        self.assertEqual(
            c.desayuno_total + c.comida_total + c.cena_total + c.bebidas_independientes,
            c.coste_general,
        )

    def test_filtro_desayuno_desglose(self) -> None:
        data = _app()
        d0 = date(2026, 7, 10)
        data.desayunos.append(RegistroDesayuno(
            "d1", d0, coste_total=10.0, registrado_por="Ana", num_huespedes=20,
            lineas_detalle=[
                LineaDetalleOrigen(
                    OrigenConsumo.PRODUCTO_DIRECTO.value, "p1", 0.1, 7.0,
                    tipo_servicio="desayuno", es_bebida_snapshot=False,
                ),
                LineaDetalleOrigen(
                    OrigenConsumo.PRODUCTO_DIRECTO.value, "p2", 0.2, 3.0,
                    tipo_servicio="desayuno", es_bebida_snapshot=True,
                ),
            ],
        ))
        self.assertEqual(
            dash.coste_filtrado(d0, d0, categoria="Desayuno", desglose_desayuno="Desayuno", data=data),
            7.0,
        )
        self.assertEqual(
            dash.coste_filtrado(
                d0, d0, categoria="Desayuno", desglose_desayuno="Bebidas en desayuno", data=data,
            ),
            3.0,
        )
        self.assertEqual(
            dash.coste_filtrado(
                d0, d0, categoria="Desayuno", desglose_desayuno="Desayuno total", data=data,
            ),
            10.0,
        )
        self.assertEqual(dash.huespedes_desayuno(d0, d0, data=data), 20)

    def test_resolver_periodo_default_mes(self) -> None:
        hoy = date(2026, 7, 15)
        p = dash.resolver_periodo("Este mes", hoy=hoy)
        self.assertEqual(p.desde, date(2026, 7, 1))
        self.assertEqual(p.hasta, hoy)

    def test_evolucion_servicio_solo_comida(self) -> None:
        data = _app()
        d0 = date(2026, 7, 10)
        data.registros_servicio.append(
            RegistroServicio("c1", TipoServicio.COMIDA.value, d0, coste_total=20.0),
        )
        evo = dash.evolucion_servicio("Comida", d0, d0, data=data)
        self.assertEqual(len(evo), 1)
        self.assertEqual(evo[0]["Comida"], 20.0)
        self.assertEqual(set(evo[0].keys()), {"fecha", "Comida"})

    def test_evolucion_bebidas_por_origen(self) -> None:
        data = _app()
        d0 = date(2026, 7, 10)
        data.desayunos.append(RegistroDesayuno(
            "d1", d0, coste_total=3.0, registrado_por="Ana",
            lineas_detalle=[
                LineaDetalleOrigen(
                    OrigenConsumo.PRODUCTO_DIRECTO.value, "p2", 0.2, 3.0,
                    tipo_servicio="desayuno", es_bebida_snapshot=True,
                ),
            ],
        ))
        data.registros_servicio.append(RegistroServicio(
            "b1", TipoServicio.BEBIDAS.value, d0, coste_total=5.0,
            lineas_detalle=[
                LineaDetalleOrigen(
                    OrigenConsumo.PRODUCTO_DIRECTO.value, "p2", 0.5, 5.0,
                    tipo_servicio="bebidas", es_bebida_snapshot=True,
                ),
            ],
        ))
        evo = dash.evolucion_bebidas_por_origen(d0, d0, data=data)
        self.assertEqual(len(evo), 1)
        self.assertEqual(evo[0]["En desayuno"], 3.0)
        self.assertEqual(evo[0]["Independiente"], 5.0)
        self.assertEqual(evo[0]["En comida"], 0.0)
