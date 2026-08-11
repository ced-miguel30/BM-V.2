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

`deny_terminal=True` bloquea actores `terminal` excepto:

- allowlist Inventario operativa (`ACCEDER_INVENTARIO` / `ACCEDER_TERMINAL_INVENTARIO`);
- excepciones **explícitas por llamada** vía `allowed_terminals` (hoy: anulación de
  registros con `terminal_restaurante` + `ACCEDER_REGISTRO`).

`ACCEDER_CONFIGURACION` exige usuario Dir/Adm (`terminal_id=None`). Terminales no mutan responsables.
Merma Flet exige responsable **explícito** (sin autofill).

UI Flet de historial/anulación en Restaurante: **pendiente** (RBAC de dominio ya alineado).

## Backlog Flet

### Resuelto
- Re-render buscador Restaurante.
- Feedback operativo merma tipado.
- Responsable obligatorio en Merma Inventario.
- Listado Admin legible (contraste / vacío / Activo-Inactivo).
- Launcher Flet mínimo (**APROBADO** técnica + manual).
- Volver al launcher desde verticales abiertas vía launcher (misma Page; logout; sin reiniciar proceso).
- Stock por ubicación + Traslados en Flet Inventario (consulta + preview/confirm).
- Recuentos en Flet Inventario (preview memoria + borrador 7B.6 + confirmación; sin anulación de confirmados).
- RBAC: `terminal_restaurante` puede anular registros operativos (`ACCEDER_REGISTRO` +
  `allowed_terminals` acotado; sin abrir Inventario ni otros `deny_terminal`).

### Pueden esperar
- Branding / tipografía definitiva (las tres superficies Flet).
- Persistencia opcional de cestas no confirmadas.
- Skip E2E Streamlit Desayuno (selector).
- Historial + anulación en UI Flet Restaurante (dominio RBAC ya listo).
- Anulación de traslados / CRUD ubicaciones / anulación de recuentos confirmados en Flet.
- Empaquetado `.exe` / instalador (**no** construido; P2 en `docs/deploy_local_p2.md`).
- Resto de Settings Streamlit (usuarios, catálogos, backups UI, zona peligro…).
- Piloto físico Windows del despliegue C (checklist P2).

## Siguiente bloque (recomendado, no iniciado)

**Flet Restaurante: historial operativo + anulación** (capa presentación; dominio listo).

## Docs

- `docs/flet_terminal_restaurante.md`
- `docs/flet_terminal_inventario.md`
- `docs/flet_administracion_operativa.md`
- `docs/flet_launcher.md`
- `docs/flet_packaging_plan.md`
- `docs/deploy_local_p1.md`
- `docs/deploy_local_p2.md`
- `docs/flet_terminal_administracion_plan.md`
- `docs/flet_backend_contracts.md`
