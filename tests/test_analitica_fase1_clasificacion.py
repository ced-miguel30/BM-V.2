"""Pruebas Fase 1 — modelo analítico y clasificación.

Ejecutar:

    py -m unittest tests.test_analitica_fase1_clasificacion -v
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
    CategoriaReceta,
    IngredienteReceta,
    LineaDetalleOrigen,
    OrigenConsumo,
    Producto,
    Receta,
    RegistroDesayuno,
    RegistroRecetaDesayuno,
    RegistroServicio,
    TipoServicio,
    UnidadProducto,
    Usuario,
)
from app.core.models.enums import RolUsuario
from app.core.models.registro_servicio import LineaServicio, RegistroRecetaServicio
from app.core.services import analitica_consumo_service as analitica
from app.core.services.detalle_origen_service import construir_lineas_detalle
from app.core.services.cesta_service import GrupoRecetaCesta, LineaCesta, LineaCestaIngrediente
from app.data.serializers import appdata_to_dict, dict_to_appdata


def _catalogo() -> AppData:
    return AppData(
        productos=[
            Producto("p_pan", "Pan", UnidadProducto.KG, es_bebida=False),
            Producto("p_cafe", "Café", UnidadProducto.L, es_bebida=True),
            Producto("p_azucar", "Azúcar", UnidadProducto.KG, es_bebida=False),
            Producto("p_leche", "Leche", UnidadProducto.L, es_bebida=True),
            Producto("p_huevo", "Huevo", UnidadProducto.UD, es_bebida=False),
        ],
        recetas=[
            Receta(
                "r_tostada", "Tostada",
                [IngredienteReceta("p_pan", 0.1)],
                CategoriaReceta.DESAYUNO,
            ),
            Receta(
                "r_latte", "Café latte",
                [
                    IngredienteReceta("p_cafe", 0.2),
                    IngredienteReceta("p_azucar", 0.05),  # no bebida
                ],
                CategoriaReceta.BEBIDAS,
            ),
            Receta(
                "r_pasta", "Pasta",
                [IngredienteReceta("p_pan", 0.2)],
                CategoriaReceta.COMIDA,
            ),
        ],
        usuarios=[Usuario("u01", "Ana", RolUsuario.ADMIN, True)],
        usuario_actual_id="u01",
    )


def _det(
    *,
    origen: str,
    producto_id: str,
    cantidad: float,
    coste: float,
    tipo_servicio: str = "desayuno",
    receta_origen_id: str | None = None,
    es_bebida_snapshot: bool | None = None,
    categoria_receta_snapshot: str | None = None,
    categoria_receta: str | None = None,
) -> LineaDetalleOrigen:
    return LineaDetalleOrigen(
        origen=origen,
        producto_id=producto_id,
        cantidad=cantidad,
        coste=coste,
        receta_origen_id=receta_origen_id,
        registro_origen_id="reg1",
        tipo_servicio=tipo_servicio,
        categoria_receta=categoria_receta,
        es_bebida_snapshot=es_bebida_snapshot,
        categoria_receta_snapshot=categoria_receta_snapshot,
    )


class TestClasificacionDesayuno(unittest.TestCase):
    def test_receta_no_bebida(self) -> None:
        data = _catalogo()
        data.desayunos.append(RegistroDesayuno(
            "d1", date(2026, 7, 1), coste_total=5.0, registrado_por="Ana",
            registros_recetas=[
                RegistroRecetaDesayuno(
                    "r_tostada", "Tostada", 2.0,
                    categoria_receta_snapshot="desayuno",
                ),
            ],
            lineas_detalle=[
                _det(
                    origen=OrigenConsumo.INGREDIENTE_RECETA.value,
                    producto_id="p_pan", cantidad=0.2, coste=5.0,
                    receta_origen_id="r_tostada",
                    es_bebida_snapshot=False,
                    categoria_receta_snapshot="desayuno",
                ),
            ],
        ))
        d = analitica.desglose_desayuno(data=data)
        self.assertEqual(d.desayuno, 5.0)
        self.assertEqual(d.bebida_en_desayuno, 0.0)
        self.assertEqual(d.sin_desglose_historico, 0.0)
        self.assertEqual(d.desayuno_total, 5.0)
        self.assertEqual(d.desayuno + d.bebida_en_desayuno, d.desayuno_total)

    def test_producto_suelto_no_bebida(self) -> None:
        data = _catalogo()
        data.desayunos.append(RegistroDesayuno(
            "d1", date(2026, 7, 1), coste_total=3.0, registrado_por="Ana",
            lineas_detalle=[
                _det(
                    origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                    producto_id="p_huevo", cantidad=2.0, coste=3.0,
                    es_bebida_snapshot=False,
                ),
            ],
        ))
        d = analitica.desglose_desayuno(data=data)
        self.assertEqual(d.desayuno, 3.0)
        self.assertEqual(d.bebida_en_desayuno, 0.0)

    def test_extra_no_bebida(self) -> None:
        data = _catalogo()
        data.desayunos.append(RegistroDesayuno(
            "d1", date(2026, 7, 1), coste_total=1.5, registrado_por="Ana",
            lineas_detalle=[
                _det(
                    origen=OrigenConsumo.EXTRA_RECETA.value,
                    producto_id="p_pan", cantidad=0.05, coste=1.5,
                    receta_origen_id="r_tostada",
                    es_bebida_snapshot=False,
                    categoria_receta_snapshot="desayuno",
                ),
            ],
        ))
        d = analitica.desglose_desayuno(data=data)
        self.assertEqual(d.desayuno, 1.5)

    def test_bebida_directa(self) -> None:
        data = _catalogo()
        data.desayunos.append(RegistroDesayuno(
            "d1", date(2026, 7, 1), coste_total=2.0, registrado_por="Ana",
            lineas_detalle=[
                _det(
                    origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                    producto_id="p_cafe", cantidad=0.3, coste=2.0,
                    es_bebida_snapshot=True,
                ),
            ],
        ))
        d = analitica.desglose_desayuno(data=data)
        self.assertEqual(d.desayuno, 0.0)
        self.assertEqual(d.bebida_en_desayuno, 2.0)

    def test_receta_bebida_con_ingrediente_no_bebida(self) -> None:
        """Toda la receta de categoría bebidas va a bebida_en_desayuno."""
        data = _catalogo()
        data.desayunos.append(RegistroDesayuno(
            "d1", date(2026, 7, 1), coste_total=4.0, registrado_por="Ana",
            registros_recetas=[
                RegistroRecetaDesayuno(
                    "r_latte", "Café latte", 1.0,
                    categoria_receta_snapshot="bebidas",
                ),
            ],
            lineas_detalle=[
                _det(
                    origen=OrigenConsumo.INGREDIENTE_RECETA.value,
                    producto_id="p_cafe", cantidad=0.2, coste=3.0,
                    receta_origen_id="r_latte",
                    es_bebida_snapshot=True,
                    categoria_receta_snapshot="bebidas",
                ),
                _det(
                    origen=OrigenConsumo.INGREDIENTE_RECETA.value,
                    producto_id="p_azucar", cantidad=0.05, coste=1.0,
                    receta_origen_id="r_latte",
                    es_bebida_snapshot=False,  # no marcado bebida
                    categoria_receta_snapshot="bebidas",
                ),
            ],
        ))
        d = analitica.desglose_desayuno(data=data)
        self.assertEqual(d.desayuno, 0.0)
        self.assertEqual(d.bebida_en_desayuno, 4.0)
        self.assertEqual(d.desayuno_total, 4.0)
        productos = analitica.iter_eventos_producto(data=data)
        self.assertTrue(all(
            e.bucket_interno == analitica.BUCKET_BEBIDA_EN_DESAYUNO for e in productos
        ))

    def test_ingrediente_bebida_en_receta_desayuno(self) -> None:
        data = _catalogo()
        data.desayunos.append(RegistroDesayuno(
            "d1", date(2026, 7, 1), coste_total=6.0, registrado_por="Ana",
            lineas_detalle=[
                _det(
                    origen=OrigenConsumo.INGREDIENTE_RECETA.value,
                    producto_id="p_pan", cantidad=0.1, coste=4.0,
                    receta_origen_id="r_tostada",
                    es_bebida_snapshot=False,
                    categoria_receta_snapshot="desayuno",
                ),
                _det(
                    origen=OrigenConsumo.INGREDIENTE_RECETA.value,
                    producto_id="p_leche", cantidad=0.1, coste=2.0,
                    receta_origen_id="r_tostada",
                    es_bebida_snapshot=True,
                    categoria_receta_snapshot="desayuno",
                ),
            ],
        ))
        d = analitica.desglose_desayuno(data=data)
        self.assertEqual(d.desayuno, 4.0)
        self.assertEqual(d.bebida_en_desayuno, 2.0)
        self.assertEqual(d.desayuno + d.bebida_en_desayuno, d.desayuno_total)

    def test_mismo_producto_directo_e_ingrediente(self) -> None:
        data = _catalogo()
        data.desayunos.append(RegistroDesayuno(
            "d1", date(2026, 7, 1), coste_total=5.0, registrado_por="Ana",
            lineas_detalle=[
                _det(
                    origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                    producto_id="p_pan", cantidad=0.1, coste=2.0,
                    es_bebida_snapshot=False,
                ),
                _det(
                    origen=OrigenConsumo.INGREDIENTE_RECETA.value,
                    producto_id="p_pan", cantidad=0.15, coste=3.0,
                    receta_origen_id="r_tostada",
                    es_bebida_snapshot=False,
                    categoria_receta_snapshot="desayuno",
                ),
            ],
        ))
        eventos = analitica.iter_eventos_producto(data=data)
        self.assertEqual(len(eventos), 2)
        origenes = {e.tipo_elemento for e in eventos}
        self.assertEqual(
            origenes,
            {OrigenConsumo.PRODUCTO_DIRECTO.value, OrigenConsumo.INGREDIENTE_RECETA.value},
        )
        d = analitica.desglose_desayuno(data=data)
        self.assertEqual(d.desayuno_total, 5.0)
        self.assertEqual(d.desayuno, 5.0)


class TestSinDesgloseYSnapshots(unittest.TestCase):
    def test_antiguo_sin_lineas_detalle(self) -> None:
        data = _catalogo()
        data.desayunos.append(RegistroDesayuno(
            "d_old", date(2026, 6, 1), coste_total=12.5, registrado_por="Ana",
            lineas_detalle=[],
        ))
        d = analitica.desglose_desayuno(data=data)
        self.assertEqual(d.sin_desglose_historico, 12.5)
        self.assertEqual(d.desayuno, 0.0)
        self.assertEqual(d.bebida_en_desayuno, 0.0)
        self.assertEqual(d.desayuno_total, 12.5)
        self.assertEqual(
            d.desayuno + d.bebida_en_desayuno + d.sin_desglose_historico,
            d.desayuno_total,
        )
        self.assertEqual(analitica.iter_eventos_producto(data=data), [])

    def test_desayuno_total_con_y_sin_desglose(self) -> None:
        data = _catalogo()
        data.desayunos.extend([
            RegistroDesayuno(
                "d_new", date(2026, 7, 1), coste_total=10.0, registrado_por="Ana",
                lineas_detalle=[
                    _det(
                        origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                        producto_id="p_pan", cantidad=0.2, coste=7.0,
                        es_bebida_snapshot=False,
                    ),
                    _det(
                        origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                        producto_id="p_cafe", cantidad=0.1, coste=3.0,
                        es_bebida_snapshot=True,
                    ),
                ],
            ),
            RegistroDesayuno(
                "d_old", date(2026, 7, 2), coste_total=8.0, registrado_por="Ana",
                lineas_detalle=[],
            ),
        ])
        d = analitica.desglose_desayuno(data=data)
        self.assertEqual(d.desayuno, 7.0)
        self.assertEqual(d.bebida_en_desayuno, 3.0)
        self.assertEqual(d.sin_desglose_historico, 8.0)
        self.assertEqual(d.desayuno_total, 18.0)

    def test_antiguo_sin_snapshots_usa_catalogo(self) -> None:
        data = _catalogo()
        data.desayunos.append(RegistroDesayuno(
            "d1", date(2026, 7, 1), coste_total=5.0, registrado_por="Ana",
            lineas_detalle=[
                _det(
                    origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                    producto_id="p_cafe", cantidad=0.2, coste=2.0,
                    es_bebida_snapshot=None,
                ),
                _det(
                    origen=OrigenConsumo.INGREDIENTE_RECETA.value,
                    producto_id="p_azucar", cantidad=0.05, coste=3.0,
                    receta_origen_id="r_latte",
                    es_bebida_snapshot=None,
                    categoria_receta_snapshot=None,
                    categoria_receta=None,
                ),
            ],
        ))
        # Café vía catálogo → bebida; azúcar en receta bebidas vía catálogo de receta.
        d = analitica.desglose_desayuno(data=data)
        self.assertEqual(d.bebida_en_desayuno, 5.0)
        self.assertEqual(d.desayuno, 0.0)
        self.assertTrue(analitica.resolver_es_bebida(data.desayunos[0].lineas_detalle[0], data))


class TestFamiliasYDobleConteo(unittest.TestCase):
    def test_apis_separadas_receta_vs_producto(self) -> None:
        data = _catalogo()
        data.desayunos.append(RegistroDesayuno(
            "d1", date(2026, 7, 1), coste_total=5.0, registrado_por="Ana",
            registros_recetas=[
                RegistroRecetaDesayuno(
                    "r_tostada", "Tostada", 3.0,
                    categoria_receta_snapshot="desayuno",
                ),
            ],
            lineas_detalle=[
                _det(
                    origen=OrigenConsumo.INGREDIENTE_RECETA.value,
                    producto_id="p_pan", cantidad=0.3, coste=5.0,
                    receta_origen_id="r_tostada",
                    es_bebida_snapshot=False,
                    categoria_receta_snapshot="desayuno",
                ),
            ],
        ))
        recetas = analitica.iter_eventos_receta(data=data)
        productos = analitica.iter_eventos_producto(data=data)
        self.assertEqual(len(recetas), 1)
        self.assertEqual(recetas[0].familia_evento, analitica.FAMILIA_RECETA)
        self.assertIsNone(recetas[0].coste)
        self.assertEqual(len(productos), 1)
        self.assertEqual(productos[0].familia_evento, analitica.FAMILIA_PRODUCTO)
        # No sumar coste de receta (None) + ingredientes en agregados de producto.
        coste_productos = sum(e.coste for e in productos)
        self.assertEqual(coste_productos, 5.0)
        self.assertEqual(sum(e.porciones for e in recetas), 3.0)

    def test_ranking_menos_solo_consumo_positivo(self) -> None:
        data = _catalogo()
        data.desayunos.append(RegistroDesayuno(
            "d1", date(2026, 7, 1), coste_total=3.0, registrado_por="Ana",
            lineas_detalle=[
                _det(
                    origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                    producto_id="p_pan", cantidad=0.1, coste=2.0,
                    es_bebida_snapshot=False,
                ),
                _det(
                    origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                    producto_id="p_huevo", cantidad=1.0, coste=1.0,
                    es_bebida_snapshot=False,
                ),
            ],
        ))
        menos = analitica.ranking_productos(data=data, ascendente=True)
        self.assertTrue(all(r["usos"] > 0 for r in menos))
        self.assertEqual(menos[0]["producto_id"], "p_huevo")
        # p_leche sin consumo no aparece
        self.assertNotIn("p_leche", {r["producto_id"] for r in menos})


class TestServiciosExcluyentesYBebidas(unittest.TestCase):
    def test_coste_general_suma_cuatro(self) -> None:
        data = _catalogo()
        data.desayunos.append(RegistroDesayuno(
            "d1", date(2026, 7, 1), coste_total=10.0, registrado_por="Ana",
            lineas_detalle=[
                _det(
                    origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                    producto_id="p_pan", cantidad=0.1, coste=10.0,
                    es_bebida_snapshot=False,
                ),
            ],
        ))
        data.registros_servicio.extend([
            RegistroServicio(
                "c1", TipoServicio.COMIDA.value, date(2026, 7, 1),
                coste_total=20.0, registrado_por="Ana",
                lineas_detalle=[
                    _det(
                        origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                        producto_id="p_pan", cantidad=0.2, coste=20.0,
                        tipo_servicio="comida",
                        es_bebida_snapshot=False,
                    ),
                ],
            ),
            RegistroServicio(
                "n1", TipoServicio.CENA.value, date(2026, 7, 1),
                coste_total=15.0, registrado_por="Ana",
            ),
            RegistroServicio(
                "b1", TipoServicio.BEBIDAS.value, date(2026, 7, 1),
                coste_total=5.0, registrado_por="Ana",
                lineas_detalle=[
                    _det(
                        origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                        producto_id="p_cafe", cantidad=0.5, coste=5.0,
                        tipo_servicio="bebidas",
                        es_bebida_snapshot=True,
                    ),
                ],
            ),
        ])
        c = analitica.coste_servicios_excluyentes(data=data)
        self.assertEqual(c.desayuno_total, 10.0)
        self.assertEqual(c.comida_total, 20.0)
        self.assertEqual(c.cena_total, 15.0)
        self.assertEqual(c.bebidas_independientes, 5.0)
        self.assertEqual(c.coste_general, 50.0)

    def test_bebida_independiente_vs_bebida_en_desayuno(self) -> None:
        data = _catalogo()
        data.desayunos.append(RegistroDesayuno(
            "d1", date(2026, 7, 1), coste_total=3.0, registrado_por="Ana",
            lineas_detalle=[
                _det(
                    origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                    producto_id="p_cafe", cantidad=0.2, coste=3.0,
                    es_bebida_snapshot=True,
                ),
            ],
        ))
        data.registros_servicio.append(RegistroServicio(
            "b1", TipoServicio.BEBIDAS.value, date(2026, 7, 1),
            coste_total=7.0, registrado_por="Ana",
            lineas_detalle=[
                _det(
                    origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                    producto_id="p_cafe", cantidad=0.4, coste=7.0,
                    tipo_servicio="bebidas",
                    es_bebida_snapshot=True,
                ),
            ],
        ))
        en_des = analitica.coste_bucket_bebida(
            analitica.BUCKET_BEBIDA_EN_DESAYUNO, data=data,
        )
        indep = analitica.coste_bucket_bebida(
            analitica.BUCKET_BEBIDA_INDEPENDIENTE, data=data,
        )
        self.assertEqual(en_des, 3.0)
        self.assertEqual(indep, 7.0)
        c = analitica.coste_servicios_excluyentes(data=data)
        # Bebidas en desayuno no se suman aparte en bebidas_independientes
        self.assertEqual(c.desayuno_total, 3.0)
        self.assertEqual(c.bebidas_independientes, 7.0)
        self.assertEqual(c.coste_general, 10.0)


class TestUnidadesYSnapshotsAlRegistrar(unittest.TestCase):
    def test_agregacion_unidad_normalizada(self) -> None:
        data = _catalogo()
        data.desayunos.append(RegistroDesayuno(
            "d1", date(2026, 7, 1), coste_total=4.0, registrado_por="Ana",
            lineas_detalle=[
                _det(
                    origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                    producto_id="p_pan", cantidad=0.25, coste=2.0,
                    es_bebida_snapshot=False,
                ),
                _det(
                    origen=OrigenConsumo.INGREDIENTE_RECETA.value,
                    producto_id="p_pan", cantidad=0.15, coste=2.0,
                    receta_origen_id="r_tostada",
                    es_bebida_snapshot=False,
                    categoria_receta_snapshot="desayuno",
                ),
            ],
        ))
        ranking = analitica.ranking_productos(data=data)
        pan = next(r for r in ranking if r["producto_id"] == "p_pan")
        self.assertEqual(pan["unidad_normalizada"], "Kg")
        self.assertAlmostEqual(pan["cantidad_normalizada"], 0.4)
        self.assertEqual(pan["coste"], 4.0)

    def test_construir_detalle_rellena_snapshots(self) -> None:
        data = _catalogo()
        cesta = [LineaCesta("l1", "p_cafe", "Café", "L", 0.2)]
        grupos = [
            GrupoRecetaCesta(
                "g1", "r_latte", "Café latte", 1.0,
                [
                    LineaCestaIngrediente(
                        "i1", "p_cafe", "Café", "L", 0.2, True, False, False,
                    ),
                    LineaCestaIngrediente(
                        "i2", "p_azucar", "Azúcar", "Kg", 0.05, True, False, False,
                    ),
                ],
            ),
        ]
        detalle = construir_lineas_detalle(
            cesta, grupos, tipo_servicio="desayuno", registro_id="x1", data=data,
        )
        cafe_directo = next(
            d for d in detalle
            if d.producto_id == "p_cafe" and d.origen == OrigenConsumo.PRODUCTO_DIRECTO.value
        )
        self.assertTrue(cafe_directo.es_bebida_snapshot)
        azucar = next(d for d in detalle if d.producto_id == "p_azucar")
        self.assertFalse(azucar.es_bebida_snapshot)
        self.assertEqual(azucar.categoria_receta_snapshot, "bebidas")

    def test_serializer_roundtrip_snapshots(self) -> None:
        data = _catalogo()
        data.desayunos.append(RegistroDesayuno(
            "d1", date(2026, 7, 1), coste_total=1.0, registrado_por="Ana",
            registros_recetas=[
                RegistroRecetaDesayuno(
                    "r_tostada", "Tostada", 1.0,
                    categoria_receta_snapshot="desayuno",
                ),
            ],
            lineas_detalle=[
                _det(
                    origen=OrigenConsumo.PRODUCTO_DIRECTO.value,
                    producto_id="p_cafe", cantidad=0.1, coste=1.0,
                    es_bebida_snapshot=True,
                    categoria_receta_snapshot=None,
                ),
            ],
        ))
        restored = dict_to_appdata(appdata_to_dict(data))
        det = restored.desayunos[0].lineas_detalle[0]
        self.assertTrue(det.es_bebida_snapshot)
        self.assertEqual(
            restored.desayunos[0].registros_recetas[0].categoria_receta_snapshot,
            "desayuno",
        )
        # JSON antiguo sin claves snapshot
        payload = appdata_to_dict(data)
        del payload["desayunos"][0]["lineas_detalle"][0]["es_bebida_snapshot"]
        del payload["desayunos"][0]["registros_recetas"][0]["categoria_receta_snapshot"]
        old = dict_to_appdata(payload)
        self.assertIsNone(old.desayunos[0].lineas_detalle[0].es_bebida_snapshot)
        self.assertIsNone(old.desayunos[0].registros_recetas[0].categoria_receta_snapshot)


if __name__ == "__main__":
    unittest.main()
