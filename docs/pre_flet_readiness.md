# Pre-Flet readiness — BM-V.2

## Estado

| Vertical | Estado |
|----------|--------|
| Terminal Restaurante | **APROBADA** + refresh multiclinte |
| Terminal Inventario | **APROBADA** + refresh multiclinte |
| Administración Flet | **APROBADA** — dashboard, catálogos, docs, zona peligro, servidor |
| Launcher | **APROBADO** |
| Storage compartido | **Implementado** (`.bm_shared.lock` + `meta.revision`) |
| Empaquetado | Prototipo PyInstaller onedir |

## Docs operativos

- `docs/operations_go_live.md` — carga de datos
- `docs/operations_multi_pc.md` — tres PCs + UNC
- `docs/shared_storage.md` — locks y revisión

## Siguiente paso humano

Configurar la carpeta compartida real del hotel e instalar en PC1–PC3.
