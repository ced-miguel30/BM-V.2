# Plan — empaquetado y despliegue local

**Estado:** estrategia **C** (Python administrado) en producción documental P1/P2;
prototipo **A** (PyInstaller onedir) disponible en `packaging/` + `deploy/windows/build_exe.cmd`.

## Artefacto A (prototipo)

```powershell
deploy\windows\build_exe.cmd
# → dist\BM-Launcher\BM-Launcher.exe
```

- Runtime hook: `%LOCALAPPDATA%\BM-V2-local` (no usa `BM-V2-pilot`).
- No commitear `dist/` ni `build/`.
- Firma Authenticode / AV: pendiente de piloto.

Ver `docs/operations_go_live.md`.

---

# Plan histórico (sin construir `.exe` inicialmente)


## Objetivo de la primera instalación controlada

Entregar BM‑V.2 en un **PC Windows del hotel** de forma reproducible, con:

- acceso unificado al launcher Flet;
- datos productivos **separados** del demo canónico;
- Streamlit disponible para administración amplia;
- rollback y backup claros;
- sin SQLite/API/servidor central en esta fase.

## Contexto técnico asumido

| Tema | Asunción inicial (validar in situ) |
|------|-------------------------------------|
| SO objetivo | Windows 10/11 x64 (servidor/caja del hotel) |
| Entrypoint Flet a empaquetar (candidato) | `python -m app.presentation.flet.main_launcher` |
| Entrypoints Flet específicos | Conservados para soporte |
| Streamlit | `streamlit run app/main.py` (mismo JSON productivo vía `BM_DEMO_FILE` o equivalente documentado) |
| Persistencia | JSON file-backed (`FileBackedAppDataStore`) |
| Demo canónico | Solo lectura de referencia; **nunca** como store productivo |

## Estrategias comparadas

### A. Ejecutable único con launcher Flet

| | |
|--|--|
| Valor | Un icono; operador elige Restaurante / Inventario / Admin operativa |
| Dependencias | Empaquetador (p. ej. PyInstaller/flet pack); runtime embebido; política antivirus |
| Riesgo | Medio–alto (falsos positivos AV; tamaño; updates; Flet + Streamlit dual) |
| Alcance | Un `.exe`/`app` Flet + procedimiento aparte para Streamlit o segundo artefacto |
| Exclusiones | Instalar ya SQLite/API; migrar Settings a Flet |
| Cuándo | Tras piloto estable con C |

### B. Ejecutables separados por terminal

| | |
|--|--|
| Valor | Aislamiento por puesto (caja cocina vs almacén) |
| Dependencias | 3 empaquetados + posibles shortcuts |
| Riesgo | Alto de deriva de versiones; peor mantenimiento |
| Alcance | Tres binarios + mismos datos JSON compartidos |
| Exclusiones | Launcher unificado |
| Cuándo | Solo si el hotel exige máquinas distintas sin menú común |

### C. Entorno Python administrado + accesos directos (antes del `.exe`)

| | |
|--|--|
| Valor | Instalación controlada rápida; mismos entrypoints que desarrollo; fácil diagnóstico |
| Dependencias | Python 3.x fijado; `requirements.txt`; scripts `.bat`/accesos directos; carpeta de datos |
| Riesgo | Bajo–medio (disciplina de paths y backups); requiere alguien técnico en el primer despliegue |
| Alcance | Venv + shortcuts: launcher Flet, Streamlit Settings, opcional verticales sueltas |
| Exclusiones | `.exe` todavía |
| Cuándo | **Primera instalación controlada en hotel** |

## Recomendación

**C** para la primera instalación controlada.

Motivos: el launcher ya unifica Flet; el riesgo real del hotel es **datos y operación**, no el branding del instalador; C permite validar `BM_DEMO_FILE`, backups y convivencia Streamlit/Flet **antes** de pelear con firma AV del `.exe`. A queda como fase siguiente cuando C esté estable en producción.

## Temas de estudio (checklist de diseño)

