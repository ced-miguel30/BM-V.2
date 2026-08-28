@echo off
setlocal
REM Comprueba conexion BM + dry-run del Excel de trabajo.
cd /d "%~dp0\..\.."
set "ROOT=%CD%"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "XLSX=%ROOT%\docs\plantillas\registro_desayuno_operativo_LISTA_ACTUALIZADA_ACTUALIZADA.xlsx"
set "BM_DATOS=%LOCALAPPDATA%\BM-V2-local\data\datos_hotel.json"

if not "%~1"=="" set "XLSX=%~1"
if not "%~2"=="" set "BM_DATOS=%~2"

if not exist "%PY%" (
  echo No encuentro Python del proyecto: %PY%
  pause
  exit /b 1
)
if not exist "%BM_DATOS%" (
  echo No encuentro datos BM: %BM_DATOS%
  pause
  exit /b 1
)

echo.
echo === 1^) Conexion a la base BM ===
"%PY%" "%ROOT%\scripts\import_desayuno_excel_operativo.py" --check --path "%BM_DATOS%"
if errorlevel 1 (
  echo FALLO de conexion.
  pause
  exit /b 1
)

echo.
if exist "%XLSX%" (
  echo === 2^) Dry-run del Excel ^(si hay lineas^) ===
  echo Excel: %XLSX%
  "%PY%" "%ROOT%\scripts\import_desayuno_excel_operativo.py" "%XLSX%" --path "%BM_DATOS%" --dry-run
) else (
  echo Plantilla no encontrada: %XLSX%
  echo Ejecuta regenerar_plantilla.cmd ^(cierra el Excel antes^).
)
echo.
echo Si pone CONECTADO, importa con 2_importar_a_bm.cmd
pause
