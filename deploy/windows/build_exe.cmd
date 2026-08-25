@echo off
REM Genera dist\BM-Launcher\BM-Launcher.exe (onedir). No incluye datos productivos.
setlocal
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: cree .venv e instale requirements + pyinstaller.
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install -q "pyinstaller>=6.0"
python -m PyInstaller packaging\bm_launcher.spec --noconfirm --clean
if errorlevel 1 exit /b 1
echo.
echo Artefacto: %CD%\dist\BM-Launcher\BM-Launcher.exe
echo Carpeta CODIGO tipica: C:\Apps\BM-V2  (copiar dist\BM-Launcher ahi)
echo Carpeta DATOS: %%LOCALAPPDATA%%\BM-V2-local  (runtime hook; no tocar al actualizar)
echo Ver docs\hotel_dos_carpetas.md
echo Marcadores: deploy\windows\marcar_carpetas_hotel.cmd
endlocal
