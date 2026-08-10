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

## Flujos soportados

1. Entrada al terminal (actor `terminal_restaurante`) / logout.
2. Selección de servicio: Desayuno, Comida, Cena, Bebidas independientes.
3. Catálogo: recetas activas + productos directos, con búsqueda.
4. Cesta aislada por servicio: añadir / ajustar / quitar / vaciar.
5. Confirmación con idempotencia y bloqueo anti doble clic.

`PRODUCTO_DIRECTO` se registra **dentro** del servicio activo (no es un quinto servicio).
Desayuno usa `desayuno_registro`; los demás, `ServicioRegistro` (estrategia explícita).

## Almacenamiento y reinicio

- Persistencia: mismo JSON / serializadores actuales vía `AppDataStore`.
- Registros confirmados sobreviven a reinicio del proceso.
- La cesta no confirmada vive en memoria del proceso (MemoryBasketStore): **no** se conserva al cerrar la app.

## Seguridad económica

Viewmodels y presenter no solicitan ni transportan coste, precio, margen, importe ni símbolos monetarios.
El actor del terminal no tiene `CONSULTAR_COSTES`; el acceso directo a `costes_service` queda denegado.

## Pruebas

```bash
python -m unittest tests.test_flet_terminal_restaurante -v
python run_tests.py
python run_browser_tests.py
```

## Limitaciones (esta vertical)

- Sin merma, anulaciones, histórico detallado, ni menús administrativos.
- Sin Terminal Inventario / Administración / dashboard / compras.
- UX táctil operativa; branding definitivo pendiente.
- La búsqueda en UI puede re-renderizar el árbol (mejora P2).

## Alcance excluido

Terminal Inventario, Administración, SQLite, API, instalador `.exe`, migración completa desde Streamlit.
