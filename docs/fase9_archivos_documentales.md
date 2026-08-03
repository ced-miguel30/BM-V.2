# Fase 9 — Archivos documentales

**Estado:** implementada. **Sin OCR. Sin albaranes/facturas.**

## Alcance

| Pieza | Estado |
|-------|--------|
| `ArchivoDocumental` | Hecho |
| Escritura única en `data/documentos/{id}/` | Hecho |
| SHA-256 + verificación | Hecho |
| Soft-desactivar (fichero conservado) | Hecho |
| UI Configuración → Archivos documentales | Hecho |
| Deduplicación por hash activo | Hecho |
| Enlace `documento_id` (preparación F10) | Hecho (metadato) |
| OCR / auto-confirmación | **No** |
| Albarán → stock | **F10** |

## Invariantes

1. El original en disco no se modifica tras el alta.
2. JSON antiguo sin `archivos_documentales` → `[]`.
3. No se interpreta el contenido del archivo.
4. IDs técnicos (`adocNN`); no proveedor+fecha.

## Versión

`BM-V.2 · Ledger · Archivos documentales`
