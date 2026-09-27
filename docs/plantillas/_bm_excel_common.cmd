@echo off
REM Rutas comunes import Excel (D:\work + servidor).
REM Llamar con: call "%~dp0_bm_excel_common.cmd"

set "PLANTILLA_DIR=%~dp0"
if "%PLANTILLA_DIR:~-1%"=="\" set "PLANTILLA_DIR=%PLANTILLA_DIR:~0,-1%"

set "XLSX=%PLANTILLA_DIR%\registro_desayuno_operativo_ACTUALIZADA.xlsx"
set "DIR_DIAS=%PLANTILLA_DIR%\registros_por_dia"

REM --- BM_DATOS ---
if not defined BM_DATOS (
  if exist "%PLANTILLA_DIR%\..\2-BM-DATOS\data\datos_hotel.json" (
    set "BM_DATOS=%PLANTILLA_DIR%\..\2-BM-DATOS\data\datos_hotel.json"
  ) else if exist "%PLANTILLA_DIR%\..\..\2-BM-DATOS\data\datos_hotel.json" (
    set "BM_DATOS=%PLANTILLA_DIR%\..\..\2-BM-DATOS\data\datos_hotel.json"
  ) else (
    set "BM_DATOS=%LOCALAPPDATA%\BM-V2-local\data\datos_hotel.json"
  )
)

REM --- Python repo (prioridad; rutas literales, sin %% anidados) ---
set "PY="
set "ROOT="
if exist "C:\Users\User\Desktop\HOTEL\BM V.2\.venv\Scripts\python.exe" (
  set "ROOT=C:\Users\User\Desktop\HOTEL\BM V.2"
  set "PY=C:\Users\User\Desktop\HOTEL\BM V.2\.venv\Scripts\python.exe"
) else if exist "%PLANTILLA_DIR%\..\..\BM V.2\.venv\Scripts\python.exe" (
  set "ROOT=%PLANTILLA_DIR%\..\..\BM V.2"
  set "PY=%PLANTILLA_DIR%\..\..\BM V.2\.venv\Scripts\python.exe"
) else if exist "%PLANTILLA_DIR%\..\..\.venv\Scripts\python.exe" (
  set "ROOT=%PLANTILLA_DIR%\..\.."
  set "PY=%PLANTILLA_DIR%\..\..\.venv\Scripts\python.exe"
)

REM --- BM_EXE solo si no hay Python ---
set "BM_EXE="
if not defined PY (
  if defined BM_LAUNCHER if exist "%BM_LAUNCHER%" set "BM_EXE=%BM_LAUNCHER%"
  if not defined BM_EXE if exist "C:\Apps\BM-V2\BM-Launcher.exe" set "BM_EXE=C:\Apps\BM-V2\BM-Launcher.exe"
  if not defined BM_EXE if exist "%PLANTILLA_DIR%\..\1-BM-CODIGO\BM-Launcher.exe" set "BM_EXE=%PLANTILLA_DIR%\..\1-BM-CODIGO\BM-Launcher.exe"
  if not defined BM_EXE if exist "%PLANTILLA_DIR%\..\..\1-BM-CODIGO\BM-Launcher.exe" set "BM_EXE=%PLANTILLA_DIR%\..\..\1-BM-CODIGO\BM-Launcher.exe"
)

goto :eof
