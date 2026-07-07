@echo off
cd /d "%~dp0"
echo Breakfast Management - %CD%
py -m streamlit run app/main.py
