@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

title VaultMind

:: Add Poppler to PATH if installer saved the path
if exist "poppler_path.txt" (
    set /p POPPLER_BIN=<poppler_path.txt
    set PATH=!PATH!;!POPPLER_BIN!
)

:: Add Tesseract to PATH if installed in default location
if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    set PATH=!PATH!;C:\Program Files\Tesseract-OCR
)

echo.
echo  VaultMind - Private AI for Legal Documents
echo  -------------------------------------------

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Run install.bat first.
    pause
    exit /b 1
)

:: Install missing packages silently
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo  Installing dependencies...
    python -m pip install -r requirements.txt -q
)
python -c "import sentence_transformers" >nul 2>&1
if errorlevel 1 (
    echo  Installing semantic search packages...
    python -m pip install -r requirements.txt -q
)

:: Create workspace folders
if not exist "workspace\input"  mkdir workspace\input  >nul 2>&1
if not exist "workspace\output" mkdir workspace\output >nul 2>&1
if not exist "static"           mkdir static           >nul 2>&1

echo.
echo  Starting at: http://localhost:8000
echo  Open that URL in your browser.
echo  Press Ctrl+C to stop.
echo.

python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload

echo.
echo  VaultMind stopped.
pause
