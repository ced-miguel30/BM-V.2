# Mapa modelo actual → modelo futuro

Fuente actual: `AppData` + JSON `data/demo/datos_hotel.json`.  
Futuro: dominio documentado en [modelo_dominio_objetivo.md](modelo_dominio_objetivo.md).

## Tabla de correspondencia

| Actual (código) | Futuro (concepto) | Estrategia |
|-----------------|-------------------|------------|
| `Producto` + catálogos 6A–6C | Producto maestro | Completados |
| `LoteStock.cantidad_restante` | Stock operativo | **Fuente de verdad vigente** |
| `MovimientoInventario` | Ledger espejo | **Fase 7A completa** |
| Dual-write ops → ledger | Espejo automático | Entradas, ajustes, mermas, consumos, anulaciones |
| *(no aún)* | Ledger = fuente de verdad | **Fase 7B** (tras aprobación) |
| *(no existe)* | Stock por ubicación / traslados | 7B+ |
| *(no existe)* | Proveedor, Impuesto, documentos | **F8+** |

## Próximo paso

**Fase 7B** — solo tras aprobación explícita. Ledger sigue siendo espejo hasta entonces.
