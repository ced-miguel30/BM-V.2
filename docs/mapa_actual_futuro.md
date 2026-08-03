# Mapa modelo actual → modelo futuro

Fuente actual: `AppData` + JSON `data/demo/datos_hotel.json`.  
Futuro: dominio documentado en [modelo_dominio_objetivo.md](modelo_dominio_objetivo.md).

## Tabla de correspondencia

| Actual (código) | Futuro (concepto) | Estrategia |
|-----------------|-------------------|------------|
| `Producto` + catálogos 6A–6C | Producto maestro | Completados |
| `LoteStock.cantidad_restante` | Espejo / legacy | Conservado; no eliminado en 7B |
| `MovimientoInventario` | Ledger | **7A espejo + 7B SoT configurable** |
| Dual-write ops → ledger | Espejo automático | Entradas, ajustes, mermas, consumos, anulaciones, traslados, recuentos |
| `ledger_balance_mode` | legacy / shadow / ledger | Default `shadow`; `ledger` activable |
| Saldos por ubicación (derivados) | Stock por ubicación | 7B.3 — sin materializar en Producto |
| `traslado` | Traslado entre ubicaciones | 7B.4 |
| `SesionRecuento` | Recuento físico | 7B.6 → ajustes |
| Proveedor / Impuesto / RelacionProductoProveedor | Catálogo comercial | **Fase 8** |
| `marca_proveedor` (lote) | Snapshot textual histórico | Conservado; no se reescribe |
| *(no aún)* | Albarán / factura / conciliación | **F9+** |

## Próximo paso

**Fase 9+** — flujo documental (albarán → entrada → factura). No iniciar sin revisión de F8.
