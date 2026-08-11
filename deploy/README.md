# deploy/ — instalación local (estrategia C)

- P1: [`docs/deploy_local_p1.md`](../docs/deploy_local_p1.md)
- P2: [`docs/deploy_local_p2.md`](../docs/deploy_local_p2.md)

1. Copiar `config.example.env` → `config.env` (no commitear). Ajustar `BM_INSTANCE_ROOT`.
2. Crear/activar `.venv` e instalar `requirements.txt`.
3. `windows\prepare_env.cmd`
4. Arrancar **solo uno**: `start_launcher.cmd` **o** `start_streamlit.cmd`
5. Backup: `backup.cmd` / verify / restore según docs.
6. Release revisable: `build_release.cmd RUTA\release`
7. Migración adjuntos históricos (preview): `migrate_adjuntos.cmd`
