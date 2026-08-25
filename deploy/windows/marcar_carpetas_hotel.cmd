@echo off
REM Crea marcadores BM-CODIGO.txt / BM-DATOS.txt en las rutas por defecto del hotel.
REM Uso:
REM   deploy\windows\marcar_carpetas_hotel.cmd
REM   deploy\windows\marcar_carpetas_hotel.cmd C:\Apps\BM-V2 "%LOCALAPPDATA%\BM-V2-local"
setlocal EnableExtensions

if "%~1"=="" (
  set "CODIGO=C:\Apps\BM-V2"
) else (
  set "CODIGO=%~1"
)

if "%~2"=="" (
  set "DATOS=%LOCALAPPDATA%\BM-V2-local"
) else (
  set "DATOS=%~2"
)

echo BM-CODIGO = %CODIGO%
echo BM-DATOS  = %DATOS%

if not exist "%CODIGO%" mkdir "%CODIGO%"
if not exist "%DATOS%" mkdir "%DATOS%"
if not exist "%DATOS%\data" mkdir "%DATOS%\data"
if not exist "%DATOS%\data\documentos" mkdir "%DATOS%\data\documentos"
if not exist "%DATOS%\backups" mkdir "%DATOS%\backups"
if not exist "%DATOS%\logs" mkdir "%DATOS%\logs"
if not exist "%DATOS%\exports" mkdir "%DATOS%\exports"

> "%CODIGO%\BM-CODIGO.txt" (
  echo Carpeta de aplicacion ^(BM-CODIGO^).
  echo.
  echo Sustituir COMPLETA al actualizar la version ^(exe + _internal^).
  echo No borrar ni mezclar con BM-DATOS.
  echo El acceso directo debe apuntar a BM-Launcher.exe dentro de esta carpeta.
  echo.
  echo Ruta tipica: C:\Apps\BM-V2\
  echo Datos productivos: ver BM-DATOS.txt en %%LOCALAPPDATA%%\BM-V2-local\
)

> "%DATOS%\BM-DATOS.txt" (
  echo Carpeta de datos del hotel ^(BM-DATOS^).
  echo.
  echo Sustituir COMPLETA al llevar/traer la base ^(casa ^<-> hotel^).
  echo Incluye: data\datos_hotel.json, data\documentos\, backups\, exports\, logs\.
  echo No mezclar con una actualizacion de codigo.
  echo.
  echo Ruta tipica ^(un PC / exe^): %%LOCALAPPDATA%%\BM-V2-local\
  echo Variable: BM_INSTANCE_ROOT
)

echo.
echo Marcadores escritos:
echo   %CODIGO%\BM-CODIGO.txt
echo   %DATOS%\BM-DATOS.txt
echo Ver docs\hotel_dos_carpetas.md
endlocal
