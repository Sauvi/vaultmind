@echo off
echo.
echo  VaultMind - Private AI
echo  ----------------------
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found.
    echo  Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

:: Only install if fastapi is missing
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo  Installing dependencies for the first time...
    pip install -r requirements.txt -q
    echo  Done.
) else (
    echo  Dependencies already installed.
)

:: Create workspace folders
if not exist "workspace\input" mkdir workspace\input
if not exist "workspace\output" mkdir workspace\output
if not exist "static" mkdir static

echo.
echo  VaultMind running at --^> http://localhost:8000
echo  Open that URL in your browser.
echo  Press Ctrl+C to stop.
echo.

:: Start server
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
