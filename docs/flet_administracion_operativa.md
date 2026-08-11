# Administración operativa Flet — BM‑V.2

## Estado

**APROBADA** (piloto responsables) y **ampliada** a maestros operativos (productos, recetas, usuarios, inventario inicial, backup, configuración hotel) más **proveedores** y **compras** (registro productivo).

Streamlit permanece como referencia para costes avanzados / zona de peligro no portados.

## Alcance incluido

1. Login de **usuario** (Dirección / Administración) con `ACCEDER_CONFIGURACION`.
2. Navegación por secciones (`ADMIN_SECCIONES`): inicio, productos, recetas, usuarios, responsables, proveedores, compras, inventario_inicial, backup, configuración.
3. **Productos** — `stock_service.crear_producto` / desactivar·reactivar (propose→confirm).
4. **Recetas** — `receta_service.crear_receta` / desactivar·reactivar.
5. **Usuarios** — `settings_service` crear / editar / cambiar_rol / set_activo / restablecer_password.
6. **Responsables de merma** — CRUD existente (sin regresión).
7. **Proveedores** — `proveedor_service` crear / editar / desactivar·reactivar.
8. **Compras** — borrador (`guardar_borrador_persistente`) → `confirmar_compra` (hash + UUID); crea lotes/movimientos. Precio solo en `CompraLineaVM.precio_unitario`.
9. **Inventario inicial** — `registrar_lote` con `LoteAltaVM.precio_total`.
10. **Backup** — `generar_backup_zip` → ZIP en carpeta `backups/` junto al JSON; listado; `inspeccionar_backup` / `restaurar_desde_bytes` solo con `RESTAURAR_BACKUP` (Dirección) + confirmación `RESTAURAR`.
11. **Configuración** — nombre establecimiento / moneda vía `guardar_configuracion`.

## Exclusiones

Motivos de merma (enum fijo). Costes avanzados, zona de peligro, logo avanzado, SQLite/API/`.exe`. Conciliación multi-albarán / adjuntos de compra (UI Streamlit F13.5).

## Arranque

```bash
python -m pip install -r requirements.txt
python -m app.presentation.flet.main_administracion
```

Alternativa: `BM_FLET_TERMINAL=administracion python -m app.presentation.flet.main`

| Variable | Efecto |
|----------|--------|
| `BM_DEMO_FILE` | JSON de datos |
| `BM_FLET_VIEW` | `desktop` (default), `web`, `asgi` |

## Autenticación y permisos

| Actor | Acceso Admin |
|-------|----------------|
| Dirección | Sí (incluye restaurar backup) |
| Administración | Sí (`ACCEDER_CONFIGURACION`; export backup; sin `RESTAURAR_BACKUP`) |
| Recepción / Restaurante / terminales | No |

Gates UI: `session_bridge.puede_usar_administracion()` + `session_tiene_permiso` por permiso concreto. Compras usan `ACCEDER_COMPRAS_DOCUMENTOS`.

## Seguridad económica

Viewmodels admin sin coste/precio/importe salvo **`LoteAltaVM.precio_total`** (inventario inicial) y **`CompraLineaVM.precio_unitario`** (registro de compra). Restaurante/Inventario Flet siguen sanitizados.

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
  admin_viewmodels.py
  presenters/terminal_administracion_presenter.py
  views/admin_shell_view.py
  session_bridge.py
```

## Tests

```bash
python -m unittest tests.test_flet_admin_compras tests.test_flet_admin_maestros tests.test_flet_terminal_administracion -v
```

## Checklist manual breve

1. Login Dir OK; Rest denegado.
2. Crear producto / receta / usuario / proveedor → aparecen en listados.
3. Compra: proveedor + línea → Confirmar → stock/lote sube.
4. Receta nueva visible en Terminal Restaurante (servicio correspondiente).
5. Desactivar producto → propose→confirm.
6. Generar backup → ZIP en `backups/`.
7. Restaurar solo Dir + texto `RESTAURAR`.
8. Responsables merma siguen operativos; economía solo en inventario inicial y líneas de compra.
