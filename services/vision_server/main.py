"""
C.Y.R.U.S — Vision Microservice (port 8001).

Standalone FastAPI server that runs YOLO object detection + face recognition
on frames received as base64-encoded JPEG.

Endpoints
---------
GET  /health          → {"status":"ok","yolo":true,"face":true}
POST /analyze         → {"objects":[...], "faces":[...], "source":"remote"}

Start
-----
    python -m services.vision_server.main
    # or:
    uvicorn services.vision_server.main:app --host 0.0.0.0 --port 8001

Dependencies (install in this service's env)
---------------------------------------------
    pip install ultralytics deepface opencv-python-headless

Environment variables
---------------------
    YOLO_MODEL      path or model name  (default: yolov8n.pt)
    YOLO_CONFIDENCE float               (default: 0.45)
    YOLO_DEVICE     cuda | cpu          (default: cuda)
    FACE_DB_PATH    path to face DB dir (default: data/faces)
    VISION_PORT     listen port         (default: 8001)
"""

from __future__ import annotations

import base64
import io
import os
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="C.Y.R.U.S Vision Server", version="1.0.0")

_yolo  = None
_face_db = os.environ.get("FACE_DB_PATH", "data/faces")
_yolo_ok = False
_face_ok = False


def _load_models():
    global _yolo, _yolo_ok, _face_ok

    # ── YOLO ────────────────────────────────────────────────────────────
    try:
        from ultralytics import YOLO
        model_name = os.environ.get("YOLO_MODEL", "yolov8n.pt")
        _yolo = YOLO(model_name)
        _yolo_ok = True
        print(f"[Vision-Server] YOLO ready ({model_name})")
    except Exception as exc:
        print(f"[Vision-Server] YOLO unavailable: {exc}")

    # ── DeepFace (face recognition) ─────────────────────────────────────
    try:
        from deepface import DeepFace  # noqa: F401  — just verify import
        _face_ok = True
        print("[Vision-Server] DeepFace ready")
    except Exception as exc:
        print(f"[Vision-Server] DeepFace unavailable: {exc}")


@app.on_event("startup")
async def on_startup():
    import asyncio
    await asyncio.get_event_loop().run_in_executor(None, _load_models)


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def _decode_frame(frame_b64: str):
    """Decode base64 JPEG → OpenCV BGR ndarray."""
    import numpy as np
    import cv2
    raw = base64.b64decode(frame_b64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _run_yolo(frame) -> list[dict]:
    conf_threshold = float(os.environ.get("YOLO_CONFIDENCE", "0.45"))
    device         = os.environ.get("YOLO_DEVICE", "cuda")
    results = _yolo(frame, device=device, verbose=False)[0]
    objects = []
    for box in results.boxes:
        conf = float(box.conf[0])
        if conf < conf_threshold:
            continue
        cls_id = int(box.cls[0])
        label  = results.names.get(cls_id, str(cls_id))
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        objects.append({
            "label":      label,
            "confidence": round(conf, 3),
            "bbox":       [round(x1), round(y1), round(x2), round(y2)],
        })
    return objects


def _run_faces(frame) -> list[dict]:
    import tempfile, cv2, os as _os
    from deepface import DeepFace
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        cv2.imwrite(tmp_path, frame)
        if not os.path.isdir(_face_db):
            return []
        results = DeepFace.find(
            img_path=tmp_path,
            db_path=_face_db,
            model_name="Facenet512",
            detector_backend="retinaface",
            enforce_detection=False,
            silent=True,
        )
        faces = []
        for df in results:
            if df.empty:
                continue
            row = df.iloc[0]
            faces.append({
                "identity":   str(row.get("identity", "unknown")),
                "confidence": round(float(1.0 - row.get("distance", 1.0)), 3),
            })
        return faces
    except Exception:
        return []
    finally:
        try: _os.unlink(tmp_path)
        except: pass


# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    frame_b64: str              # base64-encoded JPEG


@app.get("/health")
async def health():
    return {"status": "ok", "yolo": _yolo_ok, "face": _face_ok}


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    if not _yolo_ok and not _face_ok:
        raise HTTPException(503, "No vision engines loaded — install ultralytics and deepface")
    try:
        import asyncio, cv2
        loop = asyncio.get_event_loop()
        frame = await loop.run_in_executor(None, _decode_frame, req.frame_b64)
        if frame is None:
            raise HTTPException(400, "Could not decode frame")

        objects: list[dict] = []
        faces:   list[dict] = []

        if _yolo_ok:
            objects = await loop.run_in_executor(None, _run_yolo, frame)
        if _face_ok:
            faces = await loop.run_in_executor(None, _run_faces, frame)

        return {"objects": objects, "faces": faces, "source": "remote"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("VISION_PORT", "8001"))
    uvicorn.run("services.vision_server.main:app", host="0.0.0.0", port=port, reload=False)
