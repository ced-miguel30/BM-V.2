# Límites arquitectónicos BM-V.2

## Capas

| Capa | Ubicación | Puede | No puede |
|------|-----------|-------|----------|
| Dominio | `app/core/models` | entidades, enums, invariantes | Streamlit, páginas, UI, I/O |
| Aplicación | `app/core/application` | puertos, UoW, reloj, actor, idempotencia | Streamlit, `app.pages`, `app.ui`, `app.presentation` |
| Servicios reutilizables | `app/core/services` | reglas de negocio, orquestación | `session_state`, `import streamlit` |
| Infraestructura | `app/core/storage`, `app/data`, adapters memoria | JSON, disco, hashing | widgets |
| Presentación Streamlit | `app/pages`, `app/ui`, `app/presentation/streamlit` | widgets, `session_state`, traducir Resultado→mensaje | FIFO, persistir JSON crudo, autorizar solo con ocultar UI |
| Composición | `app/bootstrap.py` | cablear stores para Streamlit / tests / futura Flet | lógica de dominio |

## Dependencias permitidas

```
presentation → application / services / bootstrap
services → models / application / storage (vía UoW o shim)
application → models / ports
presentation/streamlit/adapters → streamlit + ports
```

## Dependencias prohibidas

- `app.core.models` → Streamlit / pages / ui / presentation
- `app.core.application` → Streamlit / pages / ui / presentation
- `app.core.services` → `session_state` / Streamlit
- Páginas escribiendo `datos_hotel.json` o `json.dump` de negocio

## Flujo comando

```
UI → servicio / caso de uso (require_usecase)
   → AppContext / UnitOfWork
   → AppDataStore.persist
   → JSON (demo_files)
```

## Flujo consulta

```
UI → servicio de lectura (con permiso si económico)
   → AppDataStore.get / DataRepository
   → DTOs / dicts de presentación
```

## Composición

- `configure_for_streamlit()` — adaptadores `st.session_state`
- `configure_for_tests` / `build_default_container()` — memoria / file-backed sin UI
- `get_container()` — una sola fuente de AppData por proceso

## Excepciones temporales documentadas

| Excepción | Motivo | Retirada |
|-----------|--------|----------|
| `session_store.py` shim | Compat `get_data`/`persist_data` | cuando callers usen solo bootstrap |
| `app/ui/compra_grid_helpers.py` | Helpers **puros** ubicados bajo `ui/` | mover a `services` cuando se toque compras |
| Settings → `get_demo_file` | Backup/restore necesita ruta efectiva | encapsular en servicio de continuidad |

Guard automático: `tests/test_architecture_boundaries.py`.
