@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ==============================================
echo    Dank Engine Studio - Installer
echo ==============================================
echo.

REM 1. Check Python is installed
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found.
    echo.
    echo 1. Go to https://www.python.org/downloads/
    echo 2. Download Python 3.10, 3.11 or 3.12.
    echo 3. Run the installer and TICK "Add Python to PATH".
    echo 4. Run this installer again.
    echo.
    pause
    exit /b 1
)

echo Python detected. Building environment...
echo.

REM 2. Check FFmpeg is installed (needed to create the videos)
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [WARNING] FFmpeg was not found.
    echo.
    echo The video engine needs FFmpeg. To install it:
    echo 1. Go to https://www.gyan.dev/ffmpeg/builds/
    echo 2. Download the "release essentials" zip.
    echo 3. Unzip it anywhere (for example C:\ffmpeg).
    echo 4. Add the `bin` folder (C:\ffmpeg\bin) to PATH.
    echo.
    echo Setup will continue now, but videos will not render
    echo until FFmpeg is installed and this window is reopened.
    echo.
    echo Press any key to continue setup...
    pause >nul
)

REM 3. Create a virtual environment (keeps everything in one folder)
if not exist "engine_env\Scripts\python.exe" (
    python -m venv engine_env
    if errorlevel 1 (
        echo [ERROR] Could not create the virtual environment.
        pause
        exit /b 1
    )
)

call engine_env\Scripts\activate.bat
python -m pip install --upgrade pip >nul

REM 4. Install the dependencies
echo.
echo Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    echo Check your internet connection and run this installer again.
    pause
    exit /b 1
)

echo.
echo ==============================================
echo    Done! Now double-click engine.bat to start.
echo ==============================================
echo.
pause
endlocal