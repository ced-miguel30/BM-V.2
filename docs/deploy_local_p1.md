# Despliegue local P1 — Python administrado (estrategia C)

## Estado

| Dimensión | Estado |
|-----------|--------|
| Diseño | **Hecho** |
| Implementación (scripts + módulo) | **Hecho** |
| Pruebas automáticas | **Hecho** (`tests.test_deploy_local_p1`) |
| Prueba en equipo limpio | **Pendiente** (checklist abajo) |
| Piloto hotel | **No iniciado** |
| Empaquetado `.exe` | **No** (fase posterior) |

**Veredicto técnico P1:** aprobado técnicamente — pendiente de piloto / equipo limpio.

## SO objetivo

**Supuesto provisional:** Windows 10/11 x64 (PC del hotel).  
La ruta de instancia (carpeta **BM-DATOS**) se parametriza con `BM_INSTANCE_ROOT`. Canónico exe / un PC: `%LOCALAPPDATA%\BM-V2-local`. Ver también [`hotel_dos_carpetas.md`](hotel_dos_carpetas.md).

## Contrato de directorios

| Rol | Ubicación típica | ¿En Git? |
|-----|------------------|----------|
| Aplicación (código) | Clone/copia del repo | Sí (código) |
| Entorno virtual | `.venv/` junto al repo | No |
| Configuración | `deploy/config.env` (desde `config.example.env`) | No |
| Datos productivos | `%BM_INSTANCE_ROOT%\data\datos_hotel.json` | No |
| Backups | `%BM_INSTANCE_ROOT%\backups\` | No |
| Logs | `%BM_INSTANCE_ROOT%\logs\` | No |
| Exports | `<repo>/exports/` (histórico app) | Residuos locales no publicables |
| Adjuntos | `<repo>/data/documentos/` | No (binarios) |
| Demo canónico | `<repo>/data/demo/datos_hotel.json` | Solo referencia; **nunca** productivo |

En perfil `hotel` es imposible usar el demo como JSON productivo (sin fallback silencioso).

## Variables

| Variable | Reutilizada / nueva | Finalidad |
|----------|---------------------|-----------|
| `BM_DEMO_FILE` | Reutilizada | JSON efectivo (productivo en hotel) |
| `BM_FLET_VIEW` | Reutilizada | `desktop` / `web` / `asgi` |
| `BM_FLET_TERMINAL` | Reutilizada | Router Flet |
| `BM_SKIP_WEEKLY_EXPORT` | Reutilizada | Smokes / Streamlit |
| `BM_TEST_ISOLATION` | Reutilizada | Solo tests |
| `BM_DEPLOY_PROFILE` | **Nueva** | `dev` \| `hotel` |
| `BM_INSTANCE_ROOT` | **Nueva** | Raíz de datos/backups/logs |
| `BM_DEPLOY_CONFIG` | **Nueva** | Ruta a `config.env` |
| `BM_DEPLOY_ALLOW_OPS` | **Nueva** | Solo scripts backup/restore (no persistir en operador) |

`BM_DEPLOY_PROFILE=hotel` sin `BM_DEMO_FILE` ni `BM_INSTANCE_ROOT` → error claro.

## Política de proceso escritor (gate de concurrencia)

- El JSON **no** es multiusuario seguro.
- `JsonWriteLock` (A2) solo cubre una escritura atómica, no dos UIs en sesión.
- **Condición C:** un único proceso escritor (Flet **o** Streamlit).
- Candado `{datos}.bm_writer.lock` + scripts que se rechazan mutuamente.
- Entrypoints con `prepare_runtime()` en perfil hotel respetan el candado.
- **Gate de concurrencia:** cerrado para piloto multi-caja; abierto solo “un escritor”.

## Scripts (Windows)

Bajo `deploy/windows/` (artefactos locales revisables; no crean iconos en el Escritorio):

| Script | Acción |
|--------|--------|
| `prepare_env.cmd` | Carpetas + siembra mock si falta JSON |
| `start_launcher.cmd` | Launcher Flet |
| `start_streamlit.cmd` | Streamlit Settings |
| `backup.cmd` | ZIP schema v2 + sha256 |
| `verify_backup.cmd` | Valida ZIP |
| `restore.cmd` | Restore con confirmación `RESTORE` |
| `diagnose.cmd` | Diagnóstico sin secretos |
| `release_writer.cmd` | Libera candado obsoleto |

Equivalente: `python -m app.core.deploy.cli <comando>`.

## Primer arranque (resumen)

1. Instalar Python ≥ 3.10.
2. Clonar/copiar el código en carpeta fija.
3. `python -m venv .venv` y activar.
4. `python -m pip install -r requirements.txt`
5. Copiar `deploy/config.example.env` → `deploy/config.env` y ajustar `BM_INSTANCE_ROOT`.
6. `deploy\windows\prepare_env.cmd`
7. `deploy\windows\backup.cmd` (primer backup).
8. `deploy\windows\start_launcher.cmd`
9. Streamlit solo con launcher cerrado: `start_streamlit.cmd`

## Backup / restore

Reutiliza `backup_service` / `restore_backup_service` (schema v2, manifiesto SHA-256).  
Ops de script requieren `BM_DEPLOY_ALLOW_OPS` (activado solo por el CLI).  
Restore crea preventivo canónico y exige `--confirm RESTORE`.

## Rollback de instalación

- Datos y backups viven fuera del árbol reemplazable de código.
- Revertir código: restaurar carpeta N‑1 del repo/venv.
- Revertir datos: `restore` desde ZIP en `backups/`.
- Desinstalar código **sin** borrar `BM_INSTANCE_ROOT`.

## Checklist equipo limpio (pendiente de ejecución real)

1. SO/arch Windows x64  
2. Python exacto documentado  
3. Obtención del código  
4. venv  
5. `pip install -r requirements.txt`  
6. Carpetas vía prepare  
7. config.env  
8. Carga/siembra productiva  
9. Primer backup  
10. Launcher  
11. Tres verticales + login  
12. Streamlit separado  
13. Política un escritor  
14. Cierre/reinicio  
15. Persistencia  
16. Restore de prueba  
17. Logs  
18. Usuario sin permisos  
19. Sin economía en terminales  
20. Rollback sin borrar datos  

## Limitaciones

- Adjuntos siguen bajo `<repo>/data/documentos/` (acoplados a `PROJECT_ROOT`).
- Exports semanales siguen bajo `<repo>/exports/`.
- No hay `.exe`, MSI, firma ni auto-update.
- No hay multi-escritor concurrente.
- Prueba en equipo limpio **no** declarada superada hasta ejecutarla.

## Criterios de parada → no pasar a piloto

- G0/G1 (este doc): demo mezclado o fallback silencioso.
- G2: dos escritores sin candado.
- G3: backup no verificable.
- G4: scripts dependen del cwd o rutas personales hardcodeadas.
- G5: rollback inseguro o tests sobre datos reales.
