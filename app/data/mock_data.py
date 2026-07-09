"""Datos de ejemplo para desarrollo y pruebas (sin base de datos)."""

from datetime import date, datetime, timedelta

from app.core.models import (
    Actividad,
    AlertaOperativa,
    AppData,
    ConfiguracionHotel,
    IngredienteReceta,
    LineaDesayuno,
    LineaMerma,
    LoteStock,
    MotivoMerma,
    Producto,
    Receta,
    RegistroDesayuno,
    RegistroMerma,
    RolUsuario,
    TipoAlerta,
    UnidadProducto,
    Usuario,
)

HOY = date.today()
INICIO_MES = HOY.replace(day=1)


def crear_datos_mock() -> AppData:
    """Genera un conjunto coherente de datos de ejemplo."""
    productos = [
        Producto("p01", "Croissant", UnidadProducto.UD, stock_minimo=20),
        Producto("p02", "Pan de molde", UnidadProducto.UD, stock_minimo=10),
        Producto("p03", "Jamón serrano", UnidadProducto.KG, stock_minimo=2),
        Producto("p04", "Queso manchego", UnidadProducto.KG, stock_minimo=1.5),
        Producto("p05", "Yogur natural", UnidadProducto.UD, stock_minimo=24),
        Producto("p06", "Zumo de naranja", UnidadProducto.L, stock_minimo=5),
        Producto("p07", "Café molido", UnidadProducto.KG, stock_minimo=1),
        Producto("p08", "Mantequilla", UnidadProducto.KG, stock_minimo=0.5),
        Producto("p09", "Fruta fresca", UnidadProducto.KG, stock_minimo=3),
        Producto("p10", "Huevos", UnidadProducto.UD, stock_minimo=36),
    ]

    lotes = [
        LoteStock("l01", "p01", 18.00, 60, 42, HOY - timedelta(days=5), HOY + timedelta(days=3), "Panadería Sol", 3),
        LoteStock("l02", "p02", 4.50, 12, 8, HOY - timedelta(days=3), HOY + timedelta(days=7), "Bimbo", 5),
        LoteStock("l03", "p03", 45.00, 2.5, 1.2, HOY - timedelta(days=10), HOY + timedelta(days=14), "Embutidos Norte", 5),
        LoteStock("l04", "p04", 28.00, 1.8, 0.6, HOY - timedelta(days=8), HOY + timedelta(days=10), "Quesería Manchega", 5),
        LoteStock("l05", "p05", 12.00, 48, 12, HOY - timedelta(days=4), HOY + timedelta(days=2), "Danone", 3),
        LoteStock("l06", "p06", 15.00, 10, 4.5, HOY - timedelta(days=2), HOY + timedelta(days=5), "Cítricos Valle", 3),
        LoteStock("l07", "p07", 22.00, 2, 0.8, HOY - timedelta(days=15), HOY + timedelta(days=60), "Cafés Origen", 14),
        LoteStock("l08", "p08", 8.50, 1, 0.3, HOY - timedelta(days=6), HOY + timedelta(days=20), "Lácteos Sur", 5),
        LoteStock("l09", "p09", 12.00, 5, 2.1, HOY - timedelta(days=1), HOY + timedelta(days=4), "Frutas del Mercado", 2),
        LoteStock("l10", "p10", 6.00, 60, 0, HOY - timedelta(days=7), HOY - timedelta(days=1), "Granja Local", 3),
    ]

    recetas = [
        Receta(
            "r01",
            "Sándwich mixto",
            [
                IngredienteReceta("p02", 2),
                IngredienteReceta("p03", 0.01),
                IngredienteReceta("p04", 0.01),
            ],
        ),
        Receta(
            "r02",
            "Tostada con mantequilla",
            [
                IngredienteReceta("p02", 1),
                IngredienteReceta("p08", 0.01),
            ],
        ),
    ]

    desayunos = [
        RegistroDesayuno(
            "d01",
            HOY - timedelta(days=1),
            [
                LineaDesayuno("p01", 18, 5.40),
                LineaDesayuno("p03", 0.4, 7.20),
                LineaDesayuno("p06", 2.0, 3.00),
                LineaDesayuno("p10", 12, 1.20),
            ],
            16.80,
            "María García",
            28,
        ),
        RegistroDesayuno(
            "d02",
            HOY - timedelta(days=2),
            [
                LineaDesayuno("p01", 20, 6.00),
                LineaDesayuno("p05", 16, 4.00),
                LineaDesayuno("p07", 0.15, 1.65),
                LineaDesayuno("p09", 1.5, 3.60),
            ],
            15.25,
            "María García",
            32,
        ),
        RegistroDesayuno(
            "d03",
            HOY - timedelta(days=3),
            [
                LineaDesayuno("p02", 6, 2.25),
                LineaDesayuno("p04", 0.3, 4.67),
                LineaDesayuno("p08", 0.2, 1.70),
                LineaDesayuno("p10", 10, 1.00),
            ],
            9.62,
            "Carlos Ruiz",
            25,
        ),
    ]

    mermas = [
        RegistroMerma(
            "m01",
            HOY - timedelta(days=1),
            [LineaMerma("p05", 4, 1.00, MotivoMerma.EXPIRACION, "Yogures caducados")],
            1.00,
            "María García",
        ),
        RegistroMerma(
            "m02",
            HOY - timedelta(days=3),
            [LineaMerma("p01", 3, 0.90, MotivoMerma.MERMA, "Rotos en manipulación")],
            0.90,
            "Carlos Ruiz",
        ),
        RegistroMerma(
            "m03",
            HOY - timedelta(days=5),
            [LineaMerma("p10", 6, 0.60, MotivoMerma.EXPIRACION, "Huevos fuera de fecha")],
            0.60,
            "María García",
        ),
    ]

    alertas = [
        AlertaOperativa(
            "a01",
            TipoAlerta.STOCK_BAJO,
            "Stock bajo — Yogur natural",
            "Quedan 12 unidades. Stock mínimo: 24.",
            HOY,
            producto_id="p05",
        ),
        AlertaOperativa(
            "a02",
            TipoAlerta.STOCK_CERO,
            "Stock agotado — Huevos",
            "No quedan unidades disponibles.",
            HOY,
            producto_id="p10",
        ),
        AlertaOperativa(
            "a03",
            TipoAlerta.EXPIRACION_PROXIMA,
            "Próximo a expirar — Croissant",
            "El lote l01 expira en 3 días.",
            HOY,
            producto_id="p01",
        ),
        AlertaOperativa(
            "a04",
            TipoAlerta.EXPIRADO,
            "Producto expirado — Huevos",
            "El lote l10 expiró ayer. Retirar del stock.",
            HOY,
            producto_id="p10",
        ),
        AlertaOperativa(
            "a05",
            TipoAlerta.MERMA_ELEVADA,
            "Merma superior al mes anterior",
            "La merma acumulada supera un 15% respecto al mes pasado.",
            HOY,
        ),
        AlertaOperativa(
            "a06",
            TipoAlerta.DESAYUNO_NO_REGISTRADO,
            "Desayuno de hoy no registrado",
            "Aún no se ha registrado el consumo del desayuno de hoy.",
            HOY,
        ),
        AlertaOperativa(
            "a07",
            TipoAlerta.MANUAL,
            "Revisar proveedor de jamón",
            "Verificar precio del próximo pedido con Embutidos Norte.",
            HOY + timedelta(days=2),
            producto_id="p03",
        ),
    ]

    usuarios = [
        Usuario("u01", "María García", RolUsuario.OWNER, activo=True),
        Usuario("u02", "Carlos Ruiz", RolUsuario.ADMIN, activo=True),
    ]

    configuracion = ConfiguracionHotel(
        nombre_establecimiento="Hotel Boutique La Alameda",
        moneda="EUR",
        simbolo_moneda="€",
        logo_path=None,
    )

    actividades = [
        Actividad("act01", datetime.combine(HOY, datetime.min.time().replace(hour=8, minute=15)), "María García", "Inicio de sesión", "Acceso temporal sin login"),
        Actividad("act02", datetime.combine(HOY - timedelta(days=1), datetime.min.time().replace(hour=9, minute=30)), "María García", "Registro desayuno", "Desayuno del día registrado — 16,80 €"),
        Actividad("act03", datetime.combine(HOY - timedelta(days=1), datetime.min.time().replace(hour=10, minute=5)), "María García", "Registro merma", "4 yogures por expiración — 1,00 €"),
        Actividad("act04", datetime.combine(HOY - timedelta(days=2), datetime.min.time().replace(hour=9, minute=45)), "Carlos Ruiz", "Registro desayuno", "Desayuno del día registrado — 15,25 €"),
        Actividad("act05", datetime.combine(HOY - timedelta(days=3), datetime.min.time().replace(hour=11, minute=0)), "Carlos Ruiz", "Registro merma", "3 croissants por merma — 0,90 €"),
    ]

    return AppData(
        productos=productos,
        lotes=lotes,
        recetas=recetas,
        desayunos=desayunos,
        mermas=mermas,
        alertas=alertas,
        actividades=actividades,
        usuarios=usuarios,
        configuracion=configuracion,
        usuario_actual_id="u01",
    )
