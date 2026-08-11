# Terminal Restaurante — primera vertical Flet (BM‑V.2)

## Instalar Flet

```bash
python -m pip install -r requirements.txt
```

Versiones fijadas: `flet==0.86.4` y `flet-desktop==0.86.4` (Python ≥3.10; verificado con 3.14 / Windows).

## Arrancar

```bash
python -m app.presentation.flet.main
```

### Variables de entorno

| Variable | Efecto |
|----------|--------|
| `BM_DEMO_FILE` | Ruta JSON de datos (default: `data/demo/datos_hotel.json`) |
| `BM_FLET_VIEW` | `desktop` (default), `web`, o `asgi`/`headless` (smoke sin ventana) |

## Arquitectura

```
UI Flet → presenter / session_bridge → servicios / casos de uso
         → AppContext / UoW → AppDataStore → JSON
```

Composition: `configure_for_flet()` en `app/bootstrap.py`
( FileBackedAppDataStore + MemoryBasketStore + MemoryAuthSessionStore + MemoryIdempotencyStore ).

Estructura:

```
app/presentation/flet/
  main.py
  app_shell.py
  session_bridge.py
  viewmodels.py
  mappers.py
  presenters/terminal_restaurante_presenter.py
  views/login_terminal_view.py
  views/registro_servicio_view.py
```

Flet **no** importa Streamlit, `app.pages` ni `session_state`. No escribe JSON directamente.
La vista no importa servicios, repositorios ni `AppData`; solo ViewModels y callbacks.

## Flujos soportados

1. Entrada al terminal (actor `terminal_restaurante`) / logout.
2. Selección de servicio: Desayuno, Comida, Cena, Bebidas independientes.
3. Catálogo: recetas activas + productos directos, con búsqueda.
4. Cesta aislada por servicio: añadir / ajustar / quitar / vaciar.
5. Confirmación con idempotencia y bloqueo anti doble clic.
6. **Historial reciente** del servicio activo (activos + anulados + no anulables).
7. **Anulación** con `puede_anular_registro` → confirmación explícita → motivo obligatorio → wrappers productivos.

`PRODUCTO_DIRECTO` se registra **dentro** del servicio activo (no es un quinto servicio).
Desayuno usa `desayuno_registro`; los demás, `ServicioRegistro` (estrategia explícita).

## Historial (presentación)

- Fuente: `bind.api.historial_ordenado()` (Desayuno / Comida / Cena / Bebidas).
- Orden: el del servicio (fecha/hora descendente).
- Límite **solo UI**: 25 registros (`_HISTORIAL_LIMITE`); el dominio no pagina.
- Estados visibles: `Activo`, `Anulado`, `No anulable` (con motivo operativo).
- Detalle operativo sanitizado (huéspedes/líneas/recetas); **sin economía**.
- El ID técnico vive en el ViewModel para acciones; la vista no lo muestra completo.
- Tras registrar o anular se refresca; el registro recién confirmado permanece visible.

## Anulación

Flujo:

1. Operador pulsa Anular sobre un registro **activo**.
2. Presenter llama `puede_anular_registro`.
3. Si no anulable → feedback con motivo; no abre confirmación; no muta.
4. Si anulable → resumen operativo + motivo obligatorio + confirmación explícita.
5. `_anulando` bloquea reentrada local (no es idempotencia persistente).
6. Una llamada a `anular_desayuno` o `anular_servicio`.
7. Éxito → limpia pendiente, refresca historial (estado Anulado), feedback sin economía.
8. Error → sin falso éxito; contexto conservado; mensaje comprensible.

Dominio (sin cambio en esta vertical UI):

- Motivo no vacío; rechaza ya anulados; históricos sin `consumos_lote` seguros → no anulables.
- Repone lotes exactos; movimientos espejo (`REVERSION_CONSUMO`); actividad; commit UoW; rollback en memoria.
- Segunda anulación rechazada (sin clave de idempotencia persistente).
- RBAC: `deny_terminal=True` + `allowed_terminals={terminal_restaurante}` + `ACCEDER_REGISTRO`.

Cancelar, Volver al menú (`preparar_salida`) y logout **nunca** anulan automáticamente.

## Almacenamiento y reinicio

- Persistencia: mismo JSON / serializadores actuales vía `AppDataStore`.
- Registros confirmados y anulaciones sobreviven a reinicio del proceso.
- La cesta no confirmada vive en memoria del proceso (MemoryBasketStore): **no** se conserva al cerrar la app.
- La confirmación de anulación pendiente es solo UI en memoria.

## Seguridad económica

Viewmodels y presenter no solicitan ni transportan coste, precio, margen, importe ni símbolos monetarios.
El historial sanitiza cualquier campo económico que venga del dominio.
El actor del terminal no tiene `CONSULTAR_COSTES`; el acceso directo a `costes_service` queda denegado.

## Pruebas

```bash
python -m unittest tests.test_flet_terminal_restaurante -v
python -m unittest tests.test_flet_restaurante_historial_anulacion -v
python -m unittest tests.test_rbac_terminal_restaurante_anulacion -v
python run_tests.py
python run_browser_tests.py
```

## Limitaciones (esta vertical)

- Sin merma, filtros avanzados, buscador de historial, paginación productiva ni exportación.
- Sin edición de registros ni anulación de mermas.
- Sin Terminal Inventario / Administración / dashboard / compras en este shell.
- UX táctil operativa; branding definitivo pendiente.
- Búsqueda de catálogo: actualización localizada (`update_catalog_only`).

## Consolidación UX (buscador)

- Causa previa: `on_change` → `refresh()` reconstruía toda la pantalla.
- Corrección: `set_busqueda` + `update_catalog_only()` (mismas instancias de campo y columna de resultados).
- Tests: `tests/test_flet_ux_consolidacion.py`.

## Validación

- **Técnica:** gates verdes (ver `docs/pre_flet_readiness.md`).
- **Manual:** Terminal Restaurante **APROBADA** (registro); historial+anulación cubierta por suite Flet dirigida.
- Consolidación UX buscador: **APROBADA** técnica y manualmente (sin incidencias).

## Alcance excluido

- Streamlit, empaquetado, SQLite/API, branding, cambios de dominio/RBAC (salvo el ya cerrado en `14bd986`).
- Inventario / Administración / compras.
