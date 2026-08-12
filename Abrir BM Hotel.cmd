@echo off
REM Doble clic: abre BM-V.2 (launcher Flet).
REM Usa BM-Launcher.exe si existe; si no, Python del proyecto (.venv o py).
setlocal EnableExtensions
cd /d "%~dp0"

set "EXE=%~dp0dist\BM-Launcher\BM-Launcher.exe"
if exist "%EXE%" (
    start "" "%EXE%"
    exit /b 0
)

set "PY="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY=%~dp0.venv\Scripts\python.exe"
) else (
    where py >nul 2>&1 && set "PY=py"
)
if not defined PY (
    echo [BM] No hay ejecutable ni Python. Ejecute prepare_env o build_exe.cmd
    echo.
    pause
    exit /b 1
)

if not defined BM_FLET_VIEW set "BM_FLET_VIEW=desktop"
if not defined BM_DEPLOY_CONFIG if exist "%~dp0deploy\config.env" (
    set "BM_DEPLOY_CONFIG=%~dp0deploy\config.env"
)

"%PY%" -m app.presentation.flet.main_launcher
exit /b %ERRORLEVEL%
