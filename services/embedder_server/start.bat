@echo off
REM C.Y.R.U.S Embedder Server — port 8002
REM Uses: sentence-transformers (already installed)
cd /d "%~dp0..\.."

REM set EMBEDDER_MODEL=all-MiniLM-L6-v2
REM set EMBEDDER_DEVICE=cpu
REM set EMBEDDER_PORT=8002

echo [C.Y.R.U.S] Starting Embedder Server on port 8002...
python -m uvicorn services.embedder_server.main:app --host 0.0.0.0 --port 8002
pause
