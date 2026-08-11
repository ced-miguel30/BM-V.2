@echo off
setlocal EnableExtensions
cd /d "%~dp0\..\.."
if not defined BM_DEPLOY_CONFIG if exist "deploy\config.env" set "BM_DEPLOY_CONFIG=%CD%\deploy\config.env"
if "%~1"=="" (
  echo Uso: verify_backup.cmd ruta\al\backup.zip
  exit /b 2
)
python -m app.core.deploy.cli verify-backup "%~1"
exit /b %ERRORLEVEL%
