@echo off
setlocal EnableExtensions
cd /d "%~dp0\..\.."
if not defined BM_DEPLOY_CONFIG if exist "deploy\config.env" set "BM_DEPLOY_CONFIG=%CD%\deploy\config.env"
echo [BM] migrate-adjuntos PREVIEW — use --apply via CLI para copiar
python -m app.core.deploy.cli migrate-adjuntos %*
exit /b %ERRORLEVEL%
