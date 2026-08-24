# Entrega — Compras Inventario Noray (sin commit)

Fecha: 2026-08-24  
Plan: `compras_inventario_noray_*.plan.md`  
Rama: `main` (ahead de origin; **sin commit/push** en esta entrega)

## Fase 0 — Baseline / backup
- Subset compras+inventario: OK previo a cambios.
- Backup verificable (copia JSON + SHA):
  - `docs/exports/backups_noray/demo_20260824_135730.json` — SHA `D1FC23F0…7973` (canónico)
  - `docs/exports/backups_noray/hotel_local_20260824_135730.json` — SHA `BE38E795…83F7`
- Instrumentación debug (`#region agent log`, `debug-ec0c23.log`) eliminada.

## Fase 1 — Dominio
| Cambio | Dónde |
|--------|--------|
| Stock mixto factura (línea) | `compra_registro_service._aplicar_confirmacion` |
| Pendiente qty / situaciones / diferencias | `compra_pendientes_service.py` (nuevo) |
| Líneas libres = residual > 0 | `compra_grid_helpers.lineas_libres_albaran` / `expandir_*` |
| Tests | `test_b1_b3` (mixta), `test_compra_pendientes` |

## Fase 2–3 — Presenter / UI
- Espacios: `compras_panel` … `compras_historial` + ops.
- Grid editable + `on_update_linea` cableado.
- Panel KPIs, pendientes, conciliación (consulta).
- Archivos: `inventory_viewmodels.py`, `inventory_document_viewmodels.py`, `inventario_economato_mixin.py`, `inventario_economato_view.py`, `app_shell_inventario.py`, `inventario_shell_view.py`, presenter etiquetas.

## Fase 4 — Tests (verificado en entrega)
`python -m unittest` subset B1/pendientes/grid/economato/B5/architecture/terminal_inventario → **92 OK**.  
Demo canónico: **match** `D1FC23F0…7973`.

## Limitaciones
- Sin RBAC fino por acción (Ver/Confirmar/Anular).
- Pegado Excel multi-fila no garantizado en Flet (import/expandir albaranes sí).
- Admin/Streamlit siguen como fallback con banner.

## Cómo probar
```bash
python -m app.presentation.flet.main_inventario
```
Nav: Panel → Nuevo albarán / Nueva factura (grid) → Pendientes → Documentos.
