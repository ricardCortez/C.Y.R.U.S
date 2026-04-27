"""
JARVIS — ASR Microservice (port 8000).

Standalone FastAPI server wrapping faster-whisper.
OpenAI-compatible /v1/audio/transcriptions endpoint so any OpenAI client works.

Endpoints
---------
GET  /health                        → {"status":"ok","model":"tiny"}
POST /v1/audio/transcriptions       → {"text":"...", "language":"es"}   (OpenAI compat)
POST /transcribe                    → {"text":"...", "language":"es"}   (simple JSON)

Start
-----
    python -m services.asr_server.main
    # or:
    uvicorn services.asr_server.main:app --host 0.0.0.0 --port 8000

Environment variables
---------------------
    ASR_MODEL       whisper model size  (default: tiny)
    ASR_DEVICE      cuda | cpu          (default: cuda)
    ASR_COMPUTE     float16 | int8      (default: float16)
    ASR_LANGUAGE    force language      (default: es)
    ASR_PORT        listen port         (default: 8000)
"""

from __future__ import annotations

import io
import os
import wave
from pathlib import Path
from typing import Optional

import uvicorn

from backend.utils.logger import configure_file_logging, get_logger

_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
configure_file_logging(_LOG_DIR, level="INFO", process_name="asr")
logger = get_logger("jarvis.asr.server")
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

app = FastAPI(title="JARVIS ASR Server", version="1.0.0")

_model = None
_model_size = os.environ.get("ASR_MODEL", "tiny")
_language   = os.environ.get("ASR_LANGUAGE", "es") or None


def _load_model() -> None:
    global _model
    from faster_whisper import WhisperModel
    device       = os.environ.get("ASR_DEVICE", "cuda")
    compute_type = os.environ.get("ASR_COMPUTE", "float16")
    print(f"[ASR-Server] Loading whisper/{_model_size} on {device} ({compute_type})…")
    try:
        _model = WhisperModel(_model_size, device=device, compute_type=compute_type)
        print(f"[ASR-Server] Model ready")
    except Exception as exc:
        print(f"[ASR-Server] CUDA failed ({exc}); falling back to CPU/int8")
        _model = WhisperModel(_model_size, device="cpu", compute_type="int8")
        print("[ASR-Server] Model ready (CPU fallback)")


@app.on_event("startup")
async def on_startup():
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _load_model)


# ---------------------------------------------------------------------------
# Transcription helper
# ---------------------------------------------------------------------------

def _do_transcribe(audio_bytes: bytes, sample_rate: int = 16000, content_type: str = "audio/wav") -> tuple[str, str]:
    """Run faster-whisper transcription on raw WAV or PCM bytes."""
    if _model is None:
        raise RuntimeError("Model not loaded")

    # If raw PCM (not WAV), wrap it
    if not audio_bytes[:4] == b"RIFF":
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_bytes)
        audio_bytes = buf.getvalue()

    audio_file = io.BytesIO(audio_bytes)
    segments, info = _model.transcribe(
        audio_file,
        language=_language,
        beam_size=5,
        vad_filter=True,
        initial_prompt="Hola JARVIS, oye JARVIS, hey JARVIS, JARVIS",
    )
    text = " ".join(seg.text.strip() for seg in segments).strip()
    lang = info.language or (_language or "es")
    return text, lang


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok" if _model else "loading", "model": _model_size}


@app.post("/v1/audio/transcriptions")
async def openai_transcriptions(
    file: UploadFile = File(...),
    model: str = Form("whisper-1"),
    language: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
):
    """OpenAI-compatible transcription endpoint."""
    if _model is None:
        raise HTTPException(503, "Model not loaded yet")
    try:
        audio_bytes = await file.read()
        import asyncio
        loop = asyncio.get_event_loop()
        text, lang = await loop.run_in_executor(None, _do_transcribe, audio_bytes, 16000, file.content_type or "audio/wav")
        return {"text": text, "language": lang}
    except Exception as exc:
        raise HTTPException(500, str(exc))


class TranscribeRequest(BaseModel):
    audio_b64: str              # base64-encoded WAV or PCM bytes
    sample_rate: int = 16000
    is_pcm: bool = False        # True if raw PCM (not WAV)


@app.post("/transcribe")
async def transcribe_json(req: TranscribeRequest):
    """Simple JSON transcription endpoint (base64-encoded audio)."""
    if _model is None:
        raise HTTPException(503, "Model not loaded yet")
    import base64, asyncio
    try:
        audio_bytes = base64.b64decode(req.audio_b64)
        loop = asyncio.get_event_loop()
        text, lang = await loop.run_in_executor(
            None, _do_transcribe, audio_bytes, req.sample_rate,
            "audio/pcm" if req.is_pcm else "audio/wav"
        )
        return {"text": text, "language": lang}
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("ASR_PORT", "8000"))
    uvicorn.run("services.asr_server.main:app", host="0.0.0.0", port=port, reload=False)
