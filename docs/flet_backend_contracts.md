# Contratos de backend para UI Flet

Describe qué debe llamar Flet. La primera vertical (Terminal Restaurante) ya consume estos contratos.

## Composition root

```python
from app.bootstrap import configure_for_flet, get_container, AppContainer

configure_for_flet()                      # demo / BM_DEMO_FILE
configure_for_flet(data_path=ruta_tmp)    # tests con JSON temporal
```

Puertos: `AppDataStore`, `BasketStore`, `AuthSessionStore`, `IdempotencyStore`, `Clock`.

Stores Flet: `FileBackedAppDataStore` + `MemoryBasketStore` + `MemoryAuthSessionStore` + `MemoryIdempotencyStore`.

## Casos de uso / servicios reutilizables (entrypoints)

Mutación (ya con `require_usecase` donde aplica):

- Registro Terminal Restaurante (piloto Flet):
  - `desayuno_service.desayuno_registro` (Desayuno; storage `desayunos[]`)
  - `comida_service.servicio` / `cena_service.servicio` / `bebida_service.servicio`
- Merma / caducidad: `merma_service`, `caducidad_service` (workbench → `MotivoMerma.EXPIRACION`)
- Anulaciones: `anulacion_registro_service`, `anulacion_merma_service`, `anulacion_compra_service`, documentos
- Inventario: `ajuste_service`, `stock_service`, `traslado_service`, `recuento_service`
- Compras/docs: `compra_registro_service`, `albaran_service`, `factura_service`, …
- Catálogo: `receta_service.listar_recetas`, productos vía `productos_catalogo` del servicio
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
- Entrada Flet: `iniciar_terminal_restaurante()` + `save_auth_session` vía `session_bridge`.

## Qué no copiar de Streamlit

- Widgets, `st.rerun`, mensajes `st.success/error`
- Claves de navegación `nav_*`
- Adaptadores en `app/presentation/streamlit/`
- Cálculos FIFO o doble conteo en la capa visual

## DTOs

Resultados `ok`/`mensaje` existentes; viewmodels Flet sin campos económicos.
Entidades de `app/core/models`. No duplicar entidades solo para Flet.

## Persistencia

Sigue JSON vía `AppDataStore`. Ver `docs/persistence_decision.md`.
Cesta Flet: memoria de proceso (no se conserva tras reinicio).
Registros confirmados: sí persisten en el JSON configurado.
