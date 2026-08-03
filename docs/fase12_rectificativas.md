# Fase 12 — Rectificativas documentales

**Estado:** implementada. **Sin búsqueda/exportación (F13). Sin OCR.**

## Alcance

| Pieza | Estado |
|-------|--------|
| `TipoDocumento.RECTIFICATIVA` | Hecho |
| `EstadoDocumento.RECTIFICADO` | Hecho |
| `documento_rectificado_id` / `motivo_rectificacion` | Hecho |
| Copia de líneas del original (sin edición silenciosa) | Hecho |
| Confirmación: reverso stock + original → rectificado | Hecho |
| Bloqueo si lote parcialmente consumido | Hecho |
| Una rectificativa confirmada por original | Hecho |
| Confirmada = append-only (no anular) | Hecho |
| UI Stock → Rectificativas | Hecho |
| Búsqueda / exportación documental | **F13** |

## Invariantes

1. No se edita el original confirmado; se emite rectificativa.
2. Rectificación total: debe cubrir todas las líneas del original.
3. Líneas sin lote (p.ej. conciliación factura) → solo metadatos.
4. JSON antiguo sin campos nuevos → `None` / sin impacto.

## Versión

`BM-V.2 · Ledger · Proveedores · Archivos · Albaranes · Facturas · Rectificativas`
