@echo off
cd /d "%~dp0"
call engine_env\Scripts\activate.bat
python engine.py
pause