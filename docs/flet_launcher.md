# Launcher Flet mínimo — BM‑V.2

## Estado

**APROBADO TÉCNICAMENTE** — pendiente de validación manual.

No sustituye Streamlit ni las verticales existentes.

## Arranque unificado

```bash
python -m app.presentation.flet.main_launcher
```

| Variable | Efecto |
|----------|--------|
| `BM_DEMO_FILE` | JSON de datos |
| `BM_FLET_VIEW` | `desktop` (default), `web`, `asgi` |

Alternativa vía router:

```bash
BM_FLET_TERMINAL=launcher python -m app.presentation.flet.main
```

## Entrypoints específicos (conservados)

```bash
python -m app.presentation.flet.main                 # Restaurante (default)
BM_FLET_TERMINAL=inventario python -m app.presentation.flet.main
BM_FLET_TERMINAL=administracion python -m app.presentation.flet.main
python -m app.presentation.flet.main_inventario
python -m app.presentation.flet.main_administracion
```

## Comportamiento

- Muestra tres destinos: Restaurante, Inventario, Administración operativa.
- **Seleccionar no autentica ni concede permisos**; cada destino conserva su login.
- Antes de abrir un destino se hace `logout` de cualquier sesión previa (evita reutilizar actor).
- Composition única: `configure_for_flet()`.
- Indicación: *Configuración y administración completa: aplicación Streamlit.*
- Comando Streamlit documentado (no se lanza automáticamente): `streamlit run app/main.py`

## Autenticación por destino

| Destino | Auth |
|---------|------|
| Restaurante | Actor terminal restaurante al pulsar Entrar |
| Inventario | Actor terminal inventario al pulsar Entrar |
| Administración operativa | Login usuario Dir/Adm + `ACCEDER_CONFIGURACION` |

## Limitaciones

- Volver al launcher desde una vertical abierta requiere **reiniciar** la aplicación (ciclo de vida Flet / un solo montaje).
- No hay dashboard, métricas ni Settings amplio en Flet.
- Preparación futura a empaquetado: este entrypoint es el candidato a acceso único; **no** se construye `.exe` aquí.

## Tests

```bash
python -m unittest tests.test_flet_launcher -v
```