1. **SO / hardware** — Windows x64; disco local; UPS recomendable.
2. **Entrypoint** — launcher Flet como acceso diario; Streamlit para Settings.
3. **JSON productivo** — ruta fija fuera del repo (p. ej. `%ProgramData%\BM-V2\datos_hotel.json` o carpeta del hotel).
4. **Demo vs real** — demo canónico intacto en el árbol de instalación de solo lectura; productivo solo vía variable/path de datos.
5. **Permisos FS** — usuario de servicio con RW en carpeta de datos; resto RO.
6. **Backup / restore** — copia diaria del JSON + procedimiento documentado (Settings Streamlit ya tiene restauración; no ampliar aquí).
7. **Logs** — dónde van stdout/stderr de shortcuts; rotación mínima.
8. **Cierre seguro** — no matar proceso a mitad de `uow.commit`; documentar “cerrar ventana tras confirmar operaciones”.
9. **Variables** — `BM_DEMO_FILE` (o nombre definitivo productivo), `BM_FLET_VIEW=desktop`.
10. **Streamlit + Flet** — mismo archivo de datos; **no** dos escritores concurrentes sin procedimiento (turno/caja única o “un proceso a la vez” en v1).
11. **Instalación / update** — carpeta versionada; reemplazo de código; datos fuera.
12. **Firma / reputación** — pendiente si se pasa a A (certificado Authenticode).
13. **Antivirus** — esperable en A; en C menor fricción.
14. **Rollback** — conservar versión N‑1 del código + backup JSON previo.
15. **Equipo limpio** — prueba en VM Windows sin Python previo (para C: instalar Python; para A: solo exe).
16. **Red** — v1 local; sin servidor central.
17. **Multiusuario / concurrencia** — JSON no es multi-escritor seguro; gate de parada si el hotel exige 2 cajas simultáneas sobre el mismo fichero.
18. **Límites JSON** — tamaño, corrupción parcial, falta de transacciones distribuidas.
19. **Criterios para SQLite/API/central** — concurrencia real, varios PCs, auditoría remota, o corrupción recurrente.

## Gates de parada (no avanzar a `.exe` si fallan)

| Gate | Condición de parada |
|------|---------------------|
| G0 | Demo canónico o productivo mezclados |
| G1 | Dos procesos escribiendo el mismo JSON sin protocolo |
| G2 | Sin backup automático/procedimentado |
| G3 | Launcher/Streamlit no apuntan al mismo store productivo |
| G4 | Incidencia P0/P1 abierta en Flet o persistencia |
| G5 | Hotel exige multi-caja concurrente → replantear almacenamiento **antes** de empaquetar |

## Fases propuestas (sin ejecutar todavía)

| Fase | Contenido | Entregable | Stop si… |
|------|-----------|------------|----------|
| P1 | Inventario paths, variables, scripts Windows, backup ops | `docs/deploy_local_p1.md` + `deploy/` | Paths ambiguos / G0–G5 |
| P2 | Adjuntos/exports en instancia, release, simulación limpia | `docs/deploy_local_p2.md` | P2-G0–G9 |
| P3 | Piloto hotel 1–2 semanas (físico) | Informe operativo | P0/P1 o concurrencia |
| P4 | Decisión A (exe) vs permanecer en C | ADR breve | AV/firma bloquean sin remedio |
| P5 | Solo si P4=A: prototipo exe **firmado** + prueba limpia | Artefacto piloto | Fallo gates |

## Prompt ejecutable (fase P1 — planificación técnica, sin `.exe`)

```text
BM-V.2 — fase P1 de despliegue local (SOLO planificación / scripts de instalación Python).

PRECONDICIÓN: launcher Flet APROBADO; HEAD en origin/main tras cierre launcher;
demo canónico intacto; docs/flet_packaging_plan.md vigente; estrategia recomendada = C.

OBJETIVO: documentar e implementar únicamente lo mínimo de un entorno Python administrado
para el hotel: carpeta de datos productiva separada del demo, variables BM_*,
accesos directos/scripts para main_launcher y Streamlit, procedimiento de backup/restore
del JSON, y checklist de equipo limpio.

NO construir .exe, instalador MSI, SQLite, API, servidor central, ni migrar Streamlit.
NO publicar el demo ni exports/semanal/.
Detente ante gates G0–G5 del plan de empaquetado.
```

## Explicaciones al hotel (una frase)

Primero se instala como aplicación Python controlada con el mismo launcher que ya usan; el `.exe` solo se valora cuando datos, backups y uso diario estén estables.
