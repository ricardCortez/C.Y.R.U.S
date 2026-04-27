@echo off
REM ─────────────────────────────────────────────────────────────────────────
REM JARVIS — Windows Setup Script
REM Run from the project root: deployment\setup.bat
REM ─────────────────────────────────────────────────────────────────────────

echo.
echo  ██████╗██╗   ██╗██████╗ ██╗   ██╗███████╗
echo ██╔════╝╚██╗ ██╔╝██╔══██╗██║   ██║██╔════╝
echo ██║      ╚████╔╝ ██████╔╝██║   ██║███████╗
echo ██║       ╚██╔╝  ██╔══██╗██║   ██║╚════██║
echo ╚██████╗   ██║   ██║  ██║╚██████╔╝███████║
echo  ╚═════╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
echo.
echo  Cognitive sYstem for Real-time Utility and Services
echo  Phase 1 — Setup
echo.

REM Check Python version
python --version 2>NUL
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ from python.org
    exit /b 1
)

REM Move to project root
cd /d "%~dp0\.."
echo [INFO] Working directory: %CD%

REM Create virtual environment
if not exist venv (
    echo [INFO] Creating virtual environment...
    python -m venv venv
) else (
    echo [INFO] Virtual environment already exists
)

REM Activate
call venv\Scripts\activate.bat

REM Upgrade pip
python -m pip install --upgrade pip --quiet

REM Install backend dependencies
echo [INFO] Installing Python dependencies...
pip install -r requirements.txt

REM Copy .env template if .env doesn't exist
if not exist .env (
    copy config\.env.example .env
    echo [INFO] Created .env from template — edit it and add your CLAUDE_API_KEY
)

REM Create log directory
if not exist logs mkdir logs

REM Install frontend dependencies
echo [INFO] Installing frontend dependencies...
cd frontend
where npm >NUL 2>&1
if errorlevel 1 (
    echo [WARNING] npm not found. Install Node.js 18+ to run the UI.
) else (
    npm install
)
cd ..

echo.
echo ─────────────────────────────────────────────────────
echo  Setup complete!
echo.
echo  To start JARVIS:
echo.
echo    1. Activate venv:    venv\Scripts\activate
echo    2. Start Ollama:     ollama serve       (separate terminal)
echo    3. Start backend:    python -m backend.core.cyrus_engine
echo    4. Start frontend:   cd frontend ^& npm run dev
echo.
echo  Then say "Hola JARVIS" into your microphone.
echo ─────────────────────────────────────────────────────
