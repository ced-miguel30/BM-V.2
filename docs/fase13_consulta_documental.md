# Fase 13 — Búsqueda y exportación documental

**Estado:** implementada. **Sin OCR. Sin mutación de estados.**

## Alcance

| Pieza | Estado |
|-------|--------|
| Filtros: texto, tipo, estado, proveedor, fechas | Hecho |
| Búsqueda de archivos documentales | Hecho |
| Exportación CSV (`exports/documentos/`) | Hecho |
| UI Stock → Documentos | Hecho |
| Descarga CSV en navegador | Hecho |
| OCR / parseo de PDF | **No** |
| API REST | **No** |

## Invariantes

1. Solo lectura sobre documentos confirmados/borrador/etc.; no confirma ni anula.
2. CSV con BOM UTF-8; una fila por línea documental.
3. JSON antiguo sin documentos → lista vacía.
4. No sobrescribe exportaciones previas (nombre con timestamp).

## Versión

`BM-V.2 · … · Rectificativas · Documentos`
