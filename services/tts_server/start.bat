@echo off
REM C.Y.R.U.S TTS Server — port 8020
REM Engines: Kokoro (default) / Piper (optional) / XTTS v2 (needs coqui-tts)
cd /d "%~dp0..\.."

REM Optional: override voice/speed
REM set TTS_VOICE=ef_dora
REM set TTS_SPEED=0.92
REM set TTS_LANG_CODE=e
REM set PIPER_MODEL=models/tts/piper/es_MX-ald-medium.onnx
REM set TTS_PORT=8020

echo [C.Y.R.U.S] Starting TTS Server on port 8020...
python -m uvicorn services.tts_server.main:app --host 0.0.0.0 --port 8020
pause
