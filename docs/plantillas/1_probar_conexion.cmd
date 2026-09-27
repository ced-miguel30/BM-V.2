@echo off
setlocal EnableExtensions
REM Comprueba conexion BM + dry-run del Excel operativo (no guarda).
call "%~dp0_bm_excel_common.cmd"

if not "%~1"=="" set "XLSX=%~1"
if not "%~2"=="" set "BM_DATOS=%~2"

if not defined BM_EXE if not defined PY (
  echo No encuentro BM-Launcher ni Python de desarrollo.
  echo Servidor: C:\Apps\BM-V2\BM-Launcher.exe
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
echo Datos: %BM_DATOS%
if defined PY (
  "%PY%" "%ROOT%\scripts\import_registro_operativo_excel.py" --check --path "%BM_DATOS%"
) else (
  "%BM_EXE%" --bm-import-excel --check --path "%BM_DATOS%"
)
if errorlevel 1 (
  echo FALLO de conexion.
  pause
  exit /b 1
)

echo.
if exist "%XLSX%" (
  echo === 2^) Dry-run ^(no guarda^) ===
  echo Excel: %XLSX%
  if defined PY (
    "%PY%" "%ROOT%\scripts\import_registro_operativo_excel.py" "%XLSX%" --path "%BM_DATOS%" --dry-run
  ) else (
    "%BM_EXE%" --bm-import-excel "%XLSX%" --path "%BM_DATOS%" --dry-run
  )
) else (
  echo No hay Excel: %XLSX%
  echo Rellene registro_desayuno_operativo_ACTUALIZADA.xlsx en esta carpeta.
)
echo.
echo Si pone CONECTADO / DRY-RUN OK o SKIP, use:
echo   2_importar_a_bm.cmd
pause
