@echo off
setlocal EnableExtensions
cd /d "%~dp0\..\.."
if not defined BM_DEPLOY_CONFIG if exist "deploy\config.env" set "BM_DEPLOY_CONFIG=%CD%\deploy\config.env"
python -m app.core.deploy.cli diagnose
exit /b %ERRORLEVEL%
