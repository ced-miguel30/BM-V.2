# Plan — Administración Flet (piloto mínimo)

**Estado:** implementado (piloto); ver `docs/flet_administracion_operativa.md`.
**Precondición:** Terminal Restaurante, Terminal Inventario y consolidación UX Flet **APROBADAS** (técnica + manual).
**Streamlit** sigue siendo la interfaz de referencia.
**Composition:** reutilizar `configure_for_flet()` (sin backend paralelo).

## Objetivo

Demostrar Administración Flet sobre el núcleo compartido, limitada a lo que las terminales Flet actuales requieren de forma operativa:

1. Login de **usuario** con `ACCEDER_CONFIGURACION`.
2. CRUD de **responsables de merma** (listar / crear / renombrar / desactivar / reactivar).

No es un port de `app/pages/settings.py`.

## Dependencia real hacia Admin

| Terminal Flet | Necesidad Admin |
|---------------|-----------------|
| Inventario | ≥1 `ResponsableMerma` activo (`listar_responsables_merma(solo_activos=True)`); sin activos → error «Configúrelos en Administración.» |
| Restaurante | Ninguna dependencia de catálogos Admin |

`ConfiguracionHotel`, catálogos, proveedores, logo, etc. **no** son consumidos por el árbol Flet actual → fuera del piloto.

## Dominio a reutilizar (sin nuevos servicios)

Modelo: `ResponsableMerma` (`id`, `nombre`, `activo`) en `app/core/models/merma.py`.

APIs en `merma_service.py`:

- `listar_responsables_merma(solo_activos=False|True)`
- `crear_responsable_merma(nombre)`
- `renombrar_responsable_merma(id, nombre)`
- `desactivar_responsable_merma(id)`
- `reactivar_responsable_merma(id)`

Mutadores: `Permiso.ACCEDER_CONFIGURACION` + `deny_terminal=True`.
Persistencia: `AppData.responsables_merma` vía UoW / JSON existente. Soft-delete; renombre no reescribe histórico.

Auth Admin: `autenticar_usuario` → `actor_type="usuario"`, `terminal_id=None` (no reutilizar `iniciar_terminal_*`).

## Arquitectura propuesta

```
app/presentation/flet/
  main_administracion.py                         # NEW
  app_shell_administracion.py                    # NEW
  admin_viewmodels.py                            # NEW (sin economía)
  presenters/terminal_administracion_presenter.py  # NEW
  views/admin_shell_view.py                      # NEW
  session_bridge.py                              # CHANGE: login usuario Admin
```

Opcional: `BM_FLET_TERMINAL=administracion` en `main.py`.

## Fases ejecutables

| Fase | Qué | Entregable |
|------|-----|------------|
| 0 | Baseline verde + demo canónico | Sin código Admin |
| 1 | Bridge login usuario + `ACCEDER_CONFIGURACION` | `session_bridge` |
| 2 | Presenter + VMs CRUD responsables | Presenter / viewmodels |
| 3 | Shell UI (lista + crear + renombrar + activar/desactivar) | views / shell / main |
| 4 | Contrato cruzado Inventario | Tras alta Admin → inventario ve activos |
| 5 | Guards AST + auth (terminals denegados, sin economía) | tests |
| 6 | Docs de arranque y límites | `docs/flet_terminal_administracion.md` |

## Tests mínimos

- Login Dir/Admin OK; rol sin config denegado.
- Terminal Restaurante/Inventario no mutan responsables (`deny_terminal` / matriz Inventario).
- CRUD + soft-delete + renombre sin alterar histórico.
- Viewmodels sin campos económicos / sin `€`.
- Sin imports `streamlit` / `app.pages`.
- Smoke ASGI Admin.
- Cruzado: crear responsable → `TerminalInventarioPresenter` lista activos.

## Fuera de alcance (v1)

Usuarios/RBAC completo, catálogos inventario, proveedores/impuestos, archivos documentales, actividad, exportación/backup, restauración, zona de peligro, datos demo, config establecimiento/logo, costes, compras/documentos, dashboard, gestor, stock admin, traslados/recuentos, SQLite, API, `.exe`, migración Streamlit, branding definitivo, persistencia de cestas.

## Gates de aceptación

- Runners canónico + Flet relevantes verdes; browser Streamlit sin regresión nueva.
- Smokes Streamlit + tres Flet (Restaurante, Inventario, Admin).
- Demo SHA canónico intacto.
- Validación manual: crear responsable → Inventario merma operable.

## Criterio de arranque

Este plan se ejecuta **solo** cuando se autorice explícitamente la vertical Administración Flet. Hasta entonces no se escribe código de Admin.
