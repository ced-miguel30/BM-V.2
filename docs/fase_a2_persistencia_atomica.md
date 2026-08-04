# Persistencia JSON atómica (Fase A2)

## Unidad transaccional

El estado canónico de dominio vive en **un único JSON**
(`data/demo/datos_hotel.json`, o override de test vía `get_demo_file()`).

Otros ficheros (`exports/**/_meta*.json`, binarios en `data/documentos/`)
**no** forman parte de la misma transacción atómica.

## API

Módulo: [`app/core/storage/json_atomic.py`](../app/core/storage/json_atomic.py)

| Pieza | Rol |
|-------|-----|
| `JsonWriteLock` / `json_write_lock` | Exclusión mutua por destino |
| `atomic_write_json` | temp → write → **flush** → **fsync** → close → `os.replace` → fsync dir |
| `transactional_update` | lock → leer fresco → deepcopy → mutar → validar → write |
| `cleanup_stale_temps` | Borra solo `*.tmp.*` obsoletos |

`save_json` delega en `atomic_write_json` (con `BM_TEST_ISOLATION` de A1).

## Límites del bloqueo

- Prototipo **servidor único** / filesystem compartido.
- Coordina hilos y procesos locales vía fichero `*.lock` (`O_EXCL`).
- **No** sustituye transacciones PostgreSQL.
- **No** coordina varios servidores sin lock/FS compartido.

## Adjuntos

`os.replace` del JSON **no** hace atómica la operación JSON + binario.
Staging, publicación, commit JSON y compensación = fases documentales
posteriores (fuera de A2).

## Fallos

| Momento | Efecto |
|---------|--------|
| Validación / serialización / escritura temp / fsync / `os.replace` | Destino intacto; temporal eliminado; error |
| Tras `os.replace`, fsync de directorio falla | Destino **ya** sustituido; `dir_synced=False`; no se afirma rollback |
