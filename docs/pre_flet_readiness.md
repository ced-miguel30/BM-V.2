# Pre-Flet readiness — BM-V.2 (primera vertical Flet implementada)

Documento actualizado tras implementar **Terminal Restaurante** en Flet.

## Estado de referencia

- Rama: `main`
- Persistencia: JSON vía `AppDataStore` (composition root) + adjuntos
- UI Streamlit (referencia): `app/main.py` → `configure_for_streamlit()`
- UI Flet (piloto): `python -m app.presentation.flet.main` → `configure_for_flet()`
- Núcleo: `app/core/services/*`, `app/core/application/*`, `app/core/models/*`
- Adaptadores Streamlit: `app/presentation/streamlit/adapters.py`
- Presentación Flet: `app/presentation/flet/*`

## Arquitectura funcional actual

```
UI Streamlit ─┐
              ├→ servicios / casos de uso → AppContext / UoW → AppDataStore → JSON
UI Flet ──────┘        ↘ inventory_batch (FIFO) → movimientos
```

Composition: `app/bootstrap.py` (`configure_for_streamlit` / `configure_for_tests` / `configure_for_flet`).

## Primera vertical — resultado de gates

| Gate | Resultado |
|------|-----------|
| Composición Flet sin Streamlit | OK |
| Presenter auth / cesta / confirmación | OK |
| Idempotencia / persistencia temporal | OK |
| Seguridad económica (VM + usecase) | OK |
| Guard arquitectónico Flet | OK |
| `python run_tests.py` | Verde tras vertical |
| `python run_browser_tests.py` | Verde (1 skip E2E Streamlit previo) |
| Demo canónico | Intacto |
| Streamlit arranque | Intacto como interfaz de referencia |

Ver detalle operativo: `docs/flet_terminal_restaurante.md`.

## Módulos reutilizables (sin Streamlit)

Todos los de `app/core/services` (tras extracción de cestas).
Puertos: `AppDataStore`, `BasketStore`, `AuthSessionStore`, `IdempotencyStore`.

## Dependencias directas de Streamlit (solo presentación Streamlit)

- `app/presentation/streamlit/adapters.py`
- `app/pages/*`, `app/ui/*`
- Shim documentado: `app/core/storage/session_store.py` (delega en bootstrap)

## session_state (solo adaptadores Streamlit / UI Streamlit)

| Clave | Store |
|-------|-------|
| `bm_data` | StreamlitAppDataStore |
| `bm_auth_session` | StreamlitAuthSessionStore |
| `bm_cesta_*` / merma | StreamlitBasketStore |
| `*_clave_idempotencia` | StreamlitIdempotencyStore |
| nav / espacio | solo UI |

Flet usa stores en memoria inyectados por `configure_for_flet()` (sin `session_state`).

## Decisiones de dominio (sin cambio)

Otros consumos = PRODUCTO_DIRECTO; caducidad = merma EXPIRACION; ajustes compensatorios;
coste_general = 4 buckets; bebidas transversales aparte.

## Autorización

Terminal Inventario deniega economía en `require_permiso` / `session_tiene_permiso` por `terminal_id`.
Terminal Restaurante Flet: `ACCEDER_TERMINAL_RESTAURANTE` / `ACCEDER_REGISTRO`; sin `CONSULTAR_COSTES`.

## Backlog Flet (P2/P3 — no corregir en Streamlit ahora)

- Selector/localización E2E «Confirmar registro» Desayuno (skip browser actual).
- Evitar re-render completo del TextField de búsqueda en cada tecla.
- Branding / tipografía definitiva del terminal.
- Persistencia opcional de cesta no confirmada entre reinicios (hoy: no).
- Merma, anulaciones, histórico y resto de verticales.
- Empaquetado desktop / instalador (fuera de alcance actual).

## Docs relacionados

- `docs/architecture_boundaries.md`
- `docs/flet_backend_contracts.md`
- `docs/flet_terminal_restaurante.md`
- `docs/streamlit_manual_regression.md`
- `docs/persistence_decision.md`
- `docs/browser_e2e.md`
