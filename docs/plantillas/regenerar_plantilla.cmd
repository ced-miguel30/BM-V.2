@echo off
setlocal
REM Regenera la plantilla Excel de trabajo (preserva hojas de registro).
cd /d "%~dp0\..\.."
set "ROOT=%CD%"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "BM_DATOS=%LOCALAPPDATA%\BM-V2-local\data\datos_hotel.json"
set "OUT=%ROOT%\docs\plantillas\registro_desayuno_operativo_ACTUALIZADA.xlsx"

if not "%~1"=="" set "BM_DATOS=%~1"

echo Regenerando plantilla operativa (desayuno, comida, cena, buffet) desde:
echo   %BM_DATOS%
echo   Destino: %OUT%
echo.
"%PY%" "%ROOT%\scripts\build_plantilla_desayuno_excel.py" --path "%BM_DATOS%" --out "%OUT%"
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
