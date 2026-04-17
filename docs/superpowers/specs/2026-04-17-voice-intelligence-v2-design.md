# Voice Intelligence v2 — Design Spec

**Date:** 2026-04-17  
**Status:** Approved

---

## Goal

Upgrade C.Y.R.U.S audio pipeline with four integrated improvements:
1. Noise reduction before transcription
2. Better Whisper ASR (Spanish accuracy)
3. Neural speaker recognition with multi-role system
4. XTTS v2 voice cloning for natural TTS output

---

## Architecture

```
Mic → [Denoiser] → [VAD] → [Whisper ASR]
                                  ↓
                      [SpeakerIntelligence]
                         owner / guest / unknown
                                  ↓
                         [CyrusEngine]
                       logic per role
                                  ↓
                         [XTTS v2 Voice]
                              Audio out
```

---

## Module 1 — Denoiser (`backend/modules/audio/denoiser.py`)

**Library:** `noisereduce` (spectral gating, NumPy-based, no GPU required)

**Mode:** `stationary=True` — optimized for continuous background noise (fans, AC, TV hum)

**Pipeline position:** Applied to raw PCM before VAD and Whisper. Stateless per chunk.

**Performance:** ~5ms per 1024-sample chunk on CPU.

**Interface:**
```python
class Denoiser:
    def __init__(self, sample_rate: int = 16000) -> None: ...
    def process(self, pcm: bytes) -> bytes: ...
```

`process()` accepts int16 PCM bytes, returns denoised int16 PCM bytes of same length.

---

## Module 2 — Whisper ASR Upgrade (`backend/modules/audio/whisper_asr.py`)

**Model selection (auto at startup):**

| Environment | Model | Compute type | VRAM/RAM |
|-------------|-------|--------------|----------|
| CPU | `small` | `int8` | ~500MB RAM |
| GPU < 5GB VRAM | `small` | `float16` | ~500MB VRAM |
| GPU ≥ 5GB VRAM | `medium` | `float16` | ~1.5GB VRAM |

**Spanish accuracy improvements:**
- `initial_prompt`: `"Habla en español. C.Y.R.U.S es un asistente de IA personal."`
- `beam_size`: `1` → `5`
- `vad_filter`: `True` (already enabled, keep)
- `language`: `"es"` (already set, keep)

**Auto-detection logic:**
```python
def _select_model_and_device() -> tuple[str, str, str]:
    if cuda_available():
        vram = get_vram_gb()
        if vram >= 5.0:
            return "medium", "cuda", "float16"
        else:
            return "small", "cuda", "float16"
    return "small", "cpu", "int8"
```

No manual config needed — works on CPU, 2GB GPU, and 6GB+ GPU automatically.

---

## Module 3 — Speaker Intelligence (`backend/modules/audio/speaker_intelligence.py`)

**Replaces:** `backend/modules/audio/speaker_profile.py` (PSD cosine approach — too basic)

**Model:** SpeechBrain ECAPA-TDNN (`speechbrain/spkrec-ecapa-voxceleb`)
- Pre-trained on VoxCeleb dataset (millions of speakers)
- Generates 192-dimensional speaker embeddings
- CPU: ~80ms per utterance | GPU: ~15ms

### Roles

```python
class SpeakerRole(Enum):
    OWNER   = "owner"
    GUEST   = "guest"
    UNKNOWN = "unknown"
```

### Enrollment

- **Owner**: 8 samples × ~3 seconds each
- **Guest**: 5 samples × ~3 seconds + name label
- Embeddings averaged → stored as `.npz` file

**Storage layout:**
```
data/speakers/
  owner.npz           ← averaged embedding + raw embeddings
  guests/
    <name>.npz
```

### Recognition

```python
@dataclass
class SpeakerResult:
    role:        SpeakerRole
    speaker_id:  str          # "owner" | guest name | "unknown"
    confidence:  float        # cosine similarity score 0..1
```

Threshold for positive match: `0.82` (configurable in `config.yaml`).

### Adaptive online learning

After each correct recognition (confidence > 0.92), the stored embedding is updated:
```
new_embedding = 0.95 × stored + 0.05 × current
```
The fingerprint improves with use without full re-enrollment.

