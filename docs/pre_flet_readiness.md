# Pre-Flet readiness — BM-V.2

## Estado

| Vertical | Estado |
|----------|--------|
| Terminal Restaurante | **APROBADA** (técnica + manual) |
| Terminal Inventario | **APROBADA** (técnica + manual) |
| Consolidación UX Flet | **APROBADA** (técnica + manual) |
| Administración operativa Flet | **APROBADA TÉCNICAMENTE** — pendiente validación manual |

| Campo | Valor |
|-------|--------|
| Composition Flet | `configure_for_flet()` (única) |
| UI Streamlit | Referencia intacta |
| Arranque Restaurante | `python -m app.presentation.flet.main` |
| Arranque Inventario | `python -m app.presentation.flet.main_inventario` |
| Arranque Administración | `python -m app.presentation.flet.main_administracion` |

## Autorización B5 / Admin

`deny_terminal=True` bloquea actores `terminal` excepto allowlist Inventario operativa.
`ACCEDER_CONFIGURACION` exige usuario Dir/Adm (`terminal_id=None`). Terminales no mutan responsables.

## Backlog Flet

### Resuelto
- Re-render buscador Restaurante.
- Feedback operativo merma tipado.

### Pueden esperar
- Branding / tipografía definitiva.
- Persistencia opcional de cestas no confirmadas.
- Skip E2E Streamlit Desayuno (selector).
- Traslados / recuentos / stock admin.
- Empaquetado `.exe`.
- Resto de Settings Streamlit (usuarios, catálogos, backups, zona peligro…).

## Siguiente bloque (no iniciado automáticamente)

Validación **manual** de Administración operativa; ampliations Admin solo tras aprobación.

## Docs

- `docs/flet_terminal_restaurante.md`
- `docs/flet_terminal_inventario.md`
- `docs/flet_administracion_operativa.md`
- `docs/flet_terminal_administracion_plan.md`
- `docs/flet_backend_contracts.md`
