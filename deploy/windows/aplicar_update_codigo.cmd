@echo off
REM Copia dist\BM-Launcher a la carpeta BM-CODIGO-UPDATE del escritorio.
REM Cierre BM-Launcher.exe antes de ejecutar.
setlocal EnableExtensions
cd /d "%~dp0\..\.."

set "SRC=%CD%\dist\BM-Launcher"
set "DST=%~1"
if "%DST%"=="" set "DST=%~dp0..\..\BM-CODIGO-UPDATE-tpv-ocr-20260826"

if not exist "%SRC%\BM-Launcher.exe" (
  echo ERROR: No hay build. Ejecute deploy\windows\build_exe.cmd primero.
  exit /b 1
)

echo Origen:  %SRC%
echo Destino: %DST%
echo.
echo Cierre BM-Launcher si esta abierto...
timeout /t 3 /nobreak >nul

if exist "%DST%\_internal" rmdir /s /q "%DST%\_internal"
if exist "%DST%\BM-Launcher.exe" del /f /q "%DST%\BM-Launcher.exe"
if exist "%DST%\BM-Launcher.exe.NUEVO" del /f /q "%DST%\BM-Launcher.exe.NUEVO"
if exist "%DST%\_internal_NUEVO" rmdir /s /q "%DST%\_internal_NUEVO"

xcopy /E /I /Y "%SRC%\*" "%DST%\" >nul

> "%DST%\LEEME_UPDATE.txt" (
  echo BM-CODIGO UPDATE - UX recetas, coste por producto, albaranes
  echo Fecha: 2026-08-28
  echo Sustituir 1-BM-CODIGO-EXE completo. NO tocar 2-BM-DATOS.
  echo.
  echo Cambios:
  echo - Recetas: buscador por letras, unidad al seleccionar, sin extras
  echo - Analisis Costes: tabla coste por producto + Excel semana/mes/periodo
  echo - Compras/albaranes: reload datos y buscador sin salto de scroll
)

echo.
echo OK. Carpeta actualizada: %DST%
echo Copie esta carpeta al servidor ^(C:\Apps\BM-V2^) sustituyendo la anterior.
endlocal
