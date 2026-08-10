# Plan ejecutable — Terminal Inventario (segunda vertical Flet)

**Estado:** listo para comenzar cuando se autorice. **No implementado.**  
**Precondición:** Terminal Restaurante APROBADA (técnica + manual).

## Objetivo

Demostrar que Flet puede operar el **Terminal Inventario** sobre el mismo núcleo compartido, sin Streamlit, sin economía en viewmodels y sin backend paralelo.

## Alcance de la primera vertical Inventario (espejo del shell Streamlit actual)

Replicar funcionalmente `app/pages/terminal_inventario.py` (4 pestañas), no el Stock administrativo completo:

| Área | Incluir | Entrypoints previstos |
|------|---------|------------------------|
| Entrada / logout | Sí | `iniciar_terminal_inventario`, `ACCEDER_TERMINAL_INVENTARIO` \| `ACCEDER_INVENTARIO` |
| Alertas | Lectura sí; mutación solo tras alinear `deny_terminal` | `alert_service.*` |
| Caducidad | Listar lotes + salida a cesta merma | `caducidad_service.listar_lotes_caducidad`, `registrar_salida_caducidad` |
| Merma | Cesta + confirmación | `merma_service` (`bm_cesta_merma`) |
| Ajustes | Preview + apply solo si auth lo permite al terminal | `ajuste_service.lotes_ajustables`, `previsualizar_ajuste`, `aplicar_ajuste` |

### Fuera de alcance (esta vertical)

Traslados, recuentos, grid de stock, compras/documentos, productos/recetas admin, dashboard, costes, SQLite/API/exe, migración completa, eliminación de Streamlit.

## Composición

Reutilizar `configure_for_flet()` (sin nuevo composition root). Inyectar `data_path` en tests. Una sola `AppData`.

## Presentación propuesta (adaptar al repo sin carpetas vacías)

```
app/presentation/flet/
  …(restaurante existente)…
  session_bridge.py          # ampliar: enter_terminal_inventario
  presenters/terminal_inventario_presenter.py
  views/login_inventario_view.py   # o selector compartido de terminal
  views/… caducidad / merma / alertas / ajustes …
```

Entrada: ampliar `main.py` / shell con modo Inventario **o** módulo de arranque dedicado; no mezclar reglas de Restaurante en el mismo presenter.

## Reglas obligatorias

- Sin imports de Streamlit / `app.pages` / `session_state`.
- Viewmodels **sin** coste, precio, margen, importe, € (más estricto que Streamlit merma/ajustes actuales, que aún muestran economía en UI).
- Denegación real de `CONSULTAR_COSTES` / config / gestor / compras por `terminal_id`.
- FIFO, stock, atomicidad, actor y snapshots vía servicios existentes.
- Caducidad = merma con motivo `EXPIRACION` (sin inventar reglas).

## Riesgo P1 conocido (tratar al inicio)

`require_usecase(..., deny_terminal=True)` bloquea mutaciones a **todo** `actor_type=="terminal"`.  
Efecto: `aplicar_ajuste` y mutaciones de alertas fallan hoy también para Inventario.

**Corrección mínima prevista (dominio/auth, no Flet cosmético):**

- Permitir mutaciones de inventario cuando `terminal_id == terminal_inventario` **y** el permiso de inventario aplica; o introducir `deny_terminal` más fino (`deny_terminal_restaurante` / allowlist).
- Tests: autorización terminal inventario puede ajustar/alertar; restaurante sigue denegado; economía sigue denegada.
- Archivos candidatos: `app/core/auth/usecase_guard.py`, callers en `ajuste_service` / `alert_service`, tests `test_autorizacion_*` / nuevos tests Flet Inventario.

No ampliar a traslados/recuentos en el mismo cambio salvo que el shell los exponga (hoy no).

## Fases de implementación (cuando se autorice)

0. Baseline verde + demo intacto (sin re-auditoría completa).  
1. Auth bridge Inventario + denegación economía (tests).  
2. Ajuste `deny_terminal` mínimo + tests de frontera.  
3. Presenter + viewmodels (Alertas lectura, Caducidad, Merma, Ajustes).  
4. UI Flet táctil (sin €).  
5. Tests: composición, auth, merma/caducidad/ajuste, persistencia, sin economía, smoke.  
6. Guard arquitectónico (reutilizar patrones Flet).  
7. Docs `docs/flet_terminal_inventario.md` + actualizar readiness.  
8. Commits pequeños; push solo con gates verdes.

## Gates de aceptación

- Tests Flet Inventario + runner canónico + browser Streamlit.  
- Demo canónico intacto.  
- Streamlit intacto como referencia.  
- Sin información económica en VMs.  
- Mutaciones de alcance permitido funcionan para `terminal_inventario`.  
- Validación manual pendiente tras implementación.

## No hacer

No migrar persistencia, no añadir API/SQLite, no corregir P2 Streamlit, no empezar Administración, no fusionar presenters Restaurante/Inventario.
