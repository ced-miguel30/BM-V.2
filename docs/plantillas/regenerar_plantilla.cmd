@echo off
setlocal EnableExtensions
REM Regenera la plantilla Excel (preserva hojas de registro). Solo desarrollo/servidor con BM.
call "%~dp0_bm_excel_common.cmd"

if not "%~1"=="" set "BM_DATOS=%~1"
set "OUT=%XLSX%"

if not defined BM_EXE if not defined PY (
  echo No encuentro BM-Launcher ni Python de desarrollo.
  pause
  exit /b 1
)

echo Regenerando plantilla operativa desde:
echo   %BM_DATOS%
echo   Destino: %OUT%
echo.
if defined BM_EXE (
  "%BM_EXE%" --bm-build-excel --path "%BM_DATOS%" --out "%OUT%"
) else (
  "%PY%" "%ROOT%\scripts\build_plantilla_desayuno_excel.py" --path "%BM_DATOS%" --out "%OUT%"
)
if errorlevel 1 (
  echo Fallo al guardar. Cierra el Excel e intentalo de nuevo.
  pause
  exit /b 1
)
echo.
echo Usa ESTE archivo:
echo   %OUT%
echo.
echo Importar: 2_importar_a_bm.cmd
pause
