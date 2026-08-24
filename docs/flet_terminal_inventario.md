# Terminal Inventario — vertical Flet economato + ops (BM‑V.2)

## Alcance

App única de economato hotelero (flujo Compras estilo Noray + planta):

### Compras / documentos (con economía documental)
1. **Panel** — KPIs (borradores, pendientes, docs del mes)
2. **Albarán** / **Factura** — cabecera + grid editable · multi-albarán en factura
3. **Documentos** — listado, detalle, conciliación, anular, rectificativa
4. **Maestros** — proveedores, ubicaciones, impuestos, vínculos
5. **Historial** — timeline + export CSV

### Operación de planta (sin precios en saldos)
8. **Alertas** · **Caducidad** · **Merma** · **Stock** · **Traslados** · **Recuentos** · **Ajustes**

### Dominio aditivo (Noray)
- Factura **mixta**: líneas conciliadas sin stock; líneas directas sí (`compra_registro_service`).
- Pendiente de facturar = qty recibida − Σ conciliada activa (`compra_pendientes_service`).
- Situaciones derivadas de facturación/inventario (consulta; no rompen JSON).

OCR, RBAC fino por acción, pegado Excel multi-fila: limitaciones conocidas.

Streamlit Stock «Compras y documentos» y Admin Flet Compras/Documentos quedan como **fallback deprecado** (banner en UI). Camino canónico UI = Terminal Inventario Flet → B1 `compra_registro_service`.

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

- Entrada: `iniciar_terminal_inventario()` (`terminal_id=terminal_inventario`).
- Acceso: `ACCEDER_TERMINAL_INVENTARIO` o `ACCEDER_INVENTARIO`.
- **Permitidos**: `ACCEDER_COMPRAS_DOCUMENTOS`, `ACCEDER_CONFIGURACION` (maestros).
- **Bloqueados** por `terminal_id`: `CONSULTAR_COSTES`, `ACCEDER_GESTOR`.
- Sin matriz RBAC fina Ver/Confirmar/Anular (limitación documentada).

## Arquitectura

```
UI Flet Inventario → presenter (+ InventarioEconomatoMixin)
  → compra_registro / compra_pendientes / documento_consulta / catalogo / …
  → ops: alert/caducidad/merma/ubicacion_stock/traslado/recuento/ajuste
  → AppContext / UoW → AppDataStore → JSON
```

Espacios nav: `compras_panel` … `compras_historial` + ops planta.

## Pruebas

```bash
python -m unittest tests.test_b1_b3_compra_registro tests.test_compra_pendientes tests.test_compra_grid_helpers tests.test_b5_terminal_inventario_auth tests.test_flet_terminal_inventario tests.test_flet_inventario_economato -v
```
