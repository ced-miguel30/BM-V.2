"""Registro de comida — thin wrapper sobre el motor común."""

from app.core.models import CategoriaReceta
from app.core.services.servicio_registro_service import crear_servicio

servicio = crear_servicio(
    "comida",
    "comida",
    [CategoriaReceta.COMIDA, CategoriaReceta.BEBIDAS],
    titulo_documento="Registro de Comida",
)

# Reexportar la API del servicio a nivel de módulo (mismo patrón que usarán
# las páginas y la exportación semanal).
get_cesta = servicio.get_cesta
get_cesta_recetas = servicio.get_cesta_recetas
get_mods_pendientes = servicio.get_mods_pendientes
limpiar_mods_pendientes = servicio.limpiar_mods_pendientes
limpiar_cesta = servicio.limpiar_cesta
cesta_vacia = servicio.cesta_vacia
anadir_a_cesta = servicio.anadir_a_cesta
anadir_receta_a_cesta = servicio.anadir_receta_a_cesta
anadir_mod_pendiente_receta = servicio.anadir_mod_pendiente_receta
quitar_mod_pendiente = servicio.quitar_mod_pendiente
quitar_grupo_receta = servicio.quitar_grupo_receta
quitar_linea_grupo = servicio.quitar_linea_grupo
paso_linea_grupo = servicio.paso_linea_grupo
ajustar_linea_grupo = servicio.ajustar_linea_grupo
modificar_linea_grupo = servicio.modificar_linea_grupo
modificar_porciones_grupo = servicio.modificar_porciones_grupo
ajustar_porciones_grupo = servicio.ajustar_porciones_grupo
paso_linea_suelta = servicio.paso_linea_suelta
quitar_linea_suelta = servicio.quitar_linea_suelta
ajustar_cantidad_suelto = servicio.ajustar_cantidad_suelto
modificar_cantidad_suelto = servicio.modificar_cantidad_suelto
coste_total_cesta = servicio.coste_total_cesta
productos_catalogo = servicio.productos_catalogo
productos_disponibles = servicio.productos_disponibles
registrar = servicio.registrar
historial_ordenado = servicio.historial_ordenado
fecha_mas_antigua = servicio.fecha_mas_antigua
registros_exportables = servicio.registros_exportables
configuracion_exportacion = servicio.configuracion_exportacion

CATEGORIAS_RECETA = [CategoriaReceta.COMIDA, CategoriaReceta.BEBIDAS]
PASO_CANTIDAD = 0.5
