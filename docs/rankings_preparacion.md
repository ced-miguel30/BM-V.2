# Preparación para rankings y análisis multi-categoría

Documentación actualizada en **Fase 1 analítica**. No hay UI de rankings/Dashboard en esta fase.

## Snapshots históricos

Al registrar (desayuno, comida, cena, bebidas) se persisten:

| Campo | Dónde |
|---|---|
| `es_bebida_snapshot` | `LineaDetalleOrigen` |
| `categoria_receta_snapshot` | `LineaDetalleOrigen` (si hay receta) y `registros_recetas` |

**Lectura:** snapshot si existe → si no, catálogo vivo (registros antiguos reconstruidos).

## Familias de eventos

| Familia | API | Uso |
|---|---|---|
| `eventos_receta` | `iter_eventos_receta` | Porciones, frecuencia, rankings de recetas (`coste=None`) |
| `eventos_producto` | `iter_eventos_producto` | Cantidad, coste real, ingredientes, extras, bebidas |

Nunca sumar coste de receta + ingredientes en la misma métrica agregada.

## Buckets de desayuno (coste = líneas de detalle)

Prioridad:

1. Si `categoria_receta_snapshot == bebidas` → toda la línea a `bebida_en_desayuno`.
2. Si no, clasificar con `es_bebida_snapshot`.
3. Directos/extras → `es_bebida_snapshot`.

```
desayuno_total = desayuno + bebida_en_desayuno + sin_desglose_historico
```

- Con detalle completo: `sin_desglose_historico = 0` y A+B = coste del registro.
- Sin `lineas_detalle`: importe en `sin_desglose_historico`.

## Categorías Dashboard (excluyentes)

```
coste_general =
  desayuno_total
  + comida_total
  + cena_total
  + bebidas_independientes
```

`bebidas_independientes` = solo `tipo_servicio=bebidas`. Las bebidas dentro de desayuno/comida/cena son clasificación transversal (`bebida_en_*`), no categoría Dashboard aparte.

## Valores de origen (`OrigenConsumo`)

- `producto_directo`
- `ingrediente_receta`
- `extra_receta`

## Limitaciones reales

1. Registros sin `lineas_detalle` → solo `sin_desglose_historico`.
2. Sin snapshot → reconstrucción vía catálogo vivo (puede divergir si el catálogo cambió).
3. Merma aún sin vínculo a servicio (gestor merma en fases posteriores).
4. Inventario sigue siendo **FIFO**.
