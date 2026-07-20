@echo off
echo Starting Ferret-UI server...
cd /d "%~dp0"
call venv\Scripts\activate.bat
python ferret_server.py
pause
