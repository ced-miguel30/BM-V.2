@echo off
setlocal EnableExtensions
REM IMPORT REAL de UN Excel a BM.
REM Uso recomendado:
REM   - Arrastre un archivo de registros_por_dia\ sobre este .cmd
REM   - O: 2_importar_a_bm.cmd "ruta\03-09.xlsx"
REM NO use la plantilla vacía ACTUALIZADA sin filas (fallara a proposito).
call "%~dp0_bm_excel_common.cmd"

if not "%~1"=="" set "XLSX=%~1"
if not "%~2"=="" set "BM_DATOS=%~2"

REM Bloquear plantilla vacia por nombre (salvo FORCE_PLANTILLA=1)
for %%I in ("%XLSX%") do set "XLSX_NAME=%%~nxI"
if /I "%XLSX_NAME%"=="registro_desayuno_operativo_ACTUALIZADA.xlsx" if not "%FORCE_PLANTILLA%"=="1" (
  echo.
  echo ERROR: ese archivo es la PLANTILLA vacia, no el registro del dia.
  echo.
  echo Use uno de estos:
  echo   - Arrastre un Excel de registros_por_dia\ sobre este .cmd
  echo   - 2_importar_a_bm.cmd "registros_por_dia\03-09.xlsx"
  echo   - 3_importar_carpeta_dias.cmd
  echo.
  pause
  exit /b 1
)

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
  echo Ponga el Excel del DIA en registros_por_dia\ y arrastrelo aqui,
  echo o ejecute 3_importar_carpeta_dias.cmd
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
