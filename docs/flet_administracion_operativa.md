# Administración operativa Flet — BM‑V.2

## Estado

**APROBADA** (piloto responsables) y **ampliada** a maestros operativos, compras, documentos y cierre Streamlit-free (dashboard, catálogos, servidor/shared root, actividad, zona de peligro).

Streamlit permanece como referencia para costes avanzados / gráficos de análisis no portados.

## Alcance incluido

1. Login de **usuario** (Dirección / Administración) con `ACCEDER_CONFIGURACION`.
2. Navegación por secciones (`ADMIN_SECCIONES`): dashboard (`inicio`), productos, recetas, usuarios, responsables, **catálogos**, proveedores, compras, documentos, inventario_inicial, **actividad**, backup, configuración, **servidor**, **zona_peligro** (solo Dir).
3. **Dashboard** — conteos operativos del periodo (consumos, mermas, stock bajo, caducidades, alerta de registro), revisión JSON y ruta de datos; botón *Actualizar datos* → `refresh_if_stale()`. Sin € en la UI (costes avanzados fuera de alcance).
4. **Productos** — `stock_service.crear_producto` / desactivar·reactivar (propose→confirm).
5. **Recetas** — `receta_service.crear_receta` / desactivar·reactivar.
6. **Usuarios** — `settings_service` crear / editar / cambiar_rol / set_activo / restablecer_password.
7. **Responsables de merma** — CRUD existente (sin regresión).
8. **Catálogos** — departamentos / categorías / ubicaciones vía `catalogo_service` (alta + listado activo).
9. **Proveedores** — `proveedor_service` crear / editar / desactivar·reactivar.
10. **Compras** — borrador → `confirmar_compra`. Precio solo en `CompraLineaVM.precio_unitario`.
11. **Documentos** — listado + export CSV (`documento_consulta_service.exportar_documentos_csv`) con feedback de ruta; nº de líneas en lista.
12. **Actividad** — últimas 50 entradas de `data.actividades` (solo lectura).
13. **Inventario inicial** — `registrar_lote` con `LoteAltaVM.precio_total`.
14. **Backup** — ZIP / inspeccionar / restaurar (Dir + `RESTAURAR`).
15. **Configuración** — nombre establecimiento / moneda.
16. **Servidor** — muestra data path / shared root; valida con `instance_config.validate_shared_root` / `apply_shared_root`; Guardar escribe **solo** config de cliente (nunca copia datos). `SharedPathUnavailable` → error claro, sin fallback local.
17. **Zona de peligro** — visible con `EJECUTAR_OPERACION_DESTRUCTIVA` (Dir); solo ops del inventario productivo (`restablecer_mock`); frase + checkbox.

## Exclusiones

Motivos de merma (enum fijo). Costes/gráficos avanzados de Análisis. Conciliación multi-albarán / adjuntos de compra (UI Streamlit F13.5). SQLite/API/`.exe`.

## Arranque

```bash
python -m pip install -r requirements.txt
python -m app.presentation.flet.main_administracion
```

Alternativa: `BM_FLET_TERMINAL=administracion python -m app.presentation.flet.main`

| Variable | Efecto |
|----------|--------|
| `BM_DEMO_FILE` | JSON de datos |
| `BM_INSTANCE_ROOT` / `BM_SHARED_ROOT` | Raíz de instancia compartida |
| `BM_FLET_VIEW` | `desktop` (default), `web`, `asgi` |

## Autenticación y permisos

| Actor | Acceso Admin |
|-------|----------------|
| Dirección | Sí (backup restore + zona de peligro) |
| Administración | Sí (`ACCEDER_CONFIGURACION`; export backup; sin restore / zona peligro) |
| Recepción / Restaurante / terminales | No |

Gates UI: `session_bridge.puede_usar_administracion()` + `session_tiene_permiso` por permiso concreto. Compras/documentos usan `ACCEDER_COMPRAS_DOCUMENTOS`.

## Seguridad económica

Viewmodels admin sin coste/precio/importe salvo **`LoteAltaVM.precio_total`** e **`CompraLineaVM.precio_unitario`**. Dashboard Admin usa conteos operativos (no €).

## Arquitectura

```
view → callbacks (app_shell) → presenter → servicios productivos
```

La vista **no** importa AppData, repositorios, JSON ni servicios.

## Estructura

```
app/presentation/flet/
  main_administracion.py
  app_shell_administracion.py
  admin_viewmodels.py          # ADMIN_SECCIONES + VMs
  presenters/terminal_administracion_presenter.py
  views/admin_shell_view.py
  session_bridge.py
```

## Tests

```bash
python -m unittest tests.test_flet_admin_cierre tests.test_flet_admin_compras tests.test_flet_admin_maestros tests.test_flet_terminal_administracion -v
```

## Checklist manual breve

1. Login Dir OK; Rest denegado.
2. Dashboard: conteos + revisión + *Actualizar datos*.
3. Servidor: ruta vacía rechazada; UNC/local válida guarda solo config.
4. Catálogos: crear departamento / ubicación.
5. Actividad: lista reciente.
6. Documentos: export CSV → path en feedback.
7. Zona peligro: Adm denegado; Dir ve `restablecer_mock` con frase.
8. Compra / maestros / backup siguen operativos.
