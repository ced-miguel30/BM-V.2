# Ledger de movimientos — modo espejo (Fase 7A · completa)

Documento vivo. **Fase 7A cerrada** en modo espejo.

## Estado

| Aspecto | Estado |
|---------|--------|
| Modelo + persistencia | **Hecho** |
| Dual-write lote / ajustes | **Hecho (7A.2)** |
| Dual-write merma / anulación merma | **Hecho (7A.3)** |
| Dual-write consumos / anulación registro | **Hecho (7A.4)** |
| Dual-write anulación de compra/entrada | **Hecho (7A.4)** |
| Ledger como fuente de verdad | **No** (futura 7B) |

**Fuente de verdad del stock:** `LoteStock.cantidad_restante`.  
**FIFO:** sin cambios.  
**Versión:** `BM-V.2 · Ledger espejo completo`.

Mensaje operativo:

```text
Ledger en modo espejo; stock calculado desde lotes.
```

## Tipos de movimiento

| Tipo | Dirección | Origen típico |
|------|-----------|---------------|
| `entrada_compra` | entrada | `lote` |
| `ajuste_entrada` / `ajuste_salida` | ± | `ajuste` |
| `merma` | salida | `merma` |
| `reversion_merma` | entrada | `anulacion_merma` / `anulacion_merma_historica` |
| `consumo` | salida | `desayuno` / `registro_servicio` |
| `reversion_consumo` | entrada | `anulacion_registro` / `anulacion_registro_historica` |
| `reversion_entrada` | salida | `anulacion_compra` / `anulacion_compra_historica` |

Cantidad siempre > 0. Identidad de línea sin IDs en modelos:

- Merma: `lnNN`
- Consumo: `detNN:fragNN`

## Principios

1. Append-only; correcciones = reversiones.
2. Espejo complementario; no calcula stock operativo.
3. Idempotencia por clave origen+línea+lote+tipo.
4. Atomicidad: fallo del espejo revierte lotes, registros, flags, actividades y movimientos.
5. Sin backfill. Históricos sin movimiento → cobertura parcial; anulaciones pueden generar reverso histórico sin inventar la salida original.

## Reconciliación

Informativa: entradas, consumos, mermas, ajustes, reversos, saldo teórico vs `cantidad_restante`, cobertura. **Nunca** modifica stock.

## Limitaciones actuales

- Sin stock por ubicación, traslados, recuentos, préstamos, documentos.
- Cobertura histórica parcial esperable.
- Diagnóstico no auto-corrige.

## Fase 7B (futura, no implementar)

Condiciones previas:

1. Dual-write estable en producción (7A completa).
2. Reconciliación sin divergencias sistemáticas en datos **nuevos**.
3. Política explícita para histórico pre-ledger.
4. Decisión de producto + periodo de convivencia.
5. Invariantes testados stock(lote) = Σ firmados post-activación.
6. Plan de rollback que no recalcule lotes borrando movimientos.

7B podría abordar: ledger como fuente de verdad, stock por ubicación, traslados, etc.
