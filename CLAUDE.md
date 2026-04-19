# C.Y.R.U.S — Context for Claude

## Project

Local AI assistant (Spanish). Windows 10, RTX 2070 SUPER, Proxmox + Home Assistant + Frigate on LAN.
Owner: Ricardo (Lima, Peru).

## Stack

- **Backend:** Python, FastAPI-style WebSocket server, faster-whisper, SpeechBrain, Coqui XTTS v2, Kokoro TTS, Ollama (local LLM), sounddevice (WASAPI)
- **Frontend:** React + TypeScript + Zustand + Tailwind + Framer Motion
- **DB:** SQLite (conversation history), Qdrant (semantic memory vectors)

---

## Current Status (2026-04-19)

**Last commit:** this one — GPU fixes, ASR upgrade, audio input hardening.

**Next task:** Phase 4 — Home Assistant integration.
Plan file: `docs/superpowers/plans/2026-04-12-cyrus-phases4-7-summary.md`

---

## Setup — New Machine

### Prerequisites

1. **Python 3.11+** with venv at `venv/`
2. **CUDA 12.x** + NVIDIA driver ≥ 525
3. **Ollama** installed and running (`ollama serve`)
4. Pull the LLM model:
   ```
   ollama pull qwen2.5:7b-instruct-q4_0
   ```
5. Download Piper TTS model and place at `models/tts/piper/`:
   - `es_MX-ald-medium.onnx`
   - `es_MX-ald-medium.onnx.json`
   - Download from: https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_MX/ald/medium
6. Install Python deps:
   ```
   pip install -r requirements.txt
   ```
7. Launch everything:
   ```
   python launch.py
   ```

### Critical dependency notes

- `transformers` must be `>=4.40.0,<4.46.0` — versions ≥4.50 conflict with PyTorch nightly via model_debugging_utils/k2 import chain (SpeechBrain trigger)
- `ctranslate2` 4.x bundles its own `cudnn64_8.dll` — no system cuDNN required
- `whisper_asr.py` adds ctranslate2's package dir to DLL search path automatically

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

| What | File | Notes |
|------|------|-------|
| Noise reduction | `backend/modules/audio/denoiser.py` | noisereduce spectral gating, stateless per chunk |
| Speaker recognition | `backend/modules/audio/speaker_intelligence.py` | ECAPA-TDNN, owner/guest/unknown roles, cosine similarity 0.82 threshold, EMA adaptive learning |
| Whisper ASR upgrade | `backend/modules/audio/whisper_asr.py` | Auto model: small/cpu/int8 · small/cuda/float16 · medium/cuda/float16 (≥5GB VRAM) |
| XTTS v2 voice cloning | `backend/modules/tts/xtts_tts.py` | Reference WAV conditioning, cached latents, lazy load/unload |

Engine (`backend/core/cyrus_engine.py`) wires all four. Role-based routing: OWNER full access, GUEST name-prefixed, UNKNOWN challenged.

**To use speaker recognition:** run `start_owner_enrollment` command from Control tab (8 samples).
**To use XTTS cloning:** run `record_tts_reference` command (20s recording) → saves to `data/tts/reference_voice.wav`.

Speaker profiles stored at: `data/speakers/<name>.npz`

### GPU & Audio Fixes ✅ (2026-04-19)

| What | File | Fix |
|------|------|-----|
| cuDNN probe | `backend/modules/audio/whisper_asr.py` | Replaced ctypes DLL probe with `os.add_dll_directory(ct2_dir)` + `ct2.get_cuda_device_count()` |
| WASAPI compat | `backend/modules/audio/audio_input.py` | `_open_input_stream()` detects host API before applying WasapiSettings; MME/DirectSound devices use plain InputStream |
| ASR model | `config/config.yaml` | Upgraded `asr.model: small → medium` (RTX 2070S has ≥5GB VRAM) |
| transformers pin | `requirements.txt` | `transformers>=4.40.0,<4.46.0` — permanent fix for k2/torch conflict |

---

## Key Config (config.yaml)

```yaml
speaker:
  threshold: 0.82
  data_dir: data/speakers
  model_dir: models/speaker/ecapa

asr:
  model: medium
  device: cuda
  compute_type: float16
  language: es
  initial_prompt: "Habla en español. C.Y.R.U.S es un asistente de IA personal."
  beam_size: 5

llm:
  model: qwen2.5:7b-instruct-q4_0

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

## Startup Times (RTX 2070 SUPER reference)

| Model | Time |
|-------|------|
| Whisper medium (CUDA float16) | ~19s |
| SpeechBrain ECAPA-TDNN | ~8s |
| Kokoro TTS | ~6s |
| Piper TTS | ~2s |
| Ollama 7b (first request) | ~12s |
| **Total cold boot** | **~61s** |

VRAM budget: ~2.8-3GB CYRUS models + ~4.4GB Ollama 7B = ~7.2-7.4GB (fits in 8GB).

---

## Known Tech Debt

- `_run_enrollment()` in engine is deprecated/dormant (SpeakerProfile removed) — redirected to neural enrollment
- Adaptive EMA speaker updates are in-memory only; not auto-saved between turns
- `_record_tts_reference()` uses utterance-based recording loop (may fragment on silence)
- `SpeakerProfile` TS type `{ id: string; role: string }` repeated in 3 files (not extracted)
- HyperX Cloud Flight S Chat mic fails PortAudio noise floor calibration at device index 6 (error -9984) — falls back to config silence threshold 400; non-blocking

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
