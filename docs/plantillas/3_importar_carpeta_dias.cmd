@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM Importa TODOS los Excel de registros_por_dia\ a BM (uno tras otro).
REM Idempotente: dias ya importados salen como SKIP.
call "%~dp0_bm_excel_common.cmd"

if not "%~1"=="" set "DIR_DIAS=%~1"
if not "%~2"=="" set "BM_DATOS=%~2"

if not defined BM_EXE if not defined PY (
  echo No encuentro BM-Launcher ni Python.
  pause
  exit /b 1
)
if not exist "%BM_DATOS%" (
  echo No encuentro datos: %BM_DATOS%
  pause
  exit /b 1
)
if not exist "%DIR_DIAS%" (
  echo No existe carpeta de dias: %DIR_DIAS%
  echo Cree registros_por_dia\ y copie ahi los Excel dd-mm.xlsx
  pause
  exit /b 1
)

echo.
echo === IMPORT CARPETA DE DIAS ===
echo Carpeta: %DIR_DIAS%
echo Datos  : %BM_DATOS%
if defined BM_EXE echo Programa: %BM_EXE%
echo.
echo Se descontara stock por cada archivo con filas.
pause

set "N=0"
set "FAIL=0"
for %%F in ("%DIR_DIAS%\*.xlsx") do (
  set "NOM=%%~nxF"
  if /I not "!NOM!"=="registro_desayuno_operativo_ACTUALIZADA.xlsx" (
    echo.
    echo ----- !NOM! -----
    set /a N+=1
    if defined PY (
      "%PY%" "%ROOT%\scripts\import_registro_operativo_excel.py" "%%~fF" --path "%BM_DATOS%"
    ) else (
      "%BM_EXE%" --bm-import-excel "%%~fF" --path "%BM_DATOS%"
    )
    if errorlevel 1 set /a FAIL+=1
  )
)

echo.
echo Archivos procesados: %N%  fallos: %FAIL%
if "%N%"=="0" (
  echo No habia .xlsx en la carpeta. Copie los Excel del dia a:
  echo   %DIR_DIAS%
)
echo.
echo Abra BM y revise Desayuno - Historial / Administracion - mes.
pause
if not "%FAIL%"=="0" exit /b 2
exit /b 0
