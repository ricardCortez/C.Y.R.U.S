@echo off
REM JARVIS ASR Server — port 8000
REM Uses: faster-whisper (already installed)
cd /d "%~dp0..\.."

REM set ASR_MODEL=tiny
REM set ASR_DEVICE=cuda
REM set ASR_LANGUAGE=es
REM set ASR_PORT=8000

echo [JARVIS] Starting ASR Server on port 8000...
python -m uvicorn services.asr_server.main:app --host 0.0.0.0 --port 8000
pause
