# Fase 11 — Facturas + conciliación

**Estado:** implementada. **Sin rectificativas (F12). Sin OCR.**

## Alcance

| Pieza | Estado |
|-------|--------|
| `TipoDocumento.FACTURA` | Hecho |
| Conciliación línea ↔ albarán confirmado | Hecho (metadatos) |
| Sin incremento de stock al conciliar | Hecho (D06 / P04) |
| Factura directa → lote + `entrada_factura` | Hecho |
| Una línea de albarán = una factura confirmada | Hecho |
| Anulación (libera enlace / reverso stock directa) | Hecho |
| UI Stock → Facturas | Hecho |
| Rectificativas | **Hecho** |

## Decisiones cerradas

- **P04:** conciliación = solo metadatos; sin movimiento neutro en ledger.
- ID técnico (`docNN`) ≠ `referencia_externa` del proveedor.

## Invariantes

1. Conciliar no crea lotes ni movimientos.
2. Confirmación atómica en líneas de factura directa.
3. No doble conciliación de la misma línea de albarán mientras la factura esté confirmada.
4. Anular factura confirmada con stock parcial en líneas directas → bloqueo.

## Versión

`BM-V.2 · Ledger · Proveedores · Archivos · Albaranes · Facturas`
