@echo off
setlocal EnableExtensions
REM IMPORT REAL a BM. Cierra el Excel y BM antes si puedes.
call "%~dp0_bm_excel_common.cmd"

if not "%~1"=="" set "XLSX=%~1"
if not "%~2"=="" set "BM_DATOS=%~2"

if not defined BM_EXE if not defined PY (
  echo No encuentro BM-Launcher ni Python de desarrollo.
  echo.
  echo Servidor: instale BM en C:\Apps\BM-V2\BM-Launcher.exe
  echo   o defina BM_LAUNCHER=ruta\BM-Launcher.exe
  echo.
  echo Desarrollo: ejecute desde docs\plantillas del repo BM V.2
  pause
  exit /b 1
)
if not exist "%XLSX%" (
  echo No encuentro Excel: %XLSX%
  echo Debe estar junto a este .cmd: registro_desayuno_operativo_ACTUALIZADA.xlsx
  pause
  exit /b 1
)
if not exist "%BM_DATOS%" (
  echo No encuentro datos: %BM_DATOS%
  pause
  exit /b 1
)

echo.
echo === IMPORT REAL A BM ===
echo Excel : %XLSX%
echo Datos : %BM_DATOS%
if defined BM_EXE echo Programa: %BM_EXE%
echo.
echo Se descontara stock. Continuar?
pause

if defined BM_EXE (
  "%BM_EXE%" --bm-import-excel "%XLSX%" --path "%BM_DATOS%"
) else (
  "%PY%" "%ROOT%\scripts\import_registro_operativo_excel.py" "%XLSX%" --path "%BM_DATOS%"
)
echo.
pause
