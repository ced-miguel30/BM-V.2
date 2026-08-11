@echo off
setlocal EnableExtensions
cd /d "%~dp0\..\.."
if not defined BM_DEPLOY_CONFIG if exist "deploy\config.env" set "BM_DEPLOY_CONFIG=%CD%\deploy\config.env"
echo [BM] AVISO: un unico proceso escritor. No abra Flet y Streamlit a la vez.
echo [BM] launcher — %CD%
python -m app.core.deploy.cli run-launcher
exit /b %ERRORLEVEL%
