# Administración operativa Flet (piloto mínimo) — BM‑V.2

## Estado

**APROBADA TÉCNICAMENTE** — pendiente de validación manual.

Streamlit permanece como interfaz administrativa de referencia completa.

## Alcance incluido

1. Login de **usuario** (Dirección / Administración) con `ACCEDER_CONFIGURACION`.
2. CRUD de **responsables de merma**:
   - listar / filtrar;
   - crear;
   - renombrar;
   - desactivar / reactivar;
   - resumen previo + confirmación explícita.

## Exclusiones

Motivos de merma (enum fijo `MotivoMerma` — solo informativos en UI).
Config hotel, catálogos, usuarios/RBAC completo, compras, proveedores, costes, backups, zona de peligro, traslados/recuentos, SQLite/API/`.exe`.

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

| Actor | Acceso Admin operativa |
|-------|------------------------|
| Dirección (usuario) | Sí |
| Administración (usuario) | Sí (`ACCEDER_CONFIGURACION`) |
| Recepción | No |
| Restaurante (usuario o terminal) | No |
| Terminal Inventario | No (`deny_terminal` + bloqueo `terminal_id`) |
| Sin sesión | No |

Mutaciones: `merma_service.*_responsable_merma` con `deny_terminal=True`.
No se concede admin vía `ACCEDER_INVENTARIO`.

## Responsables — activos / inactivos

- Soft-delete (`activo=False`); sin borrado físico.
- Inventario solo lista `solo_activos=True` para operaciones nuevas.
- Renombrar **no** reescribe `responsable_nombre` histórico (snapshot en línea).
- Tras mutar: el store compartido refleja el cambio al refrescar / reconstruir `configure_for_flet()` (misma composición JSON).

## Persistencia

Misma `FileBackedAppDataStore` / `AppData.responsables_merma`. Sin repositorio paralelo.

## Seguridad económica

Viewmodels Admin sin coste/precio/importe/margen/€. No se llaman servicios económicos.

## Estructura

```
app/presentation/flet/
  main_administracion.py
  app_shell_administracion.py
  admin_viewmodels.py
  presenters/terminal_administracion_presenter.py
  views/admin_shell_view.py
  session_bridge.py  # login_administracion
```

## Tests

```bash
python -m unittest tests.test_flet_terminal_administracion -v
python run_tests.py
python run_browser_tests.py
```

## Limitaciones

- No es un port de Settings Streamlit.
- Filtro de busqueda reconstruye la lista (aceptable; volumen bajo).
- Selector de responsable en UI de Inventario: **obligatorio y vacío al entrar**; no auto-elige el primero. Tras merma exitosa o cambio de pestaña se limpia.
- Branding definitivo pendiente.

## Checklist manual breve

1. Login Dir/Adm OK; Rest denegado.
2. Crear responsable → aparece en listado.
3. Inventario merma puede usarlo.
4. Desactivar → ya no seleccionable en nuevas operaciones.
5. Renombrar → histórico previo conserva snapshot.
6. Logout.
