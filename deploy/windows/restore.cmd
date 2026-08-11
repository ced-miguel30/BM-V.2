@echo off
setlocal EnableExtensions
cd /d "%~dp0\..\.."
if not defined BM_DEPLOY_CONFIG if exist "deploy\config.env" set "BM_DEPLOY_CONFIG=%CD%\deploy\config.env"
if "%~1"=="" (
  echo Uso: restore.cmd ruta\al\backup.zip
  echo Requiere confirmacion interactiva: el CLI exige --confirm RESTORE
  exit /b 2
)
echo ATENCION: se restaurara sobre el JSON productivo configurado.
echo Escriba RESTORE para confirmar:
set /p CONFIRM=
python -m app.core.deploy.cli restore "%~1" --confirm "%CONFIRM%"
exit /b %ERRORLEVEL%
