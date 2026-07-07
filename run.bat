@echo off
cd /d "%~dp0"
echo Breakfast Management - %CD%
echo.

REM Cierra cualquier instancia anterior en el puerto 8501
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8501" ^| findstr "LISTENING"') do (
    echo Cerrando proceso anterior PID %%a...
    taskkill /F /PID %%a >nul 2>&1
)

echo Iniciando Streamlit con recarga automatica al guardar...
py -m streamlit run app/main.py
