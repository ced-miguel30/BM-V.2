# Pre-Flet readiness — BM-V.2

## Estado

| Vertical | Estado |
|----------|--------|
| Terminal Restaurante | **APROBADA** (técnica + manual) |
| Terminal Inventario | **APROBADA** (técnica + manual) |

| Campo | Valor |
|-------|--------|
| HEAD / origin/main (implementación Inventario) | `2b4c503…` |
| Persistencia | JSON vía `AppDataStore` |
| UI Streamlit | Referencia intacta |
| Composition Flet | `configure_for_flet()` |
| Arranque Restaurante | `python -m app.presentation.flet.main` |
| Arranque Inventario | `python -m app.presentation.flet.main_inventario` |

## Validación manual Inventario

Resultado: **funciona** — sin incidencias P0–P3 reportadas.  
Espacios validados: Alertas, Caducidad, Merma, Ajustes.

Gates técnicos previos: B5 OK; 943 tests; browser 13 OK / 1 skip; smokes OK; demo canónico; sin economía en VMs.

## Autorización B5

`deny_terminal=True` bloquea actores `terminal` **excepto** `terminal_id=terminal_inventario` cuando el permiso es `ACCEDER_INVENTARIO` / `ACCEDER_TERMINAL_INVENTARIO`.  
Economía/config/gestor/compras siguen denegados por matriz de `terminal_id`.

## Backlog Flet (P2/P3 — no bloquean)

### Conviene resolver pronto (cuando se toque UX Flet)
- Re-render del buscador en Terminal Restaurante (cada tecla).
- Mensajes de éxito de merma sanitizados a texto genérico si el backend incluye “coste” (operación OK; feedback poco específico).

### Pueden esperar
- Branding / tipografía definitiva (ambos terminales).
- Persistencia opcional de cestas no confirmadas entre reinicios (hoy: memoria de proceso; documentado).
- Skip E2E Streamlit «Confirmar Desayuno» (deuda browser/Streamlit, no Flet Inventario).
- Traslados / recuentos / stock admin (fuera del shell Inventario actual).
- Empaquetado `.exe` / instalador.

## Siguiente bloque recomendado (no iniciado)

Prioridad: **Administración Flet (piloto acotado)** — catálogo mínimo / configuración operativa que ambos terminales ya asumen (p. ej. responsables de merma), **o** consolidación UX de las dos verticales (búsqueda Restaurante + feedback merma), según negocio.

No: traslados/recuentos como “tercera vertical inventada” antes de cerrar necesidades admin; no SQLite/API/exe todavía.

## Docs

- `docs/flet_terminal_restaurante.md`
- `docs/flet_terminal_inventario.md`
- `docs/flet_terminal_inventario_plan.md`
- `docs/flet_backend_contracts.md`
