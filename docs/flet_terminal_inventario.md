# Terminal Inventario — segunda vertical Flet (BM‑V.2)

## Alcance

Espacios operativos:

1. **Alertas** — listado y cambio de estado  
2. **Caducidad** — lotes próximos/vencidos → cesta merma (motivo Expiración)  
3. **Merma** — cesta + confirmación  
4. **Ajustes** — previsualización + confirmación de cantidad restante  

Excluido: traslados, recuentos, stock admin, compras/documentos, dashboard, costes, SQLite, API, `.exe`.

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

## Arquitectura

```
UI Flet Inventario → presenter → alert/caducidad/merma/ajuste services
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

## Persistencia y reinicio

- Confirmaciones (merma / ajustes / estados de alerta) persisten en el JSON configurado.
- Cesta de merma no confirmada: memoria de proceso (no sobrevive al cierre).
- Preview de ajuste: solo en memoria hasta confirmar.

## Seguridad económica

Viewmodels sin coste/precio/importe/margen/€. El presenter no llama a `coste_total_cesta_merma` ni expone `precio_total` del preview de ajuste.

## Pruebas

```bash
python -m unittest tests.test_b5_terminal_inventario_auth tests.test_flet_terminal_inventario -v
python run_tests.py
python run_browser_tests.py
```

## Limitaciones

- Crear responsables de merma requiere Administración (fuera de este terminal).
- Mensajes de éxito de merma pueden sanitizarse si el backend incluye texto económico.
- Branding definitivo pendiente.

## Validación

- **Técnica:** gates verdes (B5, 943 tests, smokes, demo canónico).
- **Manual:** Terminal Inventario **APROBADA** (resultado: funciona; Alertas, Caducidad, Merma y Ajustes validados; sin incidencias reportadas).
