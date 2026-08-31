@echo off
REM Rutas comunes import/regenerar Excel (desarrollo + servidor BM-Launcher).
REM Llamar con: call "%~dp0_bm_excel_common.cmd"

set "PLANTILLA_DIR=%~dp0"
if "%PLANTILLA_DIR:~-1%"=="\" set "PLANTILLA_DIR=%PLANTILLA_DIR:~0,-1%"

set "XLSX=%PLANTILLA_DIR%\registro_desayuno_operativo_ACTUALIZADA.xlsx"
set "BM_DATOS=%LOCALAPPDATA%\BM-V2-local\data\datos_hotel.json"

set "BM_EXE="
if defined BM_LAUNCHER if exist "%BM_LAUNCHER%" set "BM_EXE=%BM_LAUNCHER%"
if not defined BM_EXE if exist "C:\Apps\BM-V2\BM-Launcher.exe" set "BM_EXE=C:\Apps\BM-V2\BM-Launcher.exe"

set "PY="
set "ROOT="
if exist "%PLANTILLA_DIR%\..\..\BM V.2\.venv\Scripts\python.exe" (
  set "ROOT=%PLANTILLA_DIR%\..\..\BM V.2"
  set "PY=%ROOT%\.venv\Scripts\python.exe"
) else if exist "%PLANTILLA_DIR%\..\..\.venv\Scripts\python.exe" (
  set "ROOT=%PLANTILLA_DIR%\..\.."
  set "PY=%ROOT%\.venv\Scripts\python.exe"
)

goto :eof
