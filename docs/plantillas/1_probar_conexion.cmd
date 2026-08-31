@echo off
setlocal EnableExtensions
REM Comprueba conexion BM + dry-run del Excel de trabajo.
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
if defined BM_EXE (
  "%BM_EXE%" --bm-import-excel --check --path "%BM_DATOS%"
) else (
  "%PY%" "%ROOT%\scripts\import_registro_operativo_excel.py" --check --path "%BM_DATOS%"
)
if errorlevel 1 (
  echo FALLO de conexion.
  pause
  exit /b 1
)

echo.
if exist "%XLSX%" (
  echo === 2^) Dry-run del Excel ^(si hay lineas^) ===
  echo Excel: %XLSX%
  if defined BM_EXE (
    "%BM_EXE%" --bm-import-excel "%XLSX%" --path "%BM_DATOS%" --dry-run
  ) else (
    "%PY%" "%ROOT%\scripts\import_registro_operativo_excel.py" "%XLSX%" --path "%BM_DATOS%" --dry-run
  )
) else (
  echo Plantilla no encontrada: %XLSX%
  echo Debe estar junto a este .cmd.
)
echo.
echo Si pone CONECTADO, importa con 2_importar_a_bm.cmd
pause
