# Despliegue local P2 — instancia completa y piloto físico pendiente

## Estado

| Dimensión | Estado |
|-----------|--------|
| P1 (Python administrado) | **APROBADA técnicamente** |
| P2 (adjuntos/exports/backup/release) | **Implementada y probada automáticamente** |
| Piloto físico Windows | **Pendiente** |
| Multiusuario / multi-caja | **No soportado** |
| `.exe` / MSI | **No** |

**Veredicto técnico P2:** aprobado automáticamente — **piloto físico pendiente**.

## Contrato final de instancia (`BM_INSTANCE_ROOT`)

| Ruta | Uso |
|------|-----|
| `data/datos_hotel.json` | JSON productivo |
| `data/documentos/` | Adjuntos productivos |
| `backups/` | ZIP schema v2 + sidecars |
| `logs/` | Diagnóstico operativo |
| `exports/` | Exports productivos (semanal, documentos, historial) |
| `temp/` | Temporales de instancia (si se usan) |

Perfil `hotel` **exige** `BM_INSTANCE_ROOT`. Ningún mutable productivo se escribe en el clon del repo (`data/documentos/`, `exports/`). El demo permanece solo referencia.

## Adjuntos

- Referencia lógica persistida: `data/documentos/{id}/{nombre}` (nunca path absoluto personal).
- Escritura hotel → solo instancia.
- Lectura hotel → instancia; si falta, **compat** con `<repo>/data/documentos/...` (histórico, sin migrar ni borrar).
- Path traversal y absolutos rechazados.
- Migración explícita (preview/copia, no destructiva):
  `python -m app.core.deploy.cli migrate-adjuntos` / `--apply`.

## Exports

- Hotel → `<BM_INSTANCE_ROOT>/exports/…`
- Dev → `<repo>/exports/` (compatible)
- `exports/semanal/` local del repo sigue **excluido de Git/publicación**

## Backup v2 — contenido definitivo

Incluye por defecto:

- `appdata.json` (+ compat sesión)
- snapshot JSON en disco (opcional)
- adjuntos referenciados bajo `data/documentos/`
- `manifest.json` con SHA-256

**Política exports en backup: B — excluidos** (regenerables desde datos operativos).  
Opt-in: `generar_backup_zip(..., include_exports=True)` solo si se documenta necesidad.

Restore: valida manifiesto/hashes; preventivo; hotel solo dentro de `BM_INSTANCE_ROOT`; JSON+adjuntos coherentes.

## Release Python administrada

```text
python -m app.core.deploy.cli build-release RUTA\release --overwrite
```

Copia código + demo de referencia + `RELEASE_MANIFEST.json` (git SHA, hash de `requirements.txt`).  
**Brecha:** no hay `requirements.lock`; pin exacto vía `pip freeze` tras piloto si se exige.

Actualización: reemplazar carpeta de aplicación; **no** tocar `BM_INSTANCE_ROOT`.  
Rollback de código: volver a carpeta N‑1; datos/adjuntos intactos. Rollback de datos: restore ZIP.

## Escritor único

Sin cambios de política: Flet **o** Streamlit, nunca ambos. Candado `.bm_writer.lock`.

## Checklist físico Windows (pendiente de ejecución real)

1. Confirmar Windows x64 y arquitectura.  
2. Confirmar permisos del usuario.  
3. Confirmar ubicación de `BM_INSTANCE_ROOT`.  
4. Instalar versión exacta de Python (≥ 3.10).  
5. Crear `.venv`.  
6. Instalar `requirements.txt`.  
7. Aplicar `deploy/config.env` desde la plantilla.  
8. Ejecutar `prepare`.  
9. Verificar que no se usa el demo (`diagnose` → `data_is_demo=false`).  
10. Datos iniciales mock o productivos aprobados.  
11. Backup inicial.  
12. Abrir launcher.  
13. Probar las tres verticales.  
14. Usuarios permitidos y denegados.  
15. Cerrar launcher.  
16. Abrir Streamlit.  
17. Cerrar Streamlit.  
18. Verificar bloqueo de simultaneidad.  
19. Añadir adjunto de prueba.  
20. Generar export de prueba.  
21. Reiniciar el equipo.  
22. Comprobar persistencia.  
23. Backup + verify.  
24. Restore controlado de prueba.  
25. Revisar logs.  
26. Simular actualización de código.  
27. Simular rollback de código.  
28. Confirmar conservación de datos.  
29. Confirmar ausencia de escrituras en el repositorio.  
30. Registrar incidencias P0–P3.

## Criterios de suspensión del piloto

- Escritura en demo o mutables del repo.  
- Segundo escritor activo.  
- Backup/restore incoherente.  
- Pérdida de adjuntos.  
- Exigencia de multi-caja concurrente (replantear almacenamiento).

## Próxima decisión tras el piloto físico

Mantener estrategia C endurecida, o valorar A (`.exe`) solo si el piloto es estable y AV/firma están resueltos.
