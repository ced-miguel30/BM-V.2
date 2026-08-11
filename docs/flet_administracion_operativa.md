# Administración operativa Flet — BM‑V.2

## Estado

**APROBADA** (piloto responsables) y **ampliada** a maestros operativos (productos, recetas, usuarios, inventario inicial, backup, configuración hotel).

Streamlit permanece como referencia para costes/compras/zona de peligro no portados.

## Alcance incluido

1. Login de **usuario** (Dirección / Administración) con `ACCEDER_CONFIGURACION`.
2. Navegación por secciones (`ADMIN_SECCIONES`): inicio, productos, recetas, usuarios, responsables, inventario_inicial, backup, configuración.
3. **Productos** — `stock_service.crear_producto` / desactivar·reactivar (propose→confirm).
4. **Recetas** — `receta_service.crear_receta` / desactivar·reactivar.
5. **Usuarios** — `settings_service` crear / editar / cambiar_rol / set_activo / restablecer_password.
6. **Responsables de merma** — CRUD existente (sin regresión).
7. **Inventario inicial** — `registrar_lote` con `LoteAltaVM.precio_total` (único campo económico admin).
8. **Backup** — `generar_backup_zip` → ZIP en carpeta `backups/` junto al JSON; listado; `inspeccionar_backup` / `restaurar_desde_bytes` solo con `RESTAURAR_BACKUP` (Dirección) + confirmación `RESTAURAR`.
9. **Configuración** — nombre establecimiento / moneda vía `guardar_configuracion`.

## Exclusiones

Motivos de merma (enum fijo). Costes, compras, proveedores, zona de peligro, logo avanzado, SQLite/API/`.exe`.

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

Gates UI: `session_bridge.puede_usar_administracion()` + `session_tiene_permiso` por permiso concreto.

## Seguridad económica

Viewmodels admin sin coste/precio/importe salvo **`LoteAltaVM.precio_total`** (inventario inicial). Restaurante/Inventario Flet siguen sanitizados.

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
python -m unittest tests.test_flet_admin_maestros tests.test_flet_terminal_administracion -v
```

## Checklist manual breve

1. Login Dir OK; Rest denegado.
2. Crear producto / receta / usuario → aparecen en listados.
3. Receta nueva visible en Terminal Restaurante (servicio correspondiente).
4. Desactivar producto → propose→confirm.
5. Generar backup → ZIP en `backups/`.
6. Restaurar solo Dir + texto `RESTAURAR`.
7. Responsables merma siguen operativos; sin economía en listados generales.
