@echo off
REM Crea "BM Hotel.lnk" en el escritorio apuntando a "Abrir BM Hotel.cmd".
setlocal EnableExtensions
cd /d "%~dp0\..\.."

set "ROOT=%CD%"
set "LAUNCHER=%ROOT%\Abrir BM Hotel.cmd"
set "DESKTOP=%USERPROFILE%\Desktop"
set "LINK=%DESKTOP%\BM Hotel.lnk"
set "EXE=%ROOT%\dist\BM-Launcher\BM-Launcher.exe"

if not exist "%LAUNCHER%" (
    echo ERROR: no se encuentra "%LAUNCHER%"
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%LINK%');" ^
  "$s.TargetPath = '%LAUNCHER%';" ^
  "$s.WorkingDirectory = '%ROOT%';" ^
  "$s.WindowStyle = 7;" ^
  "if (Test-Path '%EXE%') { $s.IconLocation = '%EXE%,0' };" ^
  "$s.Description = 'BM-V.2 — Launcher (Administracion, Inventario, Restaurante)';" ^
  "$s.Save()"

if errorlevel 1 (
    echo ERROR al crear el acceso directo.
    exit /b 1
)

echo Acceso directo creado:
echo   %LINK%
echo.
echo Doble clic en "BM Hotel" del escritorio para abrir la aplicacion.
exit /b 0
