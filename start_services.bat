@echo off
REM ============================================================
REM  C.Y.R.U.S — Arranque limpio integral
REM
REM  Mata todos los procesos activos y levanta desde cero:
REM    TTS Server (8020) + Backend CYRUS (8765) + Frontend (3007)
REM    + ASR/Vision/Embedder segun flags
REM
REM  Uso:
REM    start_services.bat              -> TTS + backend + frontend
REM    start_services.bat all          -> todo (incluyendo ASR/Vision/Embedder)
REM    start_services.bat tts asr      -> TTS + ASR + backend + frontend
REM    start_services.bat noui         -> TTS + backend  (sin frontend)
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ── Valores por defecto ─────────────────────────────────────
set RUN_TTS=1
set RUN_ASR=0
set RUN_VISION=0
set RUN_EMBEDDER=0
set RUN_FRONTEND=1

REM ── Parsear argumentos ──────────────────────────────────────
if not "%~1"=="" (
    set RUN_TTS=0
    set RUN_FRONTEND=1
    :parse_args
    if /i "%~1"=="all"        set RUN_TTS=1 & set RUN_ASR=1 & set RUN_VISION=1 & set RUN_EMBEDDER=1
    if /i "%~1"=="tts"        set RUN_TTS=1
    if /i "%~1"=="asr"        set RUN_ASR=1
    if /i "%~1"=="vision"     set RUN_VISION=1
    if /i "%~1"=="embedder"   set RUN_EMBEDDER=1
    if /i "%~1"=="noui"       set RUN_FRONTEND=0
    shift
    if not "%~1"=="" goto parse_args
)

echo.
echo  ============================================
echo   C.Y.R.U.S  --  ARRANQUE LIMPIO INTEGRAL
echo  ============================================
echo.

REM ── 1. Matar procesos existentes ────────────────────────────
echo [1/3] Apagando procesos anteriores...
echo.

call :kill_port 3007 "Frontend     "
call :kill_port 8765 "CYRUS Backend"
call :kill_port 8020 "TTS Server   "
call :kill_port 8000 "ASR Server   "
call :kill_port 8001 "Vision Server"
call :kill_port 8002 "Embedder     "

echo.
echo  Puertos liberados. Esperando 2s...
timeout /t 2 /nobreak >nul

REM ── 2. Verificar entorno ────────────────────────────────────
echo.
echo [2/3] Verificando entorno...

if not exist venv\Scripts\activate.bat (
    echo.
    echo  [ERROR] Entorno virtual no encontrado.
    echo          Crea uno con: py -3.11 -m venv venv
    pause
    exit /b 1
)

if %RUN_FRONTEND%==1 (
    if not exist frontend\package.json (
        echo  [WARN] frontend\package.json no encontrado - saltando frontend
        set RUN_FRONTEND=0
    )
)

echo  OK
echo.

REM ── 3. Levantar servicios ────────────────────────────────────
echo [3/3] Levantando servicios...
echo.

if %RUN_TTS%==1 (
    echo  [+] TTS Server     puerto 8020
    start "CYRUS TTS :8020" cmd /k "cd /d %~dp0 && venv\Scripts\activate.bat && set COQUI_TOS_AGREED=1 && python -m uvicorn services.tts_server.main:app --host 0.0.0.0 --port 8020"
    timeout /t 2 /nobreak >nul
)

if %RUN_ASR%==1 (
    echo  [+] ASR Server     puerto 8000
    start "CYRUS ASR :8000" cmd /k "cd /d %~dp0 && venv\Scripts\activate.bat && python -m uvicorn services.asr_server.main:app --host 0.0.0.0 --port 8000"
    timeout /t 1 /nobreak >nul
)

if %RUN_VISION%==1 (
    echo  [+] Vision Server  puerto 8001
    start "CYRUS VISION :8001" cmd /k "cd /d %~dp0 && venv\Scripts\activate.bat && python -m uvicorn services.vision_server.main:app --host 0.0.0.0 --port 8001"
    timeout /t 1 /nobreak >nul
)

if %RUN_EMBEDDER%==1 (
    echo  [+] Embedder       puerto 8002
    start "CYRUS EMBEDDER :8002" cmd /k "cd /d %~dp0 && venv\Scripts\activate.bat && python -m uvicorn services.embedder_server.main:app --host 0.0.0.0 --port 8002"
    timeout /t 1 /nobreak >nul
)

REM Dar tiempo a los servicios antes de arrancar el backend
echo.
echo  Esperando 4s para que los servicios carguen modelos...
timeout /t 4 /nobreak >nul

echo  [+] CYRUS Backend  puerto 8765
start "CYRUS BACKEND :8765" cmd /k "cd /d %~dp0 && venv\Scripts\activate.bat && set COQUI_TOS_AGREED=1 && python -m backend.core.cyrus_engine"
timeout /t 2 /nobreak >nul

if %RUN_FRONTEND%==1 (
    echo  [+] Frontend React puerto 3007
    start "CYRUS FRONTEND :3007" cmd /k "cd /d %~dp0\frontend && npm run dev"
)

REM ── Health check ─────────────────────────────────────────────
echo.
echo  Esperando que los servicios arranquen (8s)...
timeout /t 8 /nobreak >nul

echo.
echo  Estado:
echo.
if %RUN_TTS%==1      call :check_health 8020 "TTS Server   "
if %RUN_ASR%==1      call :check_health 8000 "ASR Server   "
if %RUN_VISION%==1   call :check_health 8001 "Vision Server"
if %RUN_EMBEDDER%==1 call :check_health 8002 "Embedder     "

REM Backend usa WebSocket — verificar puerto TCP en vez de HTTP
call :check_port 8765 "CYRUS Backend"

if %RUN_FRONTEND%==1 call :check_port 3007 "Frontend     "

echo.
echo  ============================================
echo   Panel: http://localhost:3007
echo  ============================================
echo.
goto :eof

REM ── Subrutinas ───────────────────────────────────────────────

:kill_port
setlocal
set PORT=%~1
set NAME=%~2
set FOUND=0
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":%PORT% "') do (
    if not "%%p"=="0" (
        taskkill /pid %%p /f >nul 2>&1
        if not errorlevel 1 (
            echo  [kill] %NAME%  puerto %PORT%  PID %%p
            set FOUND=1
        )
    )
)
if %FOUND%==0 echo  [--]   %NAME%  puerto %PORT%  libre
endlocal
goto :eof

:check_health
setlocal
set PORT=%~1
set NAME=%~2
curl -s --max-time 3 http://localhost:%PORT%/health >nul 2>&1
if %errorlevel%==0 (
    echo   [OK]   %NAME%  http://localhost:%PORT%/health
) else (
    echo   [??]   %NAME%  http://localhost:%PORT%/health  ^(cargando aun?^)
)
endlocal
goto :eof

:check_port
setlocal
set PORT=%~1
set NAME=%~2
netstat -ano 2>nul | findstr ":%PORT% " >nul 2>&1
if %errorlevel%==0 (
    echo   [OK]   %NAME%  puerto %PORT%  escuchando
) else (
    echo   [??]   %NAME%  puerto %PORT%  no detectado aun
)
endlocal
goto :eof
