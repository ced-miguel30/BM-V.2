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

## Fase 4G — anulaciones (hecha)

- `anulacion_registro|merma|compra_service` vía AppContext (reloj, actor, auditoría, UoW).
- Si la UI pasa `AppData`, el commit sigue llamando `persist_data` sobre ese objeto.
- UI sin cambios.

## Fase 4H — exportación (hecha) — **Fase 4 completa**

- `exportacion_semanal_service` vía AppContext (reloj, actor, UoW, `next_id`).
- Campos estructurados de actividad de exportación conservados.
- UI sin cambios.

### Resumen Fase 4 (A→H)

Catálogos → alertas → ajustes → merma → registro → FIFO → anulaciones → export.

## Fase 5 — espacios de trabajo (hecha)

- Lógica pura: `app/core/application/espacios.py` (sin Streamlit).
- UI: selector «Espacio de trabajo» en `render_sidebar()`; filtra secciones operativas.
- **Configuración es global y provisionalmente visible** (no es un cuarto espacio).
- Persistencia del espacio solo en `st.session_state` (`bm_espacio_trabajo`); no AppData/JSON.
- El selector **no concede permisos**; seguridad real en **Fase 16**.
- F5 **no oculta** precios ni información económica dentro de las páginas.
- La **terminal de restaurante** no se implementa en esta fase.
- Detalle: `docs/arquitectura_objetivo/espacios_trabajo.md`.
- Tests: `tests/test_fase5_espacios.py`.

## Fase 6A — catálogos de inventario (hecha)

- Modelos: `Departamento`, `Categoria`, `Subcategoria` en `catalogo.py`.
- Producto: `categoria_id`, `subcategoria_id`, `departamento_ids` (aditivos).
- `categoria_inventario` conservada; sin backfill.
- Servicio: `catalogo_service.py` vía AppContext.
- UI: Configuración → Catálogos de inventario; Stock alta/edición.

## Fase 6B — ubicaciones (hecha)

- Modelo: `Ubicacion`; Producto: `ubicacion_ids` (sin cantidades).
- Stock hotel = Σ `cantidad_restante` (sin cambio).
- P02 (stock por ubicación) aplazada a F7.

## Fase 6C — tipos de artículo (hecha)

- Enum fijo `TipoArticulo`: consumible / reutilizable (sin CRUD).
- Producto: `tipo_articulo` aditivo; históricos → `None` («Sin clasificar»).
- Alta nueva: tipo obligatorio. Sin backfill. `es_bebida` independiente.
- Cambiar tipo no altera FIFO/stock/lotes.

## Fase 7A.1 — ledger modelo (hecha)

- `MovimientoInventario` + `AppData.movimientos`; persistencia aditiva.
- Servicio espejo (validar / idempotencia / crear API interna).
- Fuente de verdad: `LoteStock.cantidad_restante`. Sin backfill.

## Fase 7A.2 — dual-write entrada/ajustes (hecha)

- `registrar_lote` → `entrada_compra`.
- `aplicar_ajuste` → `ajuste_entrada` / `ajuste_salida` según delta.

## Fase 7A.3 — dual-write merma (hecha)

- `registrar_merma` → `merma` por línea (`origen_linea_id=lnNN`).
- `anular_merma` → `reversion_merma`; histórico sin original → `anulacion_merma_historica`.
- Siguiente: **7A.4** consumos (tras aprobación).

## Siguiente: Fase 7A.4

Dual-write espejo para consumos y anulaciones de registros (`consumos_lote`).
