# Invariantes JSON — Fase 1B

Documento de referencia (solo lectura). Implementación en código:

- [`app/core/services/diagnostico_invariantes.py`](../app/core/services/diagnostico_invariantes.py)
- Visible en Configuración → Diagnóstico técnico → «Invariantes JSON / anulaciones»

Los tests de anulación (Fase 1A) viven en `tests/test_anulacion_*_fase1a.py` y **no** forman parte de este módulo.

## Invariantes mínimas

1. FIFO consume lotes en orden `(fecha_compra, id)`; lotes anulados no entran.
2. No debe haber stock restante negativo en lotes activos.
3. Consumos nuevos persisten `consumos_lote`; la anulación repone exactamente esos lotes.
4. Históricos sin trazabilidad suficiente: anulación automática **bloqueada**.
5. Merma conserva `lote_id` cuando existe; sin `lote_id` → anulación bloqueada.
6. Ajuste cambia `cantidad_restante`; no reescribe cantidad/precio/fecha de compra.
7. Compra anulada: `cantidad_restante = 0`; conserva cantidad y precio originales.
8. Soft-delete: `anulado=true` + motivo; no borrado físico.
9. IDs únicos en el JSON (sin duplicados de producto/lote/registro/merma).
10. Datos antiguos siguen cargando (campos aditivos ausentes → default).

## Fuera de alcance Fase 1B

- Corregir o backfill automático.
- Nuevos módulos de dominio.
- Cambios de UI fuera del bloque de diagnóstico.
