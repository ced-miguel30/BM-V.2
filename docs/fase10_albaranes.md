# Fase 10 — Albaranes → entrada de inventario

**Estado:** implementada. **Sin facturas ni conciliación (F11).**

## Alcance

| Pieza | Estado |
|-------|--------|
| `Documento` / `LineaDocumento` / estados | Hecho |
| `TipoMovimiento.ENTRADA_ALBARAN` | Hecho |
| Borrador → líneas → confirmación atómica | Hecho |
| Lotes + movimientos ledger | Hecho |
| Anulación con `reversion_entrada` | Hecho (bloquea si lote parcialmente consumido) |
| Enlace a `ArchivoDocumental` | Hecho |
| UI Stock → Albaranes | Hecho |
| Factura / conciliación | **Hecho** |
| OCR | **No** |

## Invariantes

1. Confirmación atómica: si falla una línea, no quedan lotes/movimientos parciales.
2. ID técnico (`docNN`) ≠ `referencia_externa` del proveedor.
3. Snapshots de proveedor/impuesto/producto en cabecera y líneas.
4. JSON antiguo sin `documentos` → `[]`.
5. Compra manual por lote (pestaña Compras) sigue existiendo; albarán es el camino documental.

## Versión

`BM-V.2 · Ledger · Proveedores · Archivos · Albaranes`
