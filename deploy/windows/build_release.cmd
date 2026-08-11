@echo off
setlocal EnableExtensions
cd /d "%~dp0\..\.."
if "%~1"=="" (
  echo Uso: build_release.cmd RUTA\carpeta_release
  exit /b 2
)
python -m app.core.deploy.cli build-release "%~1" --overwrite
exit /b %ERRORLEVEL%
