# Contratos de backend para UI Flet

Describe qué debe llamar Flet. Verticales: Terminal Restaurante y Terminal Inventario.

## Composition root

```python
from app.bootstrap import configure_for_flet, get_container, AppContainer

configure_for_flet()                      # demo / BM_DEMO_FILE
configure_for_flet(data_path=ruta_tmp)    # tests con JSON temporal
```

Puertos: `AppDataStore`, `BasketStore`, `AuthSessionStore`, `IdempotencyStore`, `Clock`.

Stores Flet: `FileBackedAppDataStore` + `MemoryBasketStore` + `MemoryAuthSessionStore` + `MemoryIdempotencyStore`.

## deny_terminal (B5)

`require_usecase(..., deny_terminal=True)` bloquea `actor_type=terminal` salvo:

- `terminal_id == terminal_inventario` **y**
- permiso ∈ {`ACCEDER_INVENTARIO`, `ACCEDER_TERMINAL_INVENTARIO`}.

Así Terminal Inventario puede ejecutar ajustes/alertas; Restaurante y terminales genéricos no.  
Compras/config/gestor/costes siguen denegados por bloqueo de `terminal_id` en sesión.

## Casos de uso / servicios reutilizables (entrypoints)

Mutación:

- Terminal Restaurante: `desayuno_registro`, `comida/cena/bebida_service.servicio`
- Terminal Inventario: `alert_service`, `caducidad_service`, `merma_service`, `ajuste_service`, `ubicacion_stock_service` (consulta), `traslado_service` (preview/confirm/listar), `recuento_service` (crear_borrador / preview_confirmacion / confirmar_recuento / listar_recuentos_pendientes / anular solo BORRADOR desde UI)
- Anulaciones de traslados / anulación de recuentos **confirmados** / compras: existen en núcleo; fuera del shell Flet Inventario actual
- Recuentos Flet: preview inicial **solo en memoria** (no llama a `crear_borrador`). Confirmar = `crear_borrador` + comparación de esperado + `confirmar_recuento` (operaciones separadas; sin transacción conjunta). Sin `clave_idempotencia` de sesión; `_confirmando` es anti doble clic local.
- Continuidad: `backup_service`, `restore_backup_service`

Consulta: analitica/costes/dashboard exigen `CONSULTAR_COSTES`.

Borradores: `MotorCesta` + `BasketStore`; cesta merma `bm_cesta_merma`; tokens de idempotencia.

## Autorización

- Frontera: `require_usecase` / `require_permiso` (no solo UI).
- Inventario por `terminal_id`: deniega economía/config/gestor/compras.
- Entrada Flet: `session_bridge.enter_terminal_restaurante` / `enter_terminal_inventario`.
- Admin operativa: `session_bridge.login_administracion(login, password)` → usuario con `ACCEDER_CONFIGURACION` (`terminal_id=None`). Mutaciones de responsables vía `merma_service` + `deny_terminal=True`.
- Launcher: `attach_launcher` / `main_launcher` — selección de destino **sin** autenticar; hace `logout` antes de montar el shell del destino. `BM_FLET_TERMINAL=launcher|restaurante|inventario|administracion`.

## Qué no copiar de Streamlit

Widgets, `session_state`, adaptadores Streamlit, columnas de coste, FIFO en la vista.

## Persistencia

JSON vía `AppDataStore`. Cestas Flet en memoria. Confirmaciones sí persisten.
