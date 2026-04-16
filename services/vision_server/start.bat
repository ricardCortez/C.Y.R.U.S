@echo off
REM C.Y.R.U.S Vision Server — port 8001
REM Requires: pip install ultralytics deepface opencv-python-headless
cd /d "%~dp0..\.."

REM set YOLO_MODEL=yolov8n.pt
REM set YOLO_CONFIDENCE=0.45
REM set YOLO_DEVICE=cuda
REM set FACE_DB_PATH=data/faces
REM set VISION_PORT=8001

echo [C.Y.R.U.S] Starting Vision Server on port 8001...
python -m uvicorn services.vision_server.main:app --host 0.0.0.0 --port 8001
pause
