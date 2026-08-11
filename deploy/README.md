# deploy/ — artefactos de instalación local (estrategia C)

Ver documentación completa: [`docs/deploy_local_p1.md`](../docs/deploy_local_p1.md).

1. Copiar `config.example.env` → `config.env` (no commitear).
2. Crear/activar `.venv` e instalar `requirements.txt`.
3. Ejecutar `windows\prepare_env.cmd`.
4. Arrancar con `windows\start_launcher.cmd` **o** `windows\start_streamlit.cmd` (nunca ambos a la vez).
