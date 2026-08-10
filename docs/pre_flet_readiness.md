# Pre-Flet readiness — BM-V.2 (tras preparación arquitectónica)

Documento actualizado tras desacoplar AppData / auth / cestas / idempotencia de Streamlit.

## Estado de referencia

- Rama: `main`
- Persistencia: JSON vía `AppDataStore` (composition root) + adjuntos
- UI: Streamlit (`app/main.py` → `configure_for_streamlit()`)
- Núcleo: `app/core/services/*`, `app/core/application/*`, `app/core/models/*`
- Adaptadores Streamlit: `app/presentation/streamlit/adapters.py`

## Arquitectura funcional actual

```
UI Streamlit → servicios / casos de uso → AppContext / UoW → AppDataStore → JSON
                    ↘ inventory_batch (FIFO) → movimientos
```

Composition: `app/bootstrap.py` (Streamlit / tests / futura Flet).

## Módulos reutilizables (sin Streamlit)

Todos los de `app/core/services` (tras extracción de cestas).
Puertos: `AppDataStore`, `BasketStore`, `AuthSessionStore`, `IdempotencyStore`.

## Dependencias directas de Streamlit (solo presentación)

- `app/presentation/streamlit/adapters.py`
- `app/pages/*`, `app/ui/*`
- Shim documentado: `app/core/storage/session_store.py` (delega en bootstrap)

## session_state (solo adaptadores / UI)

| Clave | Store |
|-------|-------|
| `bm_data` | StreamlitAppDataStore |
| `bm_auth_session` | StreamlitAuthSessionStore |
| `bm_cesta_*` / merma | StreamlitBasketStore |
| `*_clave_idempotencia` | StreamlitIdempotencyStore |
| nav / espacio | solo UI |

## Decisiones de dominio (sin cambio)

Otros consumos = PRODUCTO_DIRECTO; caducidad = merma EXPIRACION; ajustes compensatorios;
coste_general = 4 buckets; bebidas transversales aparte.

## Autorización

Terminal Inventario deniega economía en `require_permiso` / `session_tiene_permiso` por `terminal_id`
(no solo ocultando widgets).

## Docs relacionados

- `docs/architecture_boundaries.md`
- `docs/flet_backend_contracts.md`
- `docs/streamlit_manual_regression.md`
- `docs/persistence_decision.md`

## Criterio para empezar Flet

- Este documento + contracts leídos.
- Suite verde + guard arquitectónico.
- Checklist manual regresión OK.
- Persistencia multi-terminal decidida (doc; no obligatoria para piloto Flet lectura/registro).
