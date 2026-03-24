@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ============================================================
:: VaultMind Installer v1.2
:: One-click setup for Windows
:: Downloads and installs all dependencies automatically
:: ============================================================

title VaultMind Installer

echo.
echo  ================================================
echo   VaultMind - Private AI for Legal Documents
echo   One-Click Installer v1.2
echo  ================================================
echo.
echo  This will install everything VaultMind needs.
echo  Internet required for first-time setup only.
echo  Your documents will NEVER leave this machine.
echo.
echo  Press any key to start installation...
pause >nul

:: ── STEP 0: Check Windows version ───────────────────────────
echo.
echo  [1/7] Checking system...

ver | findstr /i "10\. 11\." >nul
if errorlevel 1 (
    echo  WARNING: Windows 10 or 11 recommended.
    echo  Older versions may have issues.
)

:: Check if running as administrator (recommended)
net session >nul 2>&1
if errorlevel 1 (
    echo  NOTE: Running without admin rights.
    echo  Some installs may require admin. If anything fails,
    echo  right-click install.bat and choose "Run as administrator"
)
echo  System check done.

:: ── STEP 1: Python ──────────────────────────────────────────
echo.
echo  [2/7] Checking Python...

python --version >nul 2>&1
if errorlevel 1 (
    echo  Python not found. Downloading Python 3.11...
    echo.

    :: Download Python installer
    set PYTHON_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
    set PYTHON_INSTALLER=%TEMP%\python_installer.exe

    echo  Downloading from python.org...
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('%PYTHON_URL%', '%PYTHON_INSTALLER%')}"

    if not exist "%PYTHON_INSTALLER%" (
        echo.
        echo  ERROR: Could not download Python automatically.
        echo  Please install manually from: https://www.python.org/downloads/
        echo  Then run this installer again.
        pause
        exit /b 1
    )

    echo  Installing Python 3.11 (this takes ~1 minute)...
    :: /quiet = silent, InstallAllUsers=0 = current user only, PrependPath=1 = add to PATH
    "%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0

    :: Refresh PATH in this session
    call :refresh_path

    :: Verify
    python --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo  ERROR: Python installation failed.
        echo  Please install manually: https://www.python.org/downloads/
        echo  IMPORTANT: Tick "Add Python to PATH" during install.
        pause
        exit /b 1
    )
    echo  Python installed successfully.
) else (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
    echo  Python !PYVER! found. Good.
)

:: ── STEP 2: pip upgrade ─────────────────────────────────────
echo.
echo  [3/7] Updating pip...
python -m pip install --upgrade pip -q
echo  pip updated.

:: ── STEP 3: Python dependencies ─────────────────────────────
echo.
echo  [4/7] Installing Python packages...
echo  (This may take 3-5 minutes on first install)
echo.

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  ERROR: Some packages failed to install.
    echo  Try running: pip install -r requirements.txt
    echo  Then run this installer again.
    pause
    exit /b 1
)
echo.
echo  Python packages installed.

:: ── STEP 4: Ollama ──────────────────────────────────────────
echo.
echo  [5/7] Checking Ollama (local AI engine)...

ollama --version >nul 2>&1
if errorlevel 1 (
    echo  Ollama not found. Downloading...
    echo.

    set OLLAMA_URL=https://ollama.com/download/OllamaSetup.exe
    set OLLAMA_INSTALLER=%TEMP%\OllamaSetup.exe

    echo  Downloading Ollama from ollama.com...
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('%OLLAMA_URL%', '%OLLAMA_INSTALLER%')}"

    if not exist "%OLLAMA_INSTALLER%" (
        echo.
        echo  Could not download Ollama automatically.
        echo  Please download manually from: https://ollama.com/download
        echo  Install it, then run this installer again.
        pause
        exit /b 1
    )

    echo  Installing Ollama...
    "%OLLAMA_INSTALLER%" /S

    :: Give it a moment to finish
    timeout /t 3 /nobreak >nul
    call :refresh_path

    ollama --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo  Ollama installed but needs a restart to be recognised.
        echo  After restarting, run this installer again.
        pause
        exit /b 1
    )
    echo  Ollama installed successfully.
) else (
    echo  Ollama found. Good.
)

:: Pull the AI model
echo.
echo  Downloading AI model (phi3.5 - 2.2GB, one-time only)...
echo  This is the brain of VaultMind. Please wait...
echo.
ollama pull phi3.5
if errorlevel 1 (
    echo.
    echo  WARNING: Could not pull phi3.5 model.
    echo  Make sure Ollama is running and try: ollama pull phi3.5
) else (
    echo  AI model ready.
)

:: ── STEP 5: Tesseract OCR ────────────────────────────────────
echo.
echo  [6/7] Setting up OCR (for scanned PDFs)...

