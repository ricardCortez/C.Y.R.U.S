"""
C.Y.R.U.S — TTS Microservice (port 8020).

Standalone FastAPI server that exposes Kokoro / Piper / Edge-TTS as an HTTP API.
Drop-in compatible with xtts-api-server so RemoteTTS needs zero changes.

Endpoints
---------
GET  /health                  → {"status":"ok", "backend":"kokoro"}
GET  /speakers                → [{"name":"ef_dora", "engine":"kokoro"}, ...]
POST /tts_to_audio            → audio/wav   (xtts-api-server compat)
POST /v1/audio/speech         → audio/wav   (OpenAI TTS compat)

Start
-----
    python -m services.tts_server.main
    # or from project root:
    uvicorn services.tts_server.main:app --host 0.0.0.0 --port 8020
"""

from __future__ import annotations

import io
import os
import wave
from typing import Optional

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

app = FastAPI(title="C.Y.R.U.S TTS Server", version="1.0.0")

# ---------------------------------------------------------------------------
# Engine wrappers (loaded lazily on startup)
# ---------------------------------------------------------------------------

_kokoro = None          # KokoroTTS instance
_piper  = None          # PiperTTS instance (optional)
_xtts   = None          # XTTTS instance (optional — needs coqui-tts)
_active = "none"        # name of the first loaded engine


def _load_engines() -> None:
    global _kokoro, _piper, _xtts, _active

    # ── Kokoro ──────────────────────────────────────────────────────────
    try:
        from kokoro import KPipeline
        import sys, os
        # Find config to get voice / speed — fall back to sensible defaults
        _voice      = os.environ.get("TTS_VOICE", "ef_dora")
        _speed      = float(os.environ.get("TTS_SPEED", "0.92"))
        _lang_code  = os.environ.get("TTS_LANG_CODE", "e")
        _sample_rate = int(os.environ.get("TTS_SAMPLE_RATE", "24000"))

        pipeline = KPipeline(lang_code=_lang_code, repo_id="hexgrad/Kokoro-82M")
        _kokoro = {
            "pipeline": pipeline,
            "voice": _voice,
            "speed": _speed,
            "sample_rate": _sample_rate,
        }
        _active = "kokoro"
        print(f"[TTS-Server] Kokoro ready (voice={_voice})")
    except Exception as exc:
        print(f"[TTS-Server] Kokoro unavailable: {exc}")

    # ── Piper (optional) ────────────────────────────────────────────────
    piper_model = os.environ.get("PIPER_MODEL", "")
    if piper_model:
        try:
            from piper import PiperVoice
            from piper.voice import SynthesisConfig
            voice = PiperVoice.load(piper_model)
            _piper = {"voice": voice, "speed": float(os.environ.get("TTS_SPEED", "0.92"))}
            _active = "piper"
            print(f"[TTS-Server] Piper ready (model={piper_model})")
        except Exception as exc:
            print(f"[TTS-Server] Piper unavailable: {exc}")

    # ── XTTS v2 (optional — needs coqui-tts) ───────────────────────────
    try:
        os.environ.setdefault("COQUI_TOS_AGREED", "1")
        import torch
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts
        from TTS.utils.manage import ModelManager

        dev = os.environ.get("XTTS_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
        _XTTS_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"

        manager = ModelManager()
        model_path, config_path, _ = manager.download_model(_XTTS_MODEL)

        config = XttsConfig()
        config.load_json(config_path)
        xtts_model = Xtts.init_from_config(config)
        xtts_model.load_checkpoint(config, checkpoint_dir=model_path, eval=True)
        xtts_model.to(dev)

        _xtts = {
            "model":    xtts_model,
            "language": os.environ.get("TTS_LANGUAGE", "es"),
            "speaker":  os.environ.get("XTTS_SPEAKER", "Tammie Ema"),
            "device":   dev,
        }
        _active = "xtts-v2"
        print(f"[TTS-Server] XTTS v2 ready (device={dev})")
    except Exception as exc:
        print(f"[TTS-Server] XTTS v2 unavailable: {exc}")

    if _active == "none":
        print("[TTS-Server] WARNING: no TTS engine loaded — all requests will fail")


@app.on_event("startup")
async def on_startup() -> None:
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _load_engines)


# ---------------------------------------------------------------------------
# Synthesis helpers
# ---------------------------------------------------------------------------

