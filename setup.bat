@echo off
color 0B
echo ===================================================
echo  Thesis Full-Stack Environment Setup (GTX 1070)
echo ===================================================
echo.

echo [1/6] Creating virtual environment (.venv_desktop)...
python -m venv .venv_desktop

echo [2/6] Activating environment...
call .venv_desktop\Scripts\activate.bat

echo [3/6] Upgrading pip...
python -m pip install --upgrade pip >nul

echo [4/6] Installing PyTorch (GPU/CUDA 11.8 Version)...
echo        (This is a large download, please wait...)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

echo [5/6] Installing tool dependencies...
echo        (YOLO, BoxMOT, GUIs, Metrics, Plotting...)
pip install -r requirements.txt

echo [6/6] Checking for FFmpeg (System Requirement)...
where ffmpeg >nul 2>nul
if %errorlevel% equ 0 (
    echo        FFmpeg is already installed. Skipping download.
) else (
    echo        FFmpeg not found! Installing via winget...
    winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
)

echo.
echo ===================================================
echo  Setup complete! Starting System Check...
echo ===================================================
python check_gpu.py

echo.
echo All set for the A-Z Pipeline!
echo To run your scripts, always use the virtual environment:
echo .venv_desktop\Scripts\python.exe YOUR_SCRIPT.py
echo.
pause