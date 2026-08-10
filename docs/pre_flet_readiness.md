# Pre-Flet readiness — BM-V.2

## Estado

**Terminal Restaurante (primera vertical Flet): APROBADA** — técnica + validación manual.

| Campo | Valor |
|-------|--------|
| HEAD / origin/main | `a31aacd…` (baseline vertical + docs previos) |
| Persistencia | JSON vía `AppDataStore` (sin cambio) |
| UI Streamlit | Referencia intacta (`configure_for_streamlit`) |
| UI Flet | `python -m app.presentation.flet.main` → `configure_for_flet()` |
| Siguiente vertical | Terminal Inventario — **planificado, no implementado** |

## Gates de Terminal Restaurante

| Gate | Resultado |
|------|-----------|
| Tests Flet | 23 OK |
| `python run_tests.py` | 920 OK |
| `python run_browser_tests.py` | 13 OK, 1 skipped |
| Smoke Streamlit / Flet | OK |
| Demo canónico | Intacto |
| Sin backend paralelo | OK |
| Sin economía en viewmodels | OK |
| Autorización / idempotencia / persistencia | OK |
| Validación manual | **funciona** (sin incidencias P0–P3 reportadas) |

Detalle: `docs/flet_terminal_restaurante.md`.
Plan siguiente: `docs/flet_terminal_inventario_plan.md`.

## Arquitectura

```
UI Streamlit ─┐
              ├→ servicios / casos de uso → AppContext / UoW → AppDataStore → JSON
UI Flet ──────┘        ↘ inventory_batch (FIFO) → movimientos
```

Composition: `configure_for_streamlit` / `configure_for_tests` / `configure_for_flet`.

## Autorización

- Terminal Restaurante: `ACCEDER_TERMINAL_RESTAURANTE` / `ACCEDER_REGISTRO`; sin `CONSULTAR_COSTES`.
- Terminal Inventario: deniega economía/config/gestor/compras por `terminal_id` en `session_tiene_permiso` / `require_permiso`.

## Backlog Flet (P2/P3 — no tocar Streamlit)

### Conviene corregir antes o al inicio de Inventario
- Relajar o especializar `require_usecase(..., deny_terminal=True)` para que el actor `terminal_inventario` pueda mutar ajustes/alertas si entran en el alcance (hoy bloquea *cualquier* `actor_type=="terminal"`). Tratar como **precondición de dominio de la 2ª vertical**, no bug de Restaurante.
- Evitar re-render completo del `TextField` de búsqueda en cada tecla (Restaurante).

### Pueden esperar
- Selector E2E Streamlit «Confirmar registro» Desayuno (skip browser; deuda Streamlit/E2E, no Flet Restaurante).
- Branding / tipografía definitiva.
- Persistencia opcional de cestas no confirmadas entre reinicios.
- Merma/anulaciones/histórico en Restaurante; empaquetado `.exe`.
- Traslados / recuentos / stock admin completo (fuera del shell actual de Inventario).

## Docs relacionados

- `docs/flet_terminal_restaurante.md`
- `docs/flet_terminal_inventario_plan.md`
- `docs/flet_backend_contracts.md`
- `docs/architecture_boundaries.md`
- `docs/browser_e2e.md`
