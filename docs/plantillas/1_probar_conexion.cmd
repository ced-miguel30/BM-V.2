@echo off
setlocal EnableExtensions
REM Comprueba conexion BM + dry-run.
REM Sin argumento: prueba el PRIMER Excel de registros_por_dia\ (no la plantilla vacia).
call "%~dp0_bm_excel_common.cmd"

if not "%~1"=="" set "XLSX=%~1"
if not "%~2"=="" set "BM_DATOS=%~2"

REM Si no pasaron Excel, coger primer dia de la carpeta
if /I "%XLSX%"=="%PLANTILLA_DIR%\registro_desayuno_operativo_ACTUALIZADA.xlsx" (
  if exist "%DIR_DIAS%" (
    for %%F in ("%DIR_DIAS%\*.xlsx") do (
      if /I not "%%~nxF"=="registro_desayuno_operativo_ACTUALIZADA.xlsx" (
        set "XLSX=%%~fF"
        goto :xlsx_ok
      )
    )
  )
)
:xlsx_ok

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
  echo No hay Excel de prueba. Ponga archivos en:
  echo   %DIR_DIAS%
)
echo.
echo Si pone CONECTADO / DRY-RUN OK o SKIP, use:
echo   2_importar_a_bm.cmd  ^(un dia^)
echo   3_importar_carpeta_dias.cmd  ^(todos los dias^)
pause
