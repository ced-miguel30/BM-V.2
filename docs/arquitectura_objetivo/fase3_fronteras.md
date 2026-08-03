# Fronteras de aplicación — Fase 3

**Implementado en código** bajo `app/core/application/`.  
**No** elimina `session_store`. **No** cambia la UI.

## Piezas

| Pieza | Módulo |
|-------|--------|
| Reloj | `clock.py` (`SystemClock`, `FixedClock`) |
| Actor | `actor.py` |
| IDs | `id_generator.next_id` (mismo algoritmo que servicios) |
| UoW | `InMemoryUnitOfWork`, `JsonSessionUnitOfWork` → `session_store` |
| Contexto | `AppContext` / `build_app_context` / `data_service.get_app_context` |
| Puerto productos | `ports/producto_repository.py` |
| Adaptador JSON | `adapters/json_producto_repository.py` |
| Piloto lectura | `producto_queries.py` |
| Auditoría | `auditoria.registrar_actividad` |

## Piloto (Fase 3)

Lectura de productos vía `listar_productos` / `obtener_producto` / `mapa_productos_nombre_id`.

## Fase 4A — catálogos (hecha)

- `stock_service.mapa_productos` / `mapa_bebidas` delegan en AppContext + puerto (mismo orden/filtro legacy).
- `DataRepository.get_producto` usa `JsonProductoRepository`.
- `stock_service._next_id` usa `application.id_generator.next_id`.
- UI sin cambios.

## Fase 4B — alertas (hecha)

- `alert_service` usa AppContext: UoW (`commit`), `clock.today()`, actor, `auditoria`, `next_id`.
- Firmas públicas iguales; callers de UI no cambian.
- Fecha de desayuno «hoy» inyectable vía reloj (tests con `FixedClock`).

## Fase 4C — ajustes (hecha)

- `ajuste_service` vía AppContext: UoW, `clock`, actor, auditoría, `next_id`.
- `sincronizar_alertas(ctx)` tras aplicar.
- UI sin cambios (kwargs `ctx` opcionales).

## Fase 4D — merma (hecha)

- `merma_service` vía AppContext; UoW compat parcheable (`get_data`/`persist_data` del módulo).
- Cesta sigue en `st.session_state` (borde UI).
- UI sin cambios.

## Fase 4E — registro servicio / desayuno (hecha)

- `desayuno_service` y `servicio_registro_service` vía AppContext (CompatUoW parcheable).
- Cestas siguen en `st.session_state`.
- UI sin cambios.

## Fase 4F — FIFO (hecha)

- `inventory_batch_service` sigue puro sobre `AppData` (orden FIFO intacto).
- Nuevo `application/inventory_ops.py`: wrappers con AppContext.
- Desayuno / registro de servicio aplican descuento vía `inventory_ops`.
- UI sin cambios.

## Siguiente subfase (4G)

Anulaciones → contexto (STOP tras 4G).

## Streamlit

Humo opcional: un registro que descuente stock. Validación UI clave: **Fase 5**.