def _kokoro_synth(text: str) -> bytes:
    pipeline    = _kokoro["pipeline"]
    voice       = _kokoro["voice"]
    speed       = _kokoro["speed"]
    sample_rate = _kokoro["sample_rate"]

    segments = []
    for _, _, audio in pipeline(text, voice=voice, speed=speed, split_pattern=r"\n+"):
        if audio is not None:
            segments.append(audio)

    if not segments:
        raise RuntimeError("Kokoro returned no audio")

    combined = np.concatenate(segments)
    audio_i16 = np.clip(combined * 32767, -32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_i16.tobytes())
    return buf.getvalue()


def _piper_synth(text: str) -> bytes:
    from piper.voice import SynthesisConfig
    voice = _piper["voice"]
    speed = _piper["speed"]
    length_scale = round(1.0 / speed, 3)
    cfg = SynthesisConfig(length_scale=length_scale)

    pcm_parts = []
    sample_rate = 22050
    for chunk in voice.synthesize(text, cfg):
        pcm_parts.append(chunk.audio_int16_bytes)
        sample_rate = chunk.sample_rate

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(pcm_parts))
    return buf.getvalue()


def _xtts_synth(text: str) -> bytes:
    import io as _io, wave as _wave
    import numpy as _np
    from pathlib import Path

    model    = _xtts["model"]
    language = _xtts["language"]
    speaker  = _xtts["speaker"]

    sp = str(speaker)
    speaker_wav = sp if Path(sp).is_file() else None

    if speaker_wav:
        gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
            audio_path=[speaker_wav]
        )
    else:
        gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
            audio_path=[]
        )

    out = model.inference(
        text=text,
        language=language,
        gpt_cond_latent=gpt_cond_latent,
        speaker_embedding=speaker_embedding,
    )

    audio = out["wav"]
    if hasattr(audio, "cpu"):
        audio = audio.cpu().numpy()
    audio = _np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767).astype(_np.int16)

    buf = _io.BytesIO()
    with _wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def _synthesise(text: str) -> bytes:
    """Run synthesis with the best available engine."""
    # XTTS first (if loaded) — highest quality
    if _xtts:
        try:
            return _xtts_synth(text)
        except Exception as exc:
            print(f"[TTS-Server] XTTS failed: {exc}; trying Piper/Kokoro")
    # Piper
    if _piper:
        try:
            return _piper_synth(text)
        except Exception as exc:
            print(f"[TTS-Server] Piper failed: {exc}; trying Kokoro")
    # Kokoro
    if _kokoro:
        return _kokoro_synth(text)
    raise RuntimeError("No TTS engine available")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class TTSRequest(BaseModel):
    text: str
    speaker_wav: Optional[str] = None    # xtts-api-server compat (ignored — use XTTS_SPEAKER env)
    language:    Optional[str] = None    # ignored if only Kokoro is loaded


class OpenAITTSRequest(BaseModel):
    model:  str = "tts-1"
    input:  str
    voice:  Optional[str] = None
    speed:  Optional[float] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "backend": _active}


@app.get("/speakers")
async def speakers():
    result = []
    if _xtts:
        result.append({"name": _xtts["speaker"], "engine": "xtts-v2"})
    if _piper:
        result.append({"name": "piper-default", "engine": "piper"})
    if _kokoro:
        result.append({"name": _kokoro["voice"], "engine": "kokoro"})
    return result


@app.post("/tts_to_audio")
async def tts_to_audio(req: TTSRequest):
    """xtts-api-server compatible endpoint."""
    if not req.text.strip():
        raise HTTPException(400, "text is empty")
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        wav = await loop.run_in_executor(None, _synthesise, req.text)
        return Response(content=wav, media_type="audio/wav")
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/v1/audio/speech")
async def openai_speech(req: OpenAITTSRequest):
    """OpenAI-compatible TTS endpoint."""
    if not req.input.strip():
        raise HTTPException(400, "input is empty")
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        wav = await loop.run_in_executor(None, _synthesise, req.input)
        return Response(content=wav, media_type="audio/wav")
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    host = os.environ.get("TTS_HOST", "0.0.0.0")
    port = int(os.environ.get("TTS_PORT", "8020"))
    uvicorn.run("services.tts_server.main:app", host=host, port=port, reload=False)
