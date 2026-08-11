# Terminal Inventario — segunda vertical Flet (BM‑V.2)

## Alcance

Espacios operativos:

1. **Alertas** — listado y cambio de estado
2. **Caducidad** — lotes próximos/vencidos → cesta merma (motivo Expiración)
3. **Merma** — cesta + confirmación
4. **Stock** — consulta de saldos por ubicación / producto / lote (solo lectura; sin economía)
5. **Traslados** — preview + confirmación entre ubicaciones (servicio 7B.4; un movimiento `traslado`)
6. **Recuentos** — preview en memoria + borrador 7B.6 + confirmación (ajustes derivados `RECONTEO_FISICO`)
7. **Ajustes** — previsualización + confirmación de cantidad restante

Excluido: anulación de recuentos **confirmados**, anulación de traslados, CRUD de ubicaciones, compras/documentos, dashboard, costes, SQLite, API, `.exe`.

## Arranque

```bash
python -m pip install -r requirements.txt
python -m app.presentation.flet.main_inventario
```

Alternativa: `BM_FLET_TERMINAL=inventario python -m app.presentation.flet.main`

| Variable | Efecto |
|----------|--------|
| `BM_DEMO_FILE` | JSON de datos |
| `BM_FLET_VIEW` | `desktop` (default), `web`, `asgi` |
| `BM_FLET_TERMINAL` | `restaurante` \| `inventario` (solo con `main.py`) |

## Autenticación y permisos

- Entrada: `iniciar_terminal_inventario()` (`terminal_id=terminal_inventario`, rol administración técnico).
- Acceso: `ACCEDER_TERMINAL_INVENTARIO` o `ACCEDER_INVENTARIO`.
- Bloqueados por `terminal_id`: `CONSULTAR_COSTES`, configuración, gestor, compras/documentos.
- `deny_terminal=True`: Terminal Inventario puede mutar con `ACCEDER_INVENTARIO`; Restaurante y terminales genéricos siguen bloqueados.
- Recuentos usan el mismo permiso de dominio (`ACCEDER_INVENTARIO` + `deny_terminal`).

## Arquitectura

```
UI Flet Inventario → presenter → alert/caducidad/merma/ubicacion_stock/traslado/recuento/ajuste services
                   → AppContext / UoW → AppDataStore → JSON
```

Composition: `configure_for_flet()` (compartida con Restaurante).

```
app/presentation/flet/
  main_inventario.py
  app_shell_inventario.py
  inventory_viewmodels.py
  presenters/terminal_inventario_presenter.py
  views/inventario_shell_view.py
  session_bridge.py  # enter_terminal_inventario
```

No importa Streamlit ni `app.pages`. No escribe JSON directamente. No se acopla a las vistas de Restaurante.
La vista no accede a AppData, repositorios ni servicios productivos: solo presenter/viewmodels.

## Recuentos (7B.6 vía presentación)

### Flujo

1. **Formulario en memoria** — ubicación de catálogo (nunca `sin_ubicacion_historica`), producto con lote, cantidad ≥ 0; una o varias líneas sin duplicar producto/lote.
2. **Previsualizar** — solo memoria. No llama a `crear_borrador`. No crea sesiones, ajustes ni movimientos. Orientativo (no reserva).
3. **Confirmar** — exige preview válido; `_confirmando` + botones deshabilitados; llama `crear_borrador`; guarda `recuento_id`; compara esperado congelado vs preview en memoria.
   - Si difieren: **no** llama a `confirmar_recuento`; exige segunda confirmación explícita con valores autoritativos del borrador.
   - Si coinciden: `confirmar_recuento(recuento_id)`; limpia UI; refresca Stock / pendientes / recientes.
4. **Errores** — fallo de crear: sin `recuento_id`, formulario recuperable. Fallo de confirmar tras crear: **no** auto-anula; conserva ID; permite reintentar o descartar BORRADOR con `anular_recuento`. Fallo al descartar: conserva estado visible.
5. **Salida** — sin borrador: cancelar / cambiar espacio / Volver / logout descartan solo memoria. Con borrador pendiente: aviso claro; se puede abandonar dejando el BORRADOR en Pendientes (sin confirmar ni anular automáticamente).

### Atomicidad e idempotencia (límites reales)

| Hecho | Detalle |
|-------|---------|
| Crear y confirmar son operaciones **separadas** | No hay transacción conjunta. Si crear OK y confirmar falla, queda BORRADOR. |
| Atomicidad **interna** de `confirmar_recuento` | Un commit final; rollback en memoria si falla; sin cambios parciales de stock/ajustes/ledger. |
| Sin relectura de saldo en confirmar | El dominio usa el esperado congelado en el borrador. |
| `_confirmando` | Solo anti doble clic **local** en la instancia. |
| Sin `clave_idempotencia` de sesión | `_confirmando` no es idempotencia persistente. |
| Sin garantía entre procesos | Ni bloqueo multiusuario. |
| Anulación de confirmados | Fuera de alcance Flet en este bloque. |

## Persistencia y reinicio

- Confirmaciones (merma / ajustes / traslados / recuentos / estados de alerta) persisten en el JSON configurado.
- Cesta de merma no confirmada: memoria de proceso (no sobrevive al cierre).
- Preview de ajuste, traslado o recuento en memoria: se descarta al cambiar de espacio, logout o «Volver al menú» **si no hay borrador**.
- Borrador de recuento persistido: permanece en Pendientes tras abandonar UI.

## Seguridad económica

Viewmodels sin coste/precio/importe/margen/€. El presenter no llama a `coste_total_cesta_merma` ni expone economía en preview de ajuste, traslado o recuento.

## Pruebas

```bash
python -m unittest tests.test_b5_terminal_inventario_auth tests.test_flet_terminal_inventario tests.test_flet_inventario_stock_traslados tests.test_flet_inventario_recuentos -v
python run_tests.py
python run_browser_tests.py
```

## Limitaciones

- Crear responsables de merma: **Administración operativa Flet** (`main_administracion`) o Settings Streamlit.
- Branding definitivo pendiente.
- Anulación de recuentos confirmados: no expuesta en Flet.
- Concurrencia multiusuario / idempotencia global: no garantizadas.

## Consolidación UX (feedback merma)

- Causa previa: el backend devolvía texto con coste/€; `sanitize_mensaje` lo sustituía por un mensaje genérico.
- Corrección: `map_merma_registro_feedback` construye el éxito desde campos operativos tipados (`MermaLineaOperativa`) capturados antes de vaciar la cesta.
- Distingue éxito, validación, denegado, cesta vacía e idempotencia; no expone economía ni rutas/excepciones internas.
- Tests: `tests/test_flet_ux_consolidacion.py`.

## Validación

- **Técnica:** gates verdes (B5, suite canónica, smokes, demo canónico).
- **Manual:** Terminal Inventario **APROBADA** (resultado: funciona; Alertas, Caducidad, Merma y Ajustes validados; sin incidencias reportadas).
- Consolidación UX feedback merma: **APROBADA** técnica y manualmente (sin incidencias).
