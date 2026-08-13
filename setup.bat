@echo off
setlocal EnableDelayedExpansion

echo.
echo    ___         __       ________
echo   / _ ^| __ __/ /____  / ___/ (_)____
echo  / __ ^|/ // / __/ _ \/ /__/ / / __/
echo /_/ ^|_^|\_,_/\__/\___/\___/_/_/\__/
echo.
echo  AutoClip Setup Script for Windows
echo  ===================================
echo.

:: ── Check Python ─────────────────────────────────────────────────────────────
echo [1/4] Checking Python version...

python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [ERROR] Python not found!
    echo  Please install Python 3.10 or newer from: https://python.org/downloads
    echo  Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
    set PYMAJOR=%%a
    set PYMINOR=%%b
)

if !PYMAJOR! LSS 3 (
    echo  [ERROR] Python 3.10+ required, found !PYVER!
    pause
    exit /b 1
)
if !PYMAJOR! EQU 3 if !PYMINOR! LSS 10 (
    echo  [ERROR] Python 3.10+ required, found !PYVER!
    pause
    exit /b 1
)

echo  [OK] Python !PYVER! found.
echo.

:: ── Create virtual environment ────────────────────────────────────────────────
echo [2/4] Creating virtual environment in .venv\ ...

if exist .venv\ (
    echo  [INFO] .venv already exists, skipping creation.
) else (
    python -m venv .venv
    if %ERRORLEVEL% NEQ 0 (
        echo  [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  [OK] Virtual environment created.
)
echo.

:: ── Install dependencies ──────────────────────────────────────────────────────
echo [3/4] Installing dependencies (this may take a few minutes)...
echo  Installing PyTorch CPU + Whisper + all dependencies...
echo.

.venv\Scripts\python.exe -m pip install --upgrade pip --quiet

.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [ERROR] Dependency installation failed.
    echo  Try running manually: .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo  [OK] All dependencies installed.
echo.

:: ── Create launcher ───────────────────────────────────────────────────────────
echo [4/4] Creating autoclip launcher...

(
    echo @echo off
    echo set PYTHONUTF8=1
    echo set PYTHONPATH=%~dp0
    echo "%~dp0.venv\Scripts\python.exe" -m autoclip %%*
) > autoclip.bat

echo  [OK] Launcher created: autoclip.bat
echo.

:: ── Done ─────────────────────────────────────────────────────────────────────
echo ============================================================
echo  Setup complete!
echo.
echo  To get started, run:
echo.
echo    autoclip
echo.
echo  Requirements:
echo    - FFmpeg  : https://ffmpeg.org/download.html
echo    - Ollama  : https://ollama.ai  (optional, for AI analysis)
echo      then run: ollama pull llama3
echo.
echo ============================================================
echo.
pause
