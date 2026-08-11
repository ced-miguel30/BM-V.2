# Pre-Flet readiness — BM-V.2

## Estado

| Vertical | Estado |
|----------|--------|
| Terminal Restaurante | **APROBADA** (técnica + historial/anulación) |
| Terminal Inventario | **APROBADA** (técnica + manual) |
| Consolidación UX Flet | **APROBADA** (técnica + manual) |
| Administración operativa Flet | **APROBADA** — maestros, compras, docs, backup |
| Launcher Flet | **APROBADO** (técnica + manual) |
| Empaquetado PyInstaller | **Prototipo** (`dist/BM-Launcher`, no en Git) |

| Campo | Valor |
|-------|--------|
| Composition Flet | `configure_for_flet()` (única) |
| UI Streamlit | Referencia / compatibilidad |
| Arranque Restaurante | `python -m app.presentation.flet.main` |
| Arranque Inventario | `python -m app.presentation.flet.main_inventario` |
| Arranque Administración | `python -m app.presentation.flet.main_administracion` |
| Arranque launcher | `python -m app.presentation.flet.main_launcher` |
| Go-live | `docs/operations_go_live.md` |

## Autorización B5 / Admin

`deny_terminal=True` bloquea actores `terminal` excepto:

- allowlist Inventario operativa (`ACCEDER_INVENTARIO` / `ACCEDER_TERMINAL_INVENTARIO`);
- excepciones **explícitas por llamada** vía `allowed_terminals` (hoy: anulación de
  registros con `terminal_restaurante` + `ACCEDER_REGISTRO`).

`ACCEDER_CONFIGURACION` exige usuario Dir/Adm (`terminal_id=None`).

## Backlog Flet

### Resuelto
- Restaurante completo (registro + historial + anulación, sin economía).
- Inventario operativo (alertas, merma, stock, traslados, recuentos, ajustes).
- Admin Flet: productos, recetas, usuarios, responsables, proveedores, compras,
  documentos (consulta), inventario inicial, backup/restore, configuración.
- Launcher + volver al menú.
- P3 integrada automática (`tests/test_flet_p3_integrada.py`).
- PyInstaller onedir + runtime hook a `%LOCALAPPDATA%\BM-V2-local`.

### Pueden esperar
- Branding definitivo.
- Dashboard ejecutivo Flet / zona de peligro completa.
- Firma Authenticode / MSI.
- Piloto físico hotel.
- Anulación de traslados / recuentos confirmados en Flet.

## Siguiente bloque

**Cargar productos y recetas reales** según `docs/operations_go_live.md`.

## Docs

- `docs/operations_go_live.md`
- `docs/flet_administracion_operativa.md`
- `docs/flet_terminal_restaurante.md`
- `docs/flet_terminal_inventario.md`
- `docs/flet_launcher.md`
- `docs/flet_packaging_plan.md`
- `docs/deploy_local_p1.md` / `p2.md`
- `docs/flet_backend_contracts.md`
