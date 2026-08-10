# Pre-Flet readiness — BM-V.2

## Estado

| Vertical | Estado |
|----------|--------|
| Terminal Restaurante | **APROBADA** (técnica + manual) |
| Terminal Inventario | **Implementada — pendiente validación manual** |

| Campo | Valor |
|-------|--------|
| Persistencia | JSON vía `AppDataStore` |
| UI Streamlit | Referencia intacta |
| Composition Flet | `configure_for_flet()` |
| Arranque Restaurante | `python -m app.presentation.flet.main` |
| Arranque Inventario | `python -m app.presentation.flet.main_inventario` |

## Autorización B5

`deny_terminal=True` bloquea actores `terminal` **excepto** `terminal_id=terminal_inventario` cuando el permiso es `ACCEDER_INVENTARIO` / `ACCEDER_TERMINAL_INVENTARIO`.  
Economía/config/gestor/compras siguen denegados por matriz de `terminal_id`.

## Backlog Flet (P2/P3)

- Re-render búsqueda Restaurante.
- Branding / tipografía.
- Cestas no confirmadas no persisten (documentado).
- Skip E2E Streamlit Desayuno (deuda browser).
- Traslados / recuentos / stock admin (fuera de shell Inventario).
- Empaquetado `.exe`.

## Docs

- `docs/flet_terminal_restaurante.md`
- `docs/flet_terminal_inventario.md`
- `docs/flet_terminal_inventario_plan.md`
- `docs/flet_backend_contracts.md`
