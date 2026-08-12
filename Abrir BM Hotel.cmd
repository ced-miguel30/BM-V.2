@echo off
REM Doble clic: abre BM-V.2 (launcher Flet) igual que en terminal.
REM Preferencia: Python del proyecto (.venv) para que la UI coincida con el codigo.
REM Solo usa BM-Launcher.exe si se fuerza BM_USE_EXE=1 o no hay Python.
setlocal EnableExtensions
cd /d "%~dp0"

if not defined BM_FLET_VIEW set "BM_FLET_VIEW=desktop"
if not defined BM_DEPLOY_CONFIG if exist "%~dp0deploy\config.env" (
    set "BM_DEPLOY_CONFIG=%~dp0deploy\config.env"
)

set "PY="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY=%~dp0.venv\Scripts\python.exe"
) else (
    where py >nul 2>&1 && set "PY=py"
)

if defined PY (
    "%PY%" -m app.presentation.flet.main_launcher
    exit /b %ERRORLEVEL%
)

set "EXE=%~dp0dist\BM-Launcher\BM-Launcher.exe"
if /I "%BM_USE_EXE%"=="1" if exist "%EXE%" (
    start "" "%EXE%"
    exit /b 0
)
if exist "%EXE%" (
    echo [BM] Aviso: no hay .venv; usando ejecutable empaquetado (puede estar desactualizado).
    start "" "%EXE%"
    exit /b 0
)

echo [BM] No hay Python (.venv) ni BM-Launcher.exe.
echo     Ejecute prepare_env.cmd o: .\.venv\Scripts\python.exe -m app.presentation.flet.main_launcher
echo.
pause
exit /b 1
