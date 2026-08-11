# Shared multi-PC JSON storage

This document describes how BM V.2 coordinates several PCs writing the same
AppData JSON over a shared filesystem (SMB/NAS). Storage remains **JSON only**
(no SQLite).

## Pieces

| Piece | Role |
| --- | --- |
| `meta.revision` | Monotonic integer in `datos_hotel.json`; bumped on every coordinated save |
| `{data_file}.bm_shared.lock` | Exclusive lease lock (JSON payload: user, host, pid, operation, lease) |
| `coordinated_save` | Acquire lock → reload disk → check revision → bump → atomic write → release |
| Client `config.json` | Stores **only** `shared_root` under `%LOCALAPPDATA%/BM-V2-client` (or `~/.bm-v2-client`) |

Do **not** hold the shared lock across UI interactions. Acquire, write, release.

## Revision

- Missing `meta.revision` loads as `0` (backward compatible).
- On save, memory must match disk (`expected_revision`) or, if omitted, memory
  revision must not be lower than disk.
- Conflict → `SharedRevisionConflict`; `FileBackedAppDataStore.persist` reloads
  from disk and re-raises a clear message. Callers should refresh and retry.

## Locks

- Created with `O_CREAT | O_EXCL`; default lease **60s**.
- **Reentrant**: same host + same pid may reclaim.
- **Same host**, pid dead → reclaim.
- **Remote host**: never reclaim just because the PID looks dead locally; only
  when `lease_until` expired **and** lock file mtime is older than lease + grace.
- Corrupt lock: reclaim only after documenting and waiting lease grace.

## Disconnect policy (no local fallback)

If the shared path is unreachable (missing parent, network share down, probe
write fails), raise `SharedPathUnavailable`. The app must **not** silently
switch to a local demo/copy. Operators fix connectivity or reconfigure
`shared_root`.

## Path precedence

1. `BM_INSTANCE_ROOT` — instance root (`data/`, `backups/`, …)
2. `BM_SHARED_ROOT` — alternate env for the same idea (instance root)
3. Client config `shared_root`
4. Default / repo demo via `get_demo_file()`

`BM_DEMO_FILE` may still override the **exact** JSON path (tests).  
`apply_shared_root(path)` validates R/W, then sets `BM_INSTANCE_ROOT` and
`BM_DEMO_FILE=…/data/datos_hotel.json` for the current process. It refuses the
canonical repo demo path as a production shared root.

## Related modules

- `app/core/storage/shared_coordinator.py`
- `app/core/storage/instance_config.py`
- `app/core/application/adapters/memory_stores.py` (`FileBackedAppDataStore`)
