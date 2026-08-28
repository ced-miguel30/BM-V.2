@echo off
setlocal
REM IMPORT REAL a BM. Cierra el Excel y BM antes si puedes.
cd /d "%~dp0\..\.."
set "ROOT=%CD%"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "XLSX=%ROOT%\docs\plantillas\registro_desayuno_operativo_LISTA_ACTUALIZADA_ACTUALIZADA.xlsx"
set "BM_DATOS=%LOCALAPPDATA%\BM-V2-local\data\datos_hotel.json"

if not "%~1"=="" set "XLSX=%~1"
if not "%~2"=="" set "BM_DATOS=%~2"

if not exist "%PY%" (
  echo No encuentro Python: %PY%
  pause
  exit /b 1
)
if not exist "%XLSX%" (
  echo No encuentro Excel: %XLSX%
  echo Regenera con regenerar_plantilla.cmd
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
echo.
echo Se descontara stock. Continuar?
pause

"%PY%" "%ROOT%\scripts\import_registro_operativo_excel.py" "%XLSX%" --path "%BM_DATOS%"
echo.
pause