### Interface

```python
class SpeakerIntelligence:
    def enroll(self, role: SpeakerRole, name: str, pcm_samples: list[bytes]) -> None: ...
    def identify(self, pcm: bytes) -> SpeakerResult: ...
    def list_speakers(self) -> list[dict]: ...
    def remove_speaker(self, speaker_id: str) -> None: ...
    def save(self) -> None: ...
    def load(self) -> None: ...
```

---

## Module 4 — XTTS v2 Voice (`backend/modules/audio/xtts_voice.py`)

**Model:** Coqui XTTS v2 (`tts_models/multilingual/multi-dataset/xtts_v2`)

**Voice cloning:** User records 15–30 seconds of reference audio. XTTS extracts speaker conditioning vector. No fine-tuning required.

**Memory strategy — lazy loading:**
- Model is NOT kept in memory at all times
- Loaded on first TTS request, unloaded after `idle_unload_secs` (default: 120s)
- Prevents saturating 2GB GPU when ASR + SpeakerIntelligence are also loaded

**VRAM budget (2GB GPU scenario):**
| Module | VRAM |
|--------|------|
| Whisper small | ~500MB |
| ECAPA-TDNN | ~100MB |
| XTTS v2 (loaded) | ~1.4GB |
| Total peak | ~2.0GB |

XTTS loads only while speaking — no overlap with ASR processing.

**Reference audio storage:**
```
data/tts/
  reference_voice.wav    ← 15-30 sec sample for cloning
  speaker_conditioning.pt ← pre-computed conditioning vector (cached)
```

**Interface:**
```python
class XTTSVoice:
    def synthesize(self, text: str, language: str = "es") -> bytes: ...  # returns WAV bytes
    def set_reference(self, wav_path: str) -> None: ...
    def unload(self) -> None: ...
```

---

## Role-Based Response System (CyrusEngine)

```python
match speaker_result.role:
    case SpeakerRole.OWNER:
        # full access — all commands, memory, home automation, camera
        process_normally(utterance)

    case SpeakerRole.GUEST:
        # limited access — general questions only
        process_with_limited_context(utterance, guest_name=speaker_result.speaker_id)

    case SpeakerRole.UNKNOWN:
        # ask for identification
        respond("No reconozco tu voz. ¿Quién eres?")
        # if they give a name, register as temporary guest
```

---

## Enrollment UI (Control View)

New section in `/control` frontend tab:

- **"Enrollar propietario"** — records 8 samples guided, shows progress
- **"Enrollar invitado"** — input name + 5 samples
- **"Huellas guardadas"** — list of enrolled speakers with delete option
- **"Grabar voz de referencia TTS"** — record 15-30 sec for XTTS cloning

Backend WebSocket events:
- `enrollment_start` / `enrollment_sample` / `enrollment_complete` (already partially implemented)
- New: `tts_reference_start` / `tts_reference_complete`

---

## Integration Points

| File | Change |
|------|--------|
| `backend/core/cyrus_engine.py` | Wire Denoiser → SpeakerIntelligence → role logic |
| `backend/modules/audio/whisper_asr.py` | Auto model/device selection, better prompts |
| `backend/modules/audio/audio_input.py` | Call Denoiser on raw PCM before returning |
| `backend/core/config_manager.py` | Add `speaker_threshold`, `xtts_idle_unload_secs` |
| `config/config.yaml` | Add speaker + xtts config keys |
| `frontend/src/views/ControlView.tsx` | Enrollment UI section |
| `requirements.txt` | Add `noisereduce`, `speechbrain`, `TTS` (Coqui) |

---

## Hardware Compatibility

| Scenario | Works | Notes |
|----------|-------|-------|
| CPU only | Yes | Slower, all features available |
| GPU 2GB | Yes | XTTS lazy-loaded, no simultaneous overlap |
| GPU 4GB | Yes | Comfortable headroom |
| GPU 6GB+ | Yes | Can keep XTTS loaded, use medium Whisper |

---

## Dependencies to Add

```
noisereduce>=3.0
speechbrain>=1.0
TTS>=0.22.0          # Coqui XTTS v2
```

`speaker_profile.py` can be kept for backward compatibility during transition but is deprecated.
