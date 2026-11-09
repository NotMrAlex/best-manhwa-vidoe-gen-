@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ==============================================
echo    TTS Pipeline - Installer
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

for /f "tokens=2 delims=." %%a in ('python -c "import sys;print(sys.version_info[1])"') do set PY_MINOR=%%a
echo Python detected. Building environment...
echo.

REM 2. Create a virtual environment (keeps everything in one folder)
if not exist "tts_env\Scripts\python.exe" (
    python -m venv tts_env
    if errorlevel 1 (
        echo [ERROR] Could not create the virtual environment.
        pause
        exit /b 1
    )
)

call tts_env\Scripts\activate.bat
python -m pip install --upgrade pip >nul

REM 3. Pick the right PyTorch for this computer
set TORCH_INDEX=https://download.pytorch.org/whl/cpu
nvidia-smi >nul 2>nul
if not errorlevel 1 (
    echo NVIDIA GPU detected - installing CUDA-accelerated PyTorch.
    echo This download is large, please wait...
    python -m pip install torch
) else (
    echo No NVIDIA GPU detected - installing CPU PyTorch.
    echo.
    echo NOTE: AMD and Intel GPUs are not accelerated on Windows, so the
    echo CPU version is used. The app still works - it is just slower.
    echo.
    python -m pip install torch --index-url %TORCH_INDEX%
)
if errorlevel 1 (
    echo [ERROR] PyTorch installation failed.
    pause
    exit /b 1
)

REM 4. Install the rest of the dependencies
echo.
echo Installing remaining dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    echo Check your internet connection and run this installer again.
    pause
    exit /b 1
)

echo.
echo ==============================================
echo    Done! Now double-click run.bat to start.
echo ==============================================
echo.
pause
endlocal