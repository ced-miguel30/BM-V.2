# Terminal Inventario — segunda vertical Flet (BM‑V.2)

## Alcance

App única de economato hotelero (estilo Dynamics NAV):

### Economato (con economía documental)
1. **Maestros** — departamentos, ubicaciones tipificadas (`economato|cocina|bar|camara|otro`), proveedores, impuestos, vínculos producto–proveedor
2. **Recepción** — cabecera + grid multilínea (precio, dto %, dto €, IGIC, ubicación) · borrador/confirmar vía `compra_registro_service` · multi-albarán → factura
3. **Documentos** — listado/filtro, detalle, anular confirmado, rectificativa
4. **Historial** — timeline movimientos + documentos · export CSV

### Operación de planta (sin precios en saldos)
5. **Alertas** · **Caducidad** · **Merma** · **Stock** · **Traslados** · **Recuentos** · **Ajustes**

OCR, RBAC por ubicación y pedidos a proveedor: fuera de este alcance.

Streamlit Stock «Compras y documentos» y Admin Flet Compras/Documentos quedan como **fallback deprecado** (banner en UI).

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
- **Permitidos** en esta terminal: `ACCEDER_COMPRAS_DOCUMENTOS`, `ACCEDER_CONFIGURACION` (maestros), mutaciones con `deny_terminal` en allowlist.
- **Siguen bloqueados** por `terminal_id`: `CONSULTAR_COSTES`, `ACCEDER_GESTOR`.
- Stock/traslados/recuentos/merma: sin precios en VMs de planta (`assert_inventario_sin_economia`). Economía solo en `EconomatoPanelVM` (`inventory_document_viewmodels.py`).

## Arquitectura

```
UI Flet Inventario → presenter (+ InventarioEconomatoMixin)
  → compra_registro / documento_consulta / catalogo / proveedor / anulacion / rectificativa
  → ops: alert/caducidad/merma/ubicacion_stock/traslado/recuento/ajuste
  → AppContext / UoW → AppDataStore → JSON
```

```
app/presentation/flet/
  main_inventario.py
  app_shell_inventario.py
  inventory_viewmodels.py
  inventory_document_viewmodels.py
  presenters/terminal_inventario_presenter.py
  presenters/inventario_economato_mixin.py
  views/inventario_shell_view.py
  views/inventario_economato_view.py
```

Helpers de rejilla: `app/ui/compra_grid_helpers.py` (sin Streamlit; compartidos con 13.5).

## Regla de dominio (UI)

**Departamento** = centro de uso · **Ubicación** = dónde está el stock físico.

## Pruebas

```bash
python -m unittest tests.test_b5_terminal_inventario_auth tests.test_flet_terminal_inventario tests.test_flet_inventario_stock_traslados tests.test_flet_inventario_recuentos tests.test_flet_inventario_economato -v
```
