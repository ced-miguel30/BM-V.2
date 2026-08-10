# Contratos de backend para futura UI Flet

**No instala ni migra Flet.** Describe qué debe llamar Flet.

## Composition root

```python
from app.bootstrap import configure_for_tests, get_container, AppContainer
# Futuro: configure_for_flet() con los mismos puertos
```

Puertos: `AppDataStore`, `BasketStore`, `AuthSessionStore`, `IdempotencyStore`, `Clock`.

## Casos de uso / servicios reutilizables (entrypoints)

Mutación (ya con `require_usecase` donde aplica):

- Registro: `desayuno_service`, `servicio_registro_service` / wrappers comida·cena·bebidas
- Merma / caducidad: `merma_service`, `caducidad_service` (workbench → `MotivoMerma.EXPIRACION`)
- Anulaciones: `anulacion_registro_service`, `anulacion_merma_service`, `anulacion_compra_service`, documentos
- Inventario: `ajuste_service`, `stock_service`, `traslado_service`, `recuento_service`
- Compras/docs: `compra_registro_service`, `albaran_service`, `factura_service`, …
- Catálogo: `receta_service`, productos vía `stock_service`
- Continuidad: `backup_service`, `restore_backup_service`

Consulta:

- `historial_operativo_service`
- `analitica_consumo_service`, `costes_service`, `dashboard_service` (**exigen CONSULTAR_COSTES**)
- `alert_service`, exportaciones

Borradores:

- `MotorCesta` + `BasketStore`
- Cesta merma vía `BasketStore` (`bm_cesta_merma`)
- `current_idempotency_token` / `rotate_idempotency_token`

## Autorización

- No basta ocultar UI: `require_usecase` / `require_permiso`.
- Terminal Inventario (`terminal_id=terminal_inventario`): deniega `CONSULTAR_COSTES`, config, gestor, compras aunque el rol base sea administración.
- Restaurante: sin `CONSULTAR_COSTES` en matriz (sin cambio de matriz).
- Actor en operaciones: `AppContext.actor` / snapshots de auditoría.

## Qué no copiar de Streamlit

- Widgets, `st.rerun`, mensajes `st.success/error`
- Claves de navegación `nav_*`
- Adaptadores en `app/presentation/streamlit/`
- Cálculos FIFO o doble conteo en la capa visual

## DTOs

Resultados `ok`/`mensaje` existentes; entidades de `app/core/models`. No hace falta duplicar entidades solo para Flet.

## Persistencia

Sigue JSON vía `AppDataStore`. Ver `docs/persistence_decision.md`.
