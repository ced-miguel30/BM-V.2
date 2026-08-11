# Pre-Flet readiness — BM-V.2

## Estado

| Vertical | Estado |
|----------|--------|
| Terminal Restaurante | **APROBADA** (técnica + manual) |
| Terminal Inventario | **APROBADA** (técnica + manual) |
| Consolidación UX Flet | **APROBADA** (técnica + manual) |
| Administración operativa Flet | **APROBADA** (técnica + manual) |
| Launcher Flet | **APROBADO** (técnica + manual) |

| Campo | Valor |
|-------|--------|
| Composition Flet | `configure_for_flet()` (única) |
| UI Streamlit | Referencia intacta (Settings amplio) |
| Arranque Restaurante | `python -m app.presentation.flet.main` |
| Arranque Inventario | `python -m app.presentation.flet.main_inventario` |
| Arranque Administración | `python -m app.presentation.flet.main_administracion` |
| Arranque launcher | `python -m app.presentation.flet.main_launcher` |

## Autorización B5 / Admin

`deny_terminal=True` bloquea actores `terminal` excepto allowlist Inventario operativa.
`ACCEDER_CONFIGURACION` exige usuario Dir/Adm (`terminal_id=None`). Terminales no mutan responsables.
Merma Flet exige responsable **explícito** (sin autofill).

## Backlog Flet

### Resuelto
- Re-render buscador Restaurante.
- Feedback operativo merma tipado.
- Responsable obligatorio en Merma Inventario.
- Listado Admin legible (contraste / vacío / Activo-Inactivo).
- Launcher Flet mínimo (**APROBADO** técnica + manual).

### Pueden esperar
- Branding / tipografía definitiva (las tres superficies Flet).
- Persistencia opcional de cestas no confirmadas.
- Skip E2E Streamlit Desayuno (selector).
- Traslados / recuentos / stock admin.
- Empaquetado `.exe` / instalador (plan: `docs/flet_packaging_plan.md`; **no** construido).
- Resto de Settings Streamlit (usuarios, catálogos, backups, zona peligro…).
- Volver al launcher sin reiniciar el proceso.

## Siguiente bloque (recomendado, no iniciado)

**Planificación técnica de despliegue local** según `docs/flet_packaging_plan.md`
(sin construir `.exe` hasta autorización explícita).

## Docs

- `docs/flet_terminal_restaurante.md`
- `docs/flet_terminal_inventario.md`
- `docs/flet_administracion_operativa.md`
- `docs/flet_launcher.md`
- `docs/flet_packaging_plan.md`
- `docs/flet_terminal_administracion_plan.md`
- `docs/flet_backend_contracts.md`
