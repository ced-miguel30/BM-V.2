# Preparación para rankings futuros

Documentación de la **Fase 7**: campos ya persistidos que permiten rankings sin heurísticas.
No hay UI de rankings en esta fase.

## Tabla de cobertura

| Ranking futuro | Campo(s) almacenados | Dónde |
|---|---|---|
| Bebidas (cualquier origen) | `Producto.es_bebida` + `lineas_detalle[].producto_id` en cualquier `tipo_servicio` | Catálogo + detalle de consumo |
| Bebidas en desayuno (directo vs. ingrediente/extra) | `lineas_detalle[].tipo_servicio="desayuno"` + `origen` (`producto_directo` / `ingrediente_receta` / `extra_receta`) + `receta_origen_id` | `RegistroDesayuno.lineas_detalle` |
| Recetas Comida/Cena más/menos usadas | `RegistroServicio.tipo_servicio` + `registros_recetas[].categoria_receta` (+ `receta_id`, `porciones`) | `AppData.registros_servicio` |
| Productos/extras Comida/Cena | `lineas_detalle` filtrado por `tipo_servicio` (`comida`/`cena`) + `origen` | `RegistroServicio.lineas_detalle` |
| Extras desayuno (sin bebidas) | `tipo_servicio="desayuno"` + `origen` en (`producto_directo`, `extra_receta`) + `Producto.es_bebida=False` | Detalle desayuno + catálogo |

## Valores de origen (`OrigenConsumo`)

- `producto_directo` — producto suelto en cesta
- `ingrediente_receta` — ingrediente de una receta aplicada
- `extra_receta` — extra añadido sobre una receta

El mismo producto en un registro como suelto y como ingrediente genera **dos** líneas de detalle (no se fusionan).

## Campos clave de `LineaDetalleOrigen`

| Campo | Uso |
|---|---|
| `origen` | Distingue directo / ingrediente / extra |
| `producto_id` | Une con `Producto` (p. ej. `es_bebida`) |
| `cantidad`, `coste` | Métricas del ranking |
| `receta_origen_id` | Receta de la que proviene (si aplica) |
| `registro_origen_id` | Registro padre |
| `tipo_servicio` | `desayuno` / `comida` / `cena` / `bebidas` |
| `categoria_receta` | Categoría de la receta en líneas de receta; `None` en producto directo |

## Limitaciones reales

1. **Desayunos antiguos** (anteriores a la Fase 2) pueden tener `lineas_detalle=[]`: no admiten desglose por origen hasta que se registren de nuevo.
2. **`RegistroRecetaDesayuno`** no guarda `categoria_receta` en el snapshot; para rankings de recetas de desayuno hay que cruzar con `Receta.categoria` del catálogo (o usar `lineas_detalle[].categoria_receta` en líneas de origen receta).
3. **Comida / Cena / Bebidas** sí guardan `categoria_receta` en cada `RegistroRecetaServicio`.
4. Esta fase **no** implementa pantallas ni consultas de ranking; solo confirma que los datos necesarios ya están en persistencia.
