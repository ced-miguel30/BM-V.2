@echo off
setlocal EnableExtensions
REM IMPORT REAL del Excel operativo a BM.
REM Uso:
REM   - Rellene registro_desayuno_operativo_ACTUALIZADA.xlsx, cierre Excel
REM   - Doble clic en este .cmd
REM   - Opcional: arrastre otro .xlsx sobre este .cmd
call "%~dp0_bm_excel_common.cmd"

if not "%~1"=="" set "XLSX=%~1"
if not "%~2"=="" set "BM_DATOS=%~2"

if not defined BM_EXE if not defined PY (
  echo No encuentro BM-Launcher ni Python de desarrollo.
  echo.
  echo Servidor: instale BM en C:\Apps\BM-V2\BM-Launcher.exe
  echo   o defina BM_LAUNCHER=ruta\BM-Launcher.exe
  echo.
  pause
  exit /b 1
)
if not exist "%XLSX%" (
  echo No encuentro Excel: %XLSX%
  echo.
  echo Debe existir registro_desayuno_operativo_ACTUALIZADA.xlsx
  echo en esta carpeta, o arrastre un .xlsx sobre este .cmd.
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

if defined PY (
  "%PY%" "%ROOT%\scripts\import_registro_operativo_excel.py" "%XLSX%" --path "%BM_DATOS%"
) else (
  "%BM_EXE%" --bm-import-excel "%XLSX%" --path "%BM_DATOS%"
)
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo FALLO import ^(codigo %RC%^). Revise el mensaje de arriba.
) else (
  echo OK. Abra BM - Terminal Restaurante - Desayuno - Historial
  echo    o Administracion - Inicio - mes correspondiente.
)
pause
exit /b %RC%
