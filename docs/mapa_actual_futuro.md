# Mapa modelo actual → modelo futuro

Fuente actual: `AppData` + JSON `data/demo/datos_hotel.json`.  
Futuro: dominio documentado en [modelo_dominio_objetivo.md](modelo_dominio_objetivo.md).

## Tabla de correspondencia

| Actual (código) | Futuro (concepto) | Estrategia |
|-----------------|-------------------|------------|
| `Producto` | Producto maestro | Ampliar campos aditivos; no renombrar a la ligera |
| `categoria_inventario` | Texto histórico / libre | **Conservar tal cual**; no sustituye `categoria_id` |
| `categoria_id` / `subcategoria_id` | Categoría / Subcategoría | **Fase 6A hecha** |
| `departamento_ids` | Departamentos de uso | **Fase 6A hecha** — no es ubicación ni stock |
| `ubicacion_ids` | Ubicaciones permitidas/habituales | **Fase 6B hecha** — sin cantidades |
| `tipo_articulo` | Tipo de artículo | **Fase 6C hecha** — enum fijo; sin backfill |
| `es_bebida` | Flag de catálogo bebida | **Independiente** de `tipo_articulo` |
| `servicios_disponibles` | Servicios disponibles | Conservar semántica vacío ≠ todos |
| `LoteStock` | Lote | Soft-anulación; enlace documental futuro |
| `marca_proveedor` | Snapshot texto proveedor | Conservar; Proveedor maestro en F8 |
| `Departamento`, `Categoria`, `Subcategoria` | Catálogos 6A | Completados |
| `Ubicacion` | Maestro ubicaciones 6B | Completado (sin stock por ubicación) |
| `TipoArticulo` | consumible / reutilizable | **6C**; otros tipos = esbozo P03 |
| *(no existe)* | Stock cuantitativo por ubicación | P02 → F7 |
| *(no existe)* | Herramienta/préstamo, textil, activo | P03 futuro |
| *(no existe)* | Proveedor, Impuesto | **F8** |
| *(no existe)* | Movimiento (ledger) | **F7 (siguiente)** |

## Tipos de artículo (6C)

| Tipo | Significado (clasificación) | Operativa completa |
|------|----------------------------|--------------------|
| Consumible | Se utiliza/agota en la operación | Ya cubierta por consumo/merma actuales |
| Reutilizable | Permanece y se reutiliza | **Aplazada** (préstamo/retorno/baja → ledger) |

Históricos sin campo → `tipo_articulo=None` («Sin clasificar»). Sin conversión automática a consumible.  
No derivar el tipo desde `es_bebida`, categoría, depto ni ubicación.

## Dimensiones 6A / 6B / 6C

| Concepto | Significado |
|----------|-------------|
| Departamento | Ámbito de **uso** operativo |
| Ubicación | Lugar donde puede **existir** inventario |
| Tipo de artículo | Naturaleza consumible vs reutilizable (taxonomía fija) |
| Stock hotel | Σ `cantidad_restante` de lotes (sin cambio en 6C) |

## Próximo paso

**Fase 7** — ledger de movimientos (tras aprobación de 6C).
