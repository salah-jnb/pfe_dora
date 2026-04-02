@echo off
color 0B

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT_DIR=%%~fI"
cd /d "%ROOT_DIR%"

echo ===================================================
echo  Project Environment Setup (Python 3.11)
echo ===================================================
echo.

if not exist ".venv311\Scripts\python.exe" (
    echo [1/5] Creating virtual environment (.venv311)...
    py -3.11 -m venv .venv311
) else (
    echo [1/5] Virtual environment already exists.
)

echo [2/5] Upgrading pip tooling...
.\.venv311\Scripts\python.exe -m pip install --upgrade pip setuptools wheel

echo [3/5] Installing project dependencies...
.\.venv311\Scripts\python.exe -m pip install -r requirements.txt --prefer-binary

echo [4/5] Checking for FFmpeg (system requirement)...
where ffmpeg >nul 2>nul
if %errorlevel% equ 0 (
    echo        FFmpeg already installed.
) else (
    echo        FFmpeg not found! Installing via winget...
    winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
)

echo.
echo ===================================================
echo  Setup complete.
echo ===================================================
echo To run the API:
echo .venv311\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
echo.
pause