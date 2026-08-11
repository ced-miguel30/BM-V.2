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
- permiso ∈ {`ACCEDER_INVENTARIO`, `ACCEDER_TERMINAL_INVENTARIO`}; **o**
- un `terminal_id` pasado explícitamente en `allowed_terminals` **para esa llamada**
  (el permiso exigido sigue siendo obligatorio).

Sin `allowed_terminals`, el comportamiento por defecto es idéntico al histórico:
Inventario operativo sí; Restaurante y terminales genéricos no (salvo la excepción
acotada abajo). Compras/config/gestor/costes siguen denegados por matriz de rol /
`terminal_id`.

### Anulación de registros (Restaurante)

`anulacion_registro_service.anular_registro` conserva `deny_terminal=True` y añade:

`allowed_terminals={TERMINAL_ID_DEFAULT}` (`terminal_restaurante`).

Así:

| Actor | Condición | Anular desayuno/servicio |
|-------|-----------|--------------------------|
| Usuario Dir/Adm (u otros con `ACCEDER_REGISTRO`) | permiso OK | Sí |
| `terminal_restaurante` | `ACCEDER_REGISTRO` + allowlist de la llamada | Sí |
| `terminal_restaurante` sin `ACCEDER_REGISTRO` | — | No |
| Otro terminal (aunque tenga `ACCEDER_REGISTRO`) | no en allowlist | No |
| `terminal_inventario` | no en allowlist de anulación | No |
| Cualquier terminal en otros `deny_terminal=True` sin allowlist | — | No (p. ej. ajustes/compras/config) |

Registro operativo (`desayuno_registro` / `ServicioRegistro.registrar`) sigue con
`ACCEDER_REGISTRO` **sin** `deny_terminal` (sin cambio).

La UI Flet de historial/anulación del Terminal Restaurante consume este contrato:

- Historial: `desayuno_registro.historial_ordenado` / `comida|cena|bebida_service.servicio.historial_ordenado`.
- Anulabilidad: `puede_anular_registro(data, registro, *, tipo=None) → ResultadoPuedeAnular`.
- Anulación: `anular_desayuno` / `anular_servicio` (wrappers de `anular_registro`).
- Presenter Flet obtiene `AppData` solo vía `get_container().app_data_store.get()` para
  `puede_anular_registro` y lookup; la vista no toca datos productivos.
- Límite de historial (25) es solo de presentación.
- `_anulando` / `_confirmando` son anti doble clic local, no idempotencia persistente.

Atomicidad de anulación: commit único; rollback en memoria ante error; motivo obligatorio;
reposición de lotes exactos vía `consumos_lote`; sin idempotencia persistente (segunda
anulación → rechazo); históricos sin trazabilidad → no anulables.

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
