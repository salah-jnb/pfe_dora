@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT_DIR=%%~fI"
cd /d "%ROOT_DIR%"

echo ==========================================
echo  Dora Backend Launcher (Python 3.11)
echo ==========================================
echo.

if not exist ".venv311\Scripts\python.exe" (
  echo [1/4] Creating .venv311 using Python 3.11...
  py -3.11 -m venv .venv311
)

echo [2/4] Upgrading pip tooling...
.\.venv311\Scripts\python.exe -m pip install --upgrade pip wheel "setuptools<82"

echo [3/4] Installing project requirements...
.\.venv311\Scripts\python.exe -m pip install -r requirements.txt --prefer-binary

echo [4/4] Starting API server on http://127.0.0.1:8000/front
.\.venv311\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

endlocal
