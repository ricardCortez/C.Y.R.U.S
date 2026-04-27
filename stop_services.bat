@echo off
REM ============================================================
REM  JARVIS — Detener todos los procesos
REM  Libera puertos: 8765 (backend), 8020/8000/8001/8002 (servicios)
REM ============================================================

cd /d "%~dp0"

echo.
echo [*] Deteniendo JARVIS...
echo.

call :kill_port 3007 "Frontend     "
call :kill_port 8765 "JARVIS Backend"
call :kill_port 8020 "TTS Server   "
call :kill_port 8000 "ASR Server   "
call :kill_port 8001 "Vision Server"
call :kill_port 8002 "Embedder     "

echo.
echo [*] Todos los procesos detenidos.
echo.
goto :eof

:kill_port
setlocal
set PORT=%~1
set NAME=%~2
set FOUND=0
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":%PORT% "') do (
    if not "%%p"=="0" (
        taskkill /pid %%p /f >nul 2>&1
        if not errorlevel 1 (
            echo  [stop] %NAME%  puerto %PORT%  PID %%p
            set FOUND=1
        )
    )
)
if %FOUND%==0 echo  [--]   %NAME%  puerto %PORT%  ya libre
endlocal
goto :eof
