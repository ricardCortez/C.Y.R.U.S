# C.Y.R.U.S — Context for Claude

## Project

Local AI assistant (Spanish). Windows 11, RTX 2070S, Proxmox + Home Assistant + Frigate on LAN.
Owner: Ricardo (Lima, Peru).

## Stack

- **Backend:** Python, FastAPI-style WebSocket server, faster-whisper, SpeechBrain, Coqui XTTS v2, Ollama (local LLM), sounddevice (WASAPI)
- **Frontend:** React + TypeScript + Zustand + Tailwind + Framer Motion
- **DB:** SQLite (conversation history), Qdrant (semantic memory vectors)

---

## Current Status (2026-04-18)

**Last commit:** `763dfd5` — Voice Intelligence v2 complete.

**Next task:** Phase 4 — Home Assistant integration.
Plan file: `docs/superpowers/plans/2026-04-12-cyrus-phases4-7-summary.md`

---

## Completed Work

### Phase 1 — Core Audio Loop ✅
Full pipeline: Mic → VAD → Whisper ASR → TriggerDetector → LLM → TTS → Speaker.
WebSocket server + React frontend.

### Phase 2 — Vision & Cameras ✅
LocalCamera (OpenCV), FrigateClient (NVR), YOLO, FaceDetector, VisionManager.

### Phase 3 — Memory & Context ✅
Embedder (sentence-transformers), Qdrant vector store, SQLite conversation DB, MemoryManager.
Memory disabled by default (`memory.enabled: false` in config.yaml — requires Qdrant running).

### Voice Intelligence v2 ✅ (2026-04-18)
Four integrated upgrades:

| What | File | Notes |
|------|------|-------|
| Noise reduction | `backend/modules/audio/denoiser.py` | noisereduce spectral gating, stateless per chunk |
| Speaker recognition | `backend/modules/audio/speaker_intelligence.py` | ECAPA-TDNN, owner/guest/unknown roles, cosine similarity 0.82 threshold, EMA adaptive learning |
| Whisper ASR upgrade | `backend/modules/audio/whisper_asr.py` | Auto model: small/cpu/int8 · small/cuda/float16 · medium/cuda/float16 (≥5GB VRAM) |
| XTTS v2 voice cloning | `backend/modules/tts/xtts_tts.py` | Reference WAV conditioning, cached latents, lazy load/unload |

Engine (`backend/core/cyrus_engine.py`) wires all four. Role-based routing: OWNER full access, GUEST name-prefixed, UNKNOWN challenged.

New frontend section in ControlView: enroll owner/guest, delete profiles, record TTS reference voice.

**To use speaker recognition:** run `start_owner_enrollment` command from Control tab (8 samples).
**To use XTTS cloning:** run `record_tts_reference` command (20s recording) → saves to `data/tts/reference_voice.wav`.

Speaker profiles stored at: `data/speakers/<name>.npz`

---

## Key Config (config.yaml)

```yaml
speaker:
  threshold: 0.82
  data_dir: data/speakers
  model_dir: models/speaker/ecapa

asr:
  model: small
  initial_prompt: "Habla en español. C.Y.R.U.S es un asistente de IA personal."
  beam_size: 5

local:
  tts:
    xtts:
      enabled: true
      reference_voice: data/tts/reference_voice.wav
      idle_unload_secs: 120
```

---

## Phase 4 — Home Assistant (NEXT)

**Goal:** "Enciende las luces" → Philips Hue via HA REST API.

**Files to create:**
- `backend/modules/home_assistant/ha_client.py`
- `backend/modules/home_assistant/device_controller.py`
- `backend/modules/home_assistant/__init__.py`
- `tests/test_home_assistant.py`

**Files to modify:** `cyrus_engine.py`, `config.yaml` (`home_assistant:` section), `requirements.txt` (no new deps — httpx already included).

**Needs from user:** HA base URL + Long-Lived Access Token.

---

## Known Tech Debt

- `_run_enrollment()` in engine is deprecated/dormant (SpeakerProfile removed) — redirected to neural enrollment
- Adaptive EMA speaker updates are in-memory only; not auto-saved between turns
- `_record_tts_reference()` uses utterance-based recording loop (may fragment on silence)
- `SpeakerProfile` TS type `{ id: string; role: string }` repeated in 3 files (not extracted)

---

## Test Patterns

```python
# Mock cv2
import sys
sys.modules["cv2"] = MagicMock()

# Mock qdrant
sys.modules["qdrant_client"] = MagicMock()
sys.modules["qdrant_client.models"] = MagicMock()
```