tesseract --version >nul 2>&1
if errorlevel 1 (
    echo  Tesseract not found. Downloading...
    echo  (Adds Hindi + English OCR support for scanned PDFs)
    echo.

    set TESS_URL=https://github.com/UB-Mannheim/tesseract/releases/download/v5.3.3.20231005/tesseract-ocr-w64-setup-5.3.3.20231005.exe
    set TESS_INSTALLER=%TEMP%\tesseract_installer.exe

    echo  Downloading Tesseract...
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('%TESS_URL%', '%TESS_INSTALLER%')}"

    if not exist "%TESS_INSTALLER%" (
        echo  Could not download Tesseract automatically.
        echo  OCR for scanned PDFs will not work.
        echo  Install manually: https://github.com/UB-Mannheim/tesseract/wiki
        goto :skip_tesseract
    )

    echo  Installing Tesseract with Hindi language support...
    :: /S = silent, install all languages
    "%TESS_INSTALLER%" /S

    timeout /t 3 /nobreak >nul
    call :refresh_path

    tesseract --version >nul 2>&1
    if errorlevel 1 (
        echo  Tesseract installed. A restart may be needed to use OCR.
    ) else (
        echo  Tesseract installed - OCR ready for Hindi + English.
    )
) else (
    echo  Tesseract found. OCR ready.
)
:skip_tesseract

:: ── STEP 6: Poppler (for pdf2image) ──────────────────────────
echo.
echo  Checking Poppler (PDF image conversion for OCR)...

pdftoppm -v >nul 2>&1
if errorlevel 1 (
    echo  Poppler not found. Installing...

    :: Download Poppler for Windows
    set POPPLER_URL=https://github.com/oschwartz10612/poppler-windows/releases/download/v24.02.0-0/Release-24.02.0-0.zip
    set POPPLER_ZIP=%TEMP%\poppler.zip
    set POPPLER_DIR=C:\vaultmind\tools\poppler

    echo  Downloading Poppler...
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('%POPPLER_URL%', '%POPPLER_ZIP%')}"

    if not exist "%POPPLER_ZIP%" (
        echo  Could not download Poppler automatically.
        echo  OCR on scanned PDFs may be limited.
        goto :skip_poppler
    )

    echo  Extracting Poppler...
    powershell -Command "Expand-Archive -Path '%POPPLER_ZIP%' -DestinationPath 'C:\vaultmind\tools\' -Force"

    :: Find the bin folder (zip structure varies)
    for /d %%d in ("C:\vaultmind\tools\poppler*") do set POPPLER_BIN=%%d\Library\bin
    if not exist "!POPPLER_BIN!" (
        for /d %%d in ("C:\vaultmind\tools\poppler*") do set POPPLER_BIN=%%d\bin
    )

    :: Add to user PATH permanently
    if exist "!POPPLER_BIN!" (
        powershell -Command "[System.Environment]::SetEnvironmentVariable('PATH', [System.Environment]::GetEnvironmentVariable('PATH','User') + ';!POPPLER_BIN!', 'User')"
        set PATH=!PATH!;!POPPLER_BIN!
        echo  Poppler installed at !POPPLER_BIN!

        :: Also write path to a config file for file_reader.py
        echo !POPPLER_BIN!> C:\vaultmind\poppler_path.txt
        echo  Poppler path saved for VaultMind.
    ) else (
        echo  Could not locate Poppler bin folder after extraction.
    )
) else (
    echo  Poppler found. Good.
)
:skip_poppler

:: ── STEP 7: Create workspace folders ────────────────────────
echo.
echo  [7/7] Setting up workspace...
if not exist "workspace\input"           mkdir workspace\input
if not exist "workspace\output"          mkdir workspace\output
if not exist "workspace\research_library" mkdir workspace\research_library
if not exist "static"                    mkdir static
echo  Workspace ready.

:: ── Create desktop shortcut ─────────────────────────────────
echo.
echo  Creating desktop shortcut...
set SHORTCUT=%USERPROFILE%\Desktop\VaultMind.lnk
set VAULTMIND_DIR=%~dp0
powershell -Command "& { $s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT%'); $s.TargetPath='%VAULTMIND_DIR%run.bat'; $s.WorkingDirectory='%VAULTMIND_DIR%'; $s.WindowStyle=1; $s.Description='VaultMind - Private AI for Legal Documents'; $s.Save() }"
if exist "%SHORTCUT%" (
    echo  Desktop shortcut created - VaultMind.lnk
) else (
    echo  Could not create desktop shortcut (non-critical).
)

:: ── Done ─────────────────────────────────────────────────────
echo.
echo  ================================================
echo   Installation Complete!
echo  ================================================
echo.
echo  To start VaultMind:
echo    - Double-click VaultMind on your Desktop, OR
echo    - Double-click run.bat in this folder
echo.
echo  Then open your browser at: http://localhost:8000
echo.
echo  What was installed:
python --version 2>&1 | findstr Python
ollama --version 2>&1 | findstr ollama
tesseract --version 2>&1 | findstr tesseract | head /1
echo  - All Python packages (fastapi, uvicorn, etc.)
echo  - Semantic RAG model (all-MiniLM-L6-v2)
echo  - AI model: phi3.5
echo.
echo  Your documents will NEVER leave this machine.
echo  100%% local. 100%% private.
echo.
echo  Press any key to launch VaultMind now...
pause >nul

:: Launch VaultMind
start "" "%~dp0run.bat"
exit /b 0

:: ── Helper: Refresh PATH from registry ──────────────────────
:refresh_path
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set "UPATH=%%b"
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul') do set "SPATH=%%b"
set PATH=%SPATH%;%UPATH%
exit /b 0
