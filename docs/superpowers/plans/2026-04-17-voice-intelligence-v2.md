# Voice Intelligence v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade JARVIS audio pipeline with noise reduction, better ASR, neural speaker recognition (multi-role), and XTTS v2 voice cloning.

**Architecture:** Denoiser cleans PCM before Whisper. SpeakerIntelligence (ECAPA-TDNN) replaces the PSD cosine SpeakerProfile and identifies owner/guest/unknown. XTTS v2 caches conditioning latents for fast cloned-voice synthesis. CyrusEngine routes responses per speaker role.

**Tech Stack:** `noisereduce` (spectral gating), `speechbrain` (ECAPA-TDNN), `faster-whisper` (small/medium model), `TTS` (Coqui XTTS v2), `torch`

---

## File Map

| Action | File |
|--------|------|
| Create | `backend/modules/audio/denoiser.py` |
| Create | `backend/modules/audio/speaker_intelligence.py` |
| Modify | `backend/modules/audio/whisper_asr.py` |
| Modify | `backend/modules/tts/xtts_tts.py` |
| Modify | `backend/core/config_manager.py` |
| Modify | `backend/core/cyrus_engine.py` |
| Modify | `config/config.yaml` |
| Modify | `requirements.txt` |
| Modify | `tests/test_audio.py` |
| Create | `tests/test_speaker_intelligence.py` |
| Modify | `frontend/src/views/ControlView.tsx` |

---

## Task 1: Add Dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add packages to requirements.txt**

Open `requirements.txt` and add after the `# ── Automatic Speech Recognition` section:

```
# ── Noise Reduction ───────────────────────────────────────────────────────────
noisereduce>=3.0.0

# ── Speaker Recognition ───────────────────────────────────────────────────────
speechbrain>=1.0.0
```

And add after the `# ── Text-to-Speech` section (TTS was missing from requirements):

```
TTS>=0.22.0                # Coqui XTTS v2 voice cloning
```

- [ ] **Step 2: Install new packages**

```bash
pip install noisereduce>=3.0.0 speechbrain>=1.0.0 "TTS>=0.22.0"
```

Expected: All three packages install without error. SpeechBrain will download dependencies.

- [ ] **Step 3: Verify imports**

```bash
python -c "import noisereduce; import speechbrain; from TTS.tts.models.xtts import Xtts; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "feat(deps): add noisereduce, speechbrain, TTS for voice intelligence v2"
```

---

## Task 2: Denoiser Module

**Files:**
- Create: `backend/modules/audio/denoiser.py`
- Modify: `tests/test_audio.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_audio.py`:

```python
def test_denoiser_returns_same_length():
    from backend.modules.audio.denoiser import Denoiser
    d = Denoiser(sample_rate=16000)
    import numpy as np
    pcm = (np.random.randn(16000) * 100).astype(np.int16).tobytes()
    result = d.process(pcm)
    assert len(result) == len(pcm)

def test_denoiser_handles_empty():
    from backend.modules.audio.denoiser import Denoiser
    d = Denoiser(sample_rate=16000)
    result = d.process(b"")
    assert result == b""

def test_denoiser_reduces_noise():
    from backend.modules.audio.denoiser import Denoiser
    import numpy as np
    d = Denoiser(sample_rate=16000)
    # Create pure noise signal
    noise = (np.random.randn(16000) * 500).astype(np.int16)
    pcm = noise.tobytes()
    result = d.process(pcm)
    result_arr = np.frombuffer(result, dtype=np.int16).astype(np.float32)
    noise_arr = noise.astype(np.float32)
    # RMS of result should be lower than input noise RMS
    assert np.sqrt(np.mean(result_arr**2)) < np.sqrt(np.mean(noise_arr**2))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_audio.py::test_denoiser_returns_same_length -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.modules.audio.denoiser'`

- [ ] **Step 3: Create `backend/modules/audio/denoiser.py`**

```python
"""
JARVIS — Spectral noise reduction for PCM audio.

Applies stationary noise reduction (noisereduce) to int16 PCM bytes
before VAD and Whisper transcription.
"""
from __future__ import annotations

import numpy as np

from backend.utils.logger import get_logger

logger = get_logger("jarvis.audio.denoiser")

try:
    import noisereduce as nr
    _NR_AVAILABLE = True
except ImportError:
    _NR_AVAILABLE = False
    logger.warning("[JARVIS] Denoiser: noisereduce not installed — passthrough mode")


class Denoiser:
    """Stationary spectral noise gate for 16 kHz mono int16 PCM.

    Args:
        sample_rate: PCM sample rate in Hz (default 16000).
        prop_decrease: Strength of noise reduction 0.0–1.0 (default 0.75).
    """

    def __init__(self, sample_rate: int = 16000, prop_decrease: float = 0.75) -> None:
        self._sr = sample_rate
        self._prop = prop_decrease

    def process(self, pcm: bytes) -> bytes:
        """Return denoised PCM bytes of the same length as input.

        Falls back to passthrough if noisereduce is unavailable or audio is empty.
        """
        if not pcm or not _NR_AVAILABLE:
            return pcm

        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if arr.size == 0:
            return pcm

        try:
            reduced = nr.reduce_noise(
                y=arr,
                sr=self._sr,
                stationary=True,
                prop_decrease=self._prop,
            )
            out = np.clip(reduced * 32768.0, -32768, 32767).astype(np.int16)
            return out.tobytes()
        except Exception as exc:
            logger.debug(f"[JARVIS] Denoiser: failed ({exc}) — passthrough")
            return pcm
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_audio.py::test_denoiser_returns_same_length tests/test_audio.py::test_denoiser_handles_empty tests/test_audio.py::test_denoiser_reduces_noise -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/modules/audio/denoiser.py tests/test_audio.py
git commit -m "feat(audio): add spectral noise reduction denoiser module"
```

---

## Task 3: Config Updates

**Files:**
- Modify: `backend/core/config_manager.py`
- Modify: `config/config.yaml`

- [ ] **Step 1: Add `SpeakerConfig` dataclass to `config_manager.py`**

After the `AudioOutputConfig` dataclass (around line 94), add:

```python
@dataclass
class SpeakerConfig:
    threshold: float = 0.82
    adaptive_lr: float = 0.05          # online learning rate for embedding update
    data_dir: str = "data/speakers"    # where .npz fingerprints are stored
    model_dir: str = "models/speaker/ecapa"  # local SpeechBrain model cache
```

Then add `speaker` field to `JARVISConfig` (around line 215, after `services`):

```python
@dataclass
class JARVISConfig:
    system: SystemConfig = field(default_factory=SystemConfig)
    local: LocalConfig = field(default_factory=LocalConfig)
    api: APIConfig = field(default_factory=APIConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    trigger: TriggerConfig = field(default_factory=TriggerConfig)
    asr: ASRConfig = field(default_factory=ASRConfig)
    conversation: ConversationConfig = field(default_factory=ConversationConfig)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    services: ServicesConfig = field(default_factory=ServicesConfig)
    speaker: SpeakerConfig = field(default_factory=SpeakerConfig)   # ← add this

    project_root: Path = field(default_factory=Path.cwd)
    soul_text: str = ""
    prompts: Dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 2: Add speaker config loader in `load_config()`**

In `load_config()`, after the services block (around line 363), add:

```python
    # ── speaker recognition ───────────────────────────────────────────────────
    if spk := raw.get("speaker"):
        cfg.speaker = SpeakerConfig(**{k: v for k, v in spk.items() if k in SpeakerConfig.__dataclass_fields__})
```

- [ ] **Step 3: Update `config/config.yaml`**

Add the following section at the end of `config.yaml`, before the `services:` block:

```yaml
speaker:
  threshold: 0.82
  adaptive_lr: 0.05
  data_dir: data/speakers
  model_dir: models/speaker/ecapa
```

Also update the `asr:` section to use `small` model and add Spanish prompt:

```yaml
asr:
  model: small
  device: cuda
  compute_type: float16
  language: es
  beam_size: 5
  vad_filter: false
  initial_prompt: "Habla en español. JARVIS es un asistente de IA personal."
```

And update the XTTS config under `local.tts.xtts`:

```yaml
    xtts:
      enabled: true
      language: es
      speaker: Tammie Ema
      reference_voice: data/tts/reference_voice.wav
      idle_unload_secs: 120
```

- [ ] **Step 4: Verify config loads**

```bash
python -c "from backend.core.config_manager import load_config; cfg = load_config(); print(cfg.speaker.threshold, cfg.asr.model)"
```

Expected: `0.82 small`

- [ ] **Step 5: Commit**

```bash
git add backend/core/config_manager.py config/config.yaml
git commit -m "feat(config): add SpeakerConfig dataclass and voice intelligence v2 config keys"
```

---

## Task 4: SpeakerIntelligence Module (ECAPA-TDNN)

**Files:**
- Create: `backend/modules/audio/speaker_intelligence.py`
- Create: `tests/test_speaker_intelligence.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_speaker_intelligence.py`:

```python
"""Tests for SpeakerIntelligence ECAPA-TDNN module."""
import numpy as np
import pytest
from pathlib import Path
import tempfile


def _make_pcm(seconds: float = 2.0, sr: int = 16000) -> bytes:
    """Generate synthetic speech-like PCM (sine wave burst)."""
    t = np.linspace(0, seconds, int(sr * seconds))
    wave = (np.sin(2 * np.pi * 200 * t) * 8000).astype(np.int16)
    return wave.tobytes()


def test_speaker_intelligence_imports():
    from backend.modules.audio.speaker_intelligence import (
        SpeakerIntelligence, SpeakerRole, SpeakerResult
    )
    assert SpeakerRole.OWNER.value == "owner"
    assert SpeakerRole.GUEST.value == "guest"
    assert SpeakerRole.UNKNOWN.value == "unknown"


def test_identify_returns_unknown_without_profiles(tmp_path):
    from backend.modules.audio.speaker_intelligence import (
        SpeakerIntelligence, SpeakerRole
    )
    si = SpeakerIntelligence(
        data_dir=str(tmp_path),
        model_dir=str(tmp_path / "model"),
        threshold=0.82,
    )
    # Don't load the real model — test the fallback path
    pcm = _make_pcm()
    result = si.identify(pcm)
    assert result.role == SpeakerRole.UNKNOWN
    assert result.confidence == 0.0


def test_list_speakers_empty(tmp_path):
    from backend.modules.audio.speaker_intelligence import SpeakerIntelligence
    si = SpeakerIntelligence(
        data_dir=str(tmp_path),
        model_dir=str(tmp_path / "model"),
        threshold=0.82,
    )
    assert si.list_speakers() == []


def test_remove_nonexistent_speaker_does_not_raise(tmp_path):
    from backend.modules.audio.speaker_intelligence import SpeakerIntelligence
    si = SpeakerIntelligence(
        data_dir=str(tmp_path),
        model_dir=str(tmp_path / "model"),
        threshold=0.82,
    )
    si.remove_speaker("nobody")  # should not raise


def test_enroll_and_identify_owner(tmp_path, monkeypatch):
    """Enroll owner, then identify should return OWNER with mocked embedder."""
    from backend.modules.audio.speaker_intelligence import (
        SpeakerIntelligence, SpeakerRole
    )
    import numpy as np

    si = SpeakerIntelligence(
        data_dir=str(tmp_path),
        model_dir=str(tmp_path / "model"),
        threshold=0.60,
    )

    # Mock _embed to return a deterministic unit vector
    fixed_embed = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    monkeypatch.setattr(si, "_embed", lambda pcm: fixed_embed)

    # Enroll owner with 3 samples
    pcm_samples = [_make_pcm() for _ in range(3)]
    si.enroll(SpeakerRole.OWNER, "owner", pcm_samples)

    # Identify with same fixed embedding
    result = si.identify(_make_pcm())
    assert result.role == SpeakerRole.OWNER
    assert result.speaker_id == "owner"
    assert result.confidence >= 0.99


def test_enroll_guest_identified_as_guest(tmp_path, monkeypatch):
    from backend.modules.audio.speaker_intelligence import (
        SpeakerIntelligence, SpeakerRole
    )
    import numpy as np

    si = SpeakerIntelligence(
        data_dir=str(tmp_path),
        model_dir=str(tmp_path / "model"),
        threshold=0.60,
    )

    owner_embed = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    guest_embed = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    call_count = {"n": 0}

    def mock_embed(pcm):
        call_count["n"] += 1
        # First N calls during enrollment return owner/guest embeds;
        # the last call (identify) returns guest embed
        return guest_embed

    monkeypatch.setattr(si, "_embed", mock_embed)
    si.enroll(SpeakerRole.OWNER, "owner", [_make_pcm()])

    # Override owner embedding manually to owner vector
    si._profiles["owner"]["embedding"] = owner_embed

    si.enroll(SpeakerRole.GUEST, "carlos", [_make_pcm()])
    result = si.identify(_make_pcm())
    assert result.role == SpeakerRole.GUEST
    assert result.speaker_id == "carlos"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_speaker_intelligence.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `backend/modules/audio/speaker_intelligence.py`**

```python
"""
JARVIS — Neural speaker recognition with role-based access control.

Uses SpeechBrain ECAPA-TDNN to compute 192-dim speaker embeddings.
Supports multi-speaker enrollment (owner / guests) with online adaptive learning.
Falls back gracefully when SpeechBrain is not installed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from backend.utils.logger import get_logger

logger = get_logger("jarvis.audio.speaker_intelligence")

try:
    import torch
    import torchaudio
    _TORCH_OK = True
except ImportError:
    _TORCH_OK = False

try:
    from speechbrain.inference.speaker import EncoderClassifier
    _SB_OK = True
except ImportError:
    _SB_OK = False
    logger.warning("[JARVIS] SpeakerIntelligence: speechbrain not installed — fallback to UNKNOWN")


class SpeakerRole(Enum):
    OWNER   = "owner"
    GUEST   = "guest"
    UNKNOWN = "unknown"


@dataclass
class SpeakerResult:
    role:        SpeakerRole
    speaker_id:  str
    confidence:  float


class SpeakerIntelligence:
    """Neural multi-speaker recognition with ECAPA-TDNN.

    Stores one embedding centroid per enrolled speaker.  Identifies speakers
    by cosine similarity.  Online adaptive learning updates the centroid on
    high-confidence matches.

    Args:
        data_dir:    Directory where .npz profiles are persisted.
        model_dir:   Local cache path for SpeechBrain model download.
        threshold:   Cosine similarity required for a positive match (0–1).
        adaptive_lr: EMA learning rate for online centroid update (0–1).
        sample_rate: Expected PCM sample rate.
    """

    def __init__(
        self,
        data_dir: str = "data/speakers",
        model_dir: str = "models/speaker/ecapa",
        threshold: float = 0.82,
        adaptive_lr: float = 0.05,
        sample_rate: int = 16000,
    ) -> None:
        self._data_dir    = Path(data_dir)
        self._model_dir   = Path(model_dir)
        self._threshold   = threshold
        self._adaptive_lr = adaptive_lr
        self._sr          = sample_rate
        self._classifier  = None   # EncoderClassifier — lazy loaded

        # In-memory profiles: { speaker_id: { "role": SpeakerRole, "embedding": np.ndarray } }
        self._profiles: Dict[str, dict] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Download (first run) and load the ECAPA-TDNN speaker encoder."""
        if not _SB_OK or not _TORCH_OK:
            logger.warning("[JARVIS] SpeakerIntelligence: speechbrain/torch unavailable — UNKNOWN fallback active")
            return
        try:
            logger.info("[JARVIS] SpeakerIntelligence: loading ECAPA-TDNN...")
            self._model_dir.mkdir(parents=True, exist_ok=True)
            self._classifier = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir=str(self._model_dir),
                run_opts={"device": "cpu"},  # embedder always on CPU to save VRAM
            )
            logger.info("[JARVIS] SpeakerIntelligence: ECAPA-TDNN ready")
        except Exception as exc:
            logger.warning(f"[JARVIS] SpeakerIntelligence: load failed ({exc}) — UNKNOWN fallback")
            self._classifier = None

        self._data_dir.mkdir(parents=True, exist_ok=True)
        self.load_profiles()

    # ── Embedding ─────────────────────────────────────────────────────────────

    def _embed(self, pcm: bytes) -> Optional[np.ndarray]:
        """Return a unit-norm 192-dim embedding for *pcm*, or None on failure."""
        if self._classifier is None:
            return None
        try:
            arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
            if arr.size < self._sr * 0.5:  # need at least 0.5s
                return None
            waveform = torch.tensor(arr).unsqueeze(0)  # [1, samples]
            with torch.no_grad():
                emb = self._classifier.encode_batch(waveform)  # [1, 1, 192]
            vec = emb.squeeze().numpy().astype(np.float32)
            norm = np.linalg.norm(vec)
            if norm < 1e-8:
                return None
            return vec / norm
        except Exception as exc:
            logger.debug(f"[JARVIS] SpeakerIntelligence: embed error ({exc})")
            return None

    # ── Enrollment ────────────────────────────────────────────────────────────

    def enroll(self, role: SpeakerRole, name: str, pcm_samples: List[bytes]) -> None:
        """Enroll a speaker from PCM samples.

        Args:
            role:        OWNER or GUEST.
            name:        Unique speaker identifier (e.g. "owner", "carlos").
            pcm_samples: List of raw PCM utterances (at least 3 recommended).
        """
        embeddings = [self._embed(p) for p in pcm_samples]
        embeddings = [e for e in embeddings if e is not None]
        if not embeddings:
            raise ValueError(f"[JARVIS] SpeakerIntelligence: no usable audio for '{name}'")

        centroid = np.mean(embeddings, axis=0).astype(np.float32)
        norm = np.linalg.norm(centroid)
        if norm > 1e-8:
            centroid /= norm

        speaker_id = name.lower().strip()
        self._profiles[speaker_id] = {"role": role, "embedding": centroid}
        logger.info(f"[JARVIS] SpeakerIntelligence: enrolled '{speaker_id}' as {role.value} ({len(embeddings)} samples)")
        self.save()

    # ── Identification ────────────────────────────────────────────────────────

    def identify(self, pcm: bytes) -> SpeakerResult:
        """Identify speaker in *pcm* and return their role + confidence.

        Returns UNKNOWN with confidence 0.0 when no profiles are enrolled
        or when the speaker encoder is unavailable.
        """
        unknown = SpeakerResult(role=SpeakerRole.UNKNOWN, speaker_id="unknown", confidence=0.0)

        if not self._profiles:
            return unknown

        emb = self._embed(pcm)
        if emb is None:
            return unknown

        best_id    = None
        best_score = -1.0
        for spk_id, profile in self._profiles.items():
            score = float(np.dot(emb, profile["embedding"]))
            if score > best_score:
                best_score = score
                best_id    = spk_id

        if best_score < self._threshold:
            logger.debug(f"[JARVIS] SpeakerIntelligence: best={best_score:.3f} < {self._threshold} → UNKNOWN")
            return unknown

        profile = self._profiles[best_id]
        role    = profile["role"]
        logger.info(f"[JARVIS] SpeakerIntelligence: '{best_id}' ({role.value}) score={best_score:.3f}")

        # Online adaptive learning: update centroid toward current embedding
        if best_score > 0.92:
            updated = (1 - self._adaptive_lr) * profile["embedding"] + self._adaptive_lr * emb
            norm = np.linalg.norm(updated)
            if norm > 1e-8:
                profile["embedding"] = (updated / norm).astype(np.float32)

        return SpeakerResult(role=role, speaker_id=best_id, confidence=best_score)

    # ── Management ────────────────────────────────────────────────────────────

    def list_speakers(self) -> List[dict]:
        """Return list of enrolled speakers as dicts with id and role."""
        return [
            {"id": sid, "role": prof["role"].value}
            for sid, prof in self._profiles.items()
        ]

    def remove_speaker(self, speaker_id: str) -> None:
        """Remove an enrolled speaker by id."""
        sid = speaker_id.lower().strip()
        if sid in self._profiles:
            del self._profiles[sid]
            npz = self._data_dir / f"{sid}.npz"
            if npz.exists():
                npz.unlink()
            logger.info(f"[JARVIS] SpeakerIntelligence: removed '{sid}'")

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self) -> None:
        """Persist all speaker embeddings to data_dir/*.npz."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        for sid, profile in self._profiles.items():
            path = self._data_dir / f"{sid}.npz"
            np.savez(str(path), embedding=profile["embedding"], role=profile["role"].value)
        logger.debug(f"[JARVIS] SpeakerIntelligence: saved {len(self._profiles)} profiles")

    def load_profiles(self) -> None:
        """Load all .npz profiles from data_dir."""
        if not self._data_dir.exists():
            return
        for npz_path in self._data_dir.glob("*.npz"):
            try:
                data   = np.load(str(npz_path))
                sid    = npz_path.stem
                role   = SpeakerRole(str(data["role"]))
                emb    = data["embedding"].astype(np.float32)
                self._profiles[sid] = {"role": role, "embedding": emb}
                logger.info(f"[JARVIS] SpeakerIntelligence: loaded '{sid}' ({role.value})")
            except Exception as exc:
                logger.warning(f"[JARVIS] SpeakerIntelligence: could not load {npz_path}: {exc}")
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_speaker_intelligence.py -v
```

Expected: All 6 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/modules/audio/speaker_intelligence.py tests/test_speaker_intelligence.py
git commit -m "feat(audio): add ECAPA-TDNN neural speaker recognition with multi-role system"
```

---

## Task 5: Whisper ASR Auto-Model Selection

**Files:**
- Modify: `backend/modules/audio/whisper_asr.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_whisper.py`:

```python
def test_select_model_cpu():
    from backend.modules.audio.whisper_asr import WhisperASR
    model, device, compute = WhisperASR._select_model_and_device(force_cpu=True)
    assert model == "small"
    assert device == "cpu"
    assert compute == "int8"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_whisper.py::test_select_model_cpu -v
```

Expected: FAIL with `AttributeError: _select_model_and_device`

- [ ] **Step 3: Add `_select_model_and_device` to `whisper_asr.py`**

Add this static method to `WhisperASR` class, after `_cuda_usable()`:

```python
@staticmethod
def _select_model_and_device(force_cpu: bool = False) -> tuple[str, str, str]:
    """Auto-select Whisper model size and compute device based on available hardware.

    Returns:
        Tuple of (model_size, device, compute_type).
    """
    if force_cpu or not WhisperASR._cuda_usable():
        return "small", "cpu", "int8"

    try:
        import torch
        if not torch.cuda.is_available():
            return "small", "cpu", "int8"
        vram_bytes = torch.cuda.get_device_properties(0).total_memory
        vram_gb    = vram_bytes / (1024 ** 3)
        if vram_gb >= 5.0:
            return "medium", "cuda", "float16"
        else:
            return "small", "cuda", "float16"
    except Exception:
        return "small", "cpu", "int8"
```

- [ ] **Step 4: Update `load()` to call `_select_model_and_device` when model_size is "auto"**

In `load()`, replace the section starting at `device = self._device` with:

```python
        device       = self._device
        compute_type = self._compute_type
        model_size   = self._model_size

        # "auto" triggers hardware-aware selection — overrides config values
        if model_size == "auto" or device == "cuda":
            sel_model, sel_device, sel_compute = self._select_model_and_device()
            if model_size == "auto":
                model_size = sel_model
            if device == "cuda" and not self._cuda_usable():
                device       = sel_device
                compute_type = sel_compute
                logger.warning(
                    f"[JARVIS] ASR: CUDA requested but cuDNN not available — "
                    f"falling back to {device}/{compute_type}"
                )
```

Also update the `WhisperModel` call to use `model_size` instead of `self._model_size`:

```python
            self._model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
            )
```

- [ ] **Step 5: Update Spanish `initial_prompt` default in `__init__`**

Change the default `initial_prompt` in `WhisperASR.__init__`:

```python
        self._initial_prompt = initial_prompt or "Habla en español. JARVIS es un asistente de IA personal."
```

- [ ] **Step 6: Run test**

```bash
pytest tests/test_whisper.py::test_select_model_cpu -v
```

Expected: PASSED

- [ ] **Step 7: Commit**

```bash
git add backend/modules/audio/whisper_asr.py tests/test_whisper.py
git commit -m "feat(asr): add auto model/device selection based on VRAM, improve Spanish prompt"
```

---

## Task 6: XTTS Voice Cloning Enhancements

**Files:**
- Modify: `backend/modules/tts/xtts_tts.py`

The current `xtts_tts.py` computes conditioning latents on every synthesis call (slow). We add:
1. Latent caching — computed once from reference WAV, reused on every call
2. `set_reference()` — change reference voice at runtime
3. `unload()` — release model from memory for lazy unload

- [ ] **Step 1: Write the failing test**

Add to `tests/test_tts.py`:

```python
def test_xtts_set_reference_stores_path(tmp_path):
    from backend.modules.tts.xtts_tts import XTTTS
    import wave, struct
    # Create a minimal valid WAV
    wav_path = tmp_path / "ref.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(24000)
        wf.writeframes(struct.pack("<" + "h" * 24000, *([0] * 24000)))
    tts = XTTTS(language="es")
    tts.set_reference(str(wav_path))
    assert tts._reference_wav == str(wav_path)
    assert tts._cached_latents is None  # cache cleared on new reference

def test_xtts_unload_clears_model():
    from backend.modules.tts.xtts_tts import XTTTS
    tts = XTTTS(language="es")
    tts._available = True
    tts._tts = object()
    tts.unload()
    assert tts._tts is None
    assert tts._available is False
    assert tts._cached_latents is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_tts.py::test_xtts_set_reference_stores_path tests/test_tts.py::test_xtts_unload_clears_model -v
```

Expected: FAIL with `AttributeError`

- [ ] **Step 3: Rewrite `backend/modules/tts/xtts_tts.py`**

Replace the entire file with:

```python
"""
JARVIS — XTTS v2 TTS backend (Coqui AI) with voice cloning and latent caching.

Offline neural TTS.  Reference WAV conditioning latents are cached after first
computation so subsequent synthesis calls are fast (no repeated WAV loading).
"""
from __future__ import annotations

import io
import wave
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from backend.utils.exceptions import TTSError
from backend.utils.logger import get_logger

logger = get_logger("jarvis.tts.xtts")

_XTTS_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"


class XTTTS:
    """XTTS v2 speech synthesiser with voice cloning and latent caching.

    Args:
        language:        BCP-47 language code (e.g. ``"es"``).
        speaker:         Built-in speaker name (ignored when reference_wav is set).
        speed:           Speaking rate multiplier.
        device:          ``"cuda"`` | ``"cpu"`` | ``None`` (auto-detect).
        reference_wav:   Path to reference WAV file for voice cloning.
    """

    def __init__(
        self,
        language: str = "es",
        speaker: str = "Tammie Ema",
        speed: float = 1.0,
        device: Optional[str] = None,
        reference_wav: Optional[str] = None,
    ) -> None:
        self._language      = language
        self._speaker       = speaker
        self._speed         = speed
        self._device        = device
        self._reference_wav = reference_wav   # path to cloning WAV
        self._tts           = None
        self._available     = False
        self._cached_latents: Optional[Tuple] = None   # (gpt_cond_latent, speaker_embedding)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Download (first run ~1.8 GB) and load XTTS v2 model."""
        try:
            import os as _os
            import torch
            from TTS.tts.configs.xtts_config import XttsConfig
            from TTS.tts.models.xtts import Xtts
            from TTS.utils.manage import ModelManager

            _os.environ.setdefault("COQUI_TOS_AGREED", "1")

            dev = self._device or ("cuda" if torch.cuda.is_available() else "cpu")
            logger.info(f"[JARVIS] TTS XTTS: loading {_XTTS_MODEL} on {dev}...")

            manager = ModelManager()
            model_path, config_path, _ = manager.download_model(_XTTS_MODEL)
            if config_path is None:
                config_path = _os.path.join(model_path, "config.json")

            config = XttsConfig()
            config.load_json(config_path)
            self._tts = Xtts.init_from_config(config)
            self._tts.load_checkpoint(config, checkpoint_dir=model_path, eval=True)
            self._tts.to(dev)
            self._available = True
            logger.info(f"[JARVIS] TTS XTTS: ready on {dev}")

            # Pre-compute latents if reference WAV already configured
            if self._reference_wav and Path(self._reference_wav).is_file():
                self._precompute_latents()

        except ImportError as exc:
            logger.warning(f"[JARVIS] TTS XTTS: TTS package not available ({exc})")
        except Exception as exc:
            logger.warning(f"[JARVIS] TTS XTTS: load failed — {exc}")

    def unload(self) -> None:
        """Release model and cached latents from memory."""
        self._tts            = None
        self._available      = False
        self._cached_latents = None
        logger.info("[JARVIS] TTS XTTS: unloaded")

    @property
    def available(self) -> bool:
        return self._available

    # ── Voice reference ───────────────────────────────────────────────────────

    def set_reference(self, wav_path: str) -> None:
        """Set a new reference WAV for voice cloning and clear the latent cache.

        Args:
            wav_path: Absolute path to a WAV file (≥15s recommended).
        """
        self._reference_wav  = wav_path
        self._cached_latents = None   # force recompute on next synthesis
        logger.info(f"[JARVIS] TTS XTTS: reference voice set to {wav_path}")
        if self._available:
            self._precompute_latents()

    def _precompute_latents(self) -> None:
        """Pre-compute and cache conditioning latents from the reference WAV."""
        if not self._available or self._tts is None:
            return
        if not self._reference_wav or not Path(self._reference_wav).is_file():
            logger.warning(f"[JARVIS] TTS XTTS: reference WAV not found: {self._reference_wav}")
            return
        try:
            gpt_cond_latent, speaker_embedding = self._tts.get_conditioning_latents(
                audio_path=[self._reference_wav]
            )
            self._cached_latents = (gpt_cond_latent, speaker_embedding)
            logger.info("[JARVIS] TTS XTTS: conditioning latents cached from reference WAV")
        except Exception as exc:
            logger.warning(f"[JARVIS] TTS XTTS: latent precompute failed ({exc})")
            self._cached_latents = None

    # ── Synthesis ─────────────────────────────────────────────────────────────

    def synthesise(self, text: str) -> bytes:
        """Synthesise *text* and return WAV bytes (24 kHz, mono, int16).

        Uses cached conditioning latents when available (fast path).
        Falls back to built-in speaker when no reference WAV is set.

        Raises:
            TTSError: If synthesis fails or the model is not loaded.
        """
        if not self._available or self._tts is None:
            raise TTSError("[JARVIS] XTTS: model not loaded")

        try:
            # Use cached latents (fast) or compute on demand
            if self._cached_latents is not None:
                gpt_cond_latent, speaker_embedding = self._cached_latents
            elif self._reference_wav and Path(self._reference_wav).is_file():
                self._precompute_latents()
                if self._cached_latents:
                    gpt_cond_latent, speaker_embedding = self._cached_latents
                else:
                    gpt_cond_latent, speaker_embedding = self._tts.get_conditioning_latents(audio_path=[])
            else:
                gpt_cond_latent, speaker_embedding = self._tts.get_conditioning_latents(audio_path=[])

            out = self._tts.inference(
                text=text,
                language=self._language,
                gpt_cond_latent=gpt_cond_latent,
                speaker_embedding=speaker_embedding,
                speed=self._speed,
            )

            audio = out["wav"]
            if hasattr(audio, "cpu"):
                audio = audio.cpu().numpy()
            audio = np.clip(audio, -1.0, 1.0)
            pcm   = (audio * 32767).astype(np.int16)

            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(pcm.tobytes())

            wav_bytes = buf.getvalue()
            logger.info(f"[JARVIS] TTS XTTS: {len(wav_bytes)} bytes synthesised")
            return wav_bytes

        except TTSError:
            raise
        except Exception as exc:
            raise TTSError(f"[JARVIS] XTTS synthesis failed: {exc}") from exc
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tts.py::test_xtts_set_reference_stores_path tests/test_tts.py::test_xtts_unload_clears_model -v
```

Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/modules/tts/xtts_tts.py tests/test_tts.py
git commit -m "feat(tts): add voice cloning latent caching and set_reference() to XTTS"
```

---

## Task 7: CyrusEngine Integration

**Files:**
- Modify: `backend/core/cyrus_engine.py`

This task wires all new modules into the engine:
1. Add `Denoiser` — applied after `record_utterance()`, before ASR
2. Replace `SpeakerProfile` with `SpeakerIntelligence` — role-based response
3. Add enrollment commands for owner/guest
4. Add TTS reference recording command
5. Wire XTTS `reference_wav` from config

- [ ] **Step 1: Replace SpeakerProfile import with SpeakerIntelligence**

In `cyrus_engine.py`, find and replace:

```python
from backend.modules.audio.speaker_profile import SpeakerProfile
```

with:

```python
from backend.modules.audio.denoiser import Denoiser
from backend.modules.audio.speaker_intelligence import SpeakerIntelligence, SpeakerRole
```

- [ ] **Step 2: Add Denoiser and SpeakerIntelligence to `__init__`**

After the `# ── Audio ──` section in `__init__`, add a denoiser init:

```python
        # ── Denoiser ───────────────────────────────────────────────────────
        self._denoiser = Denoiser(
            sample_rate=ai_cfg.sample_rate,
            prop_decrease=0.75,
        )
```

Replace the voice profile loading section (at bottom of `__init__`, just before `self._audio_lock`):

```python
        # ── Speaker Intelligence ───────────────────────────────────────────
        spk_cfg = self._cfg.speaker
        self._speaker_intel = SpeakerIntelligence(
            data_dir=str(self._cfg.project_root / spk_cfg.data_dir),
            model_dir=str(self._cfg.project_root / spk_cfg.model_dir),
            threshold=spk_cfg.threshold,
            adaptive_lr=spk_cfg.adaptive_lr,
            sample_rate=ai_cfg.sample_rate,
        )
```

- [ ] **Step 3: Wire XTTS reference_wav from config**

In `__init__`, find where `self._xtts = XTTTS(...)` is constructed and update it:

```python
        xtts_cfg = getattr(tts_local_cfg, "xtts", None)
        _xtts_ref = None
        if xtts_cfg:
            _ref_str = getattr(xtts_cfg, "reference_voice", None)
            if _ref_str:
                _ref_path = self._cfg.project_root / _ref_str
                _xtts_ref = str(_ref_path) if _ref_path.is_file() else None
        self._xtts = XTTTS(
            language=getattr(xtts_cfg, "language", "es") if xtts_cfg else "es",
            speaker=getattr(xtts_cfg, "speaker", "Tammie Ema") if xtts_cfg else "Tammie Ema",
            speed=tts_local_cfg.speed,
            reference_wav=_xtts_ref,
        )
```

- [ ] **Step 4: Load SpeakerIntelligence in `_init_models()`**

In `_init_models()`, replace the voice profile loading block:

```python
        # ── Voice profile (speaker verification for barge-in) ─────────────
        profile_path = self._cfg.project_root / "config" / "voice_profile.npy"
        if profile_path.exists():
            try:
                profile = SpeakerProfile.load(profile_path, sample_rate=self._cfg.audio.input.sample_rate)
                self._audio_in.set_voice_profile(profile)
            except Exception as exc:
                logger.warning(f"[JARVIS] Could not load voice profile: {exc}")
        else:
            logger.info("[JARVIS] No voice profile found — barge-in accepts any voice (run enrollment to set up)")
```

with:

```python
        # ── Speaker Intelligence (ECAPA-TDNN) ─────────────────────────────
        logger.info("[JARVIS] Loading speaker intelligence model...")
        await loop.run_in_executor(None, self._speaker_intel.load)
        enrolled = self._speaker_intel.list_speakers()
        if enrolled:
            logger.info(f"[JARVIS] Speaker profiles loaded: {[s['id'] for s in enrolled]}")
        else:
            logger.info("[JARVIS] No speaker profiles enrolled — all voices accepted as UNKNOWN")
```

- [ ] **Step 5: Apply Denoiser and SpeakerIntelligence in `_process_one_turn()`**

Find the PCM length gate in `_process_one_turn()`:

```python
        if not pcm:
            return
```

After this, add the denoiser call:

```python
        if not pcm:
            return

        # Denoise PCM before further processing
        pcm = self._denoiser.process(pcm)
```

Find and replace the speaker gate section:

```python
        # Speaker gate — discard if voice doesn't match enrolled profile
        if not self._audio_in.verify_speaker(pcm):
            logger.debug("[JARVIS] Speaker gate: voice mismatch — discarding utterance")
            await self._state.set_status(SystemStatus.LISTENING)
            await asyncio.sleep(0.05)
            return
```

with:

```python
        # Speaker Intelligence — identify who is speaking
        speaker_result = await asyncio.get_event_loop().run_in_executor(
            None, self._speaker_intel.identify, pcm
        )
        logger.debug(f"[JARVIS] Speaker: {speaker_result.speaker_id} ({speaker_result.role.value}) conf={speaker_result.confidence:.2f}")

        # UNKNOWN speakers can only ask general questions — flag for role-based response
        _speaker_role = speaker_result.role
        _speaker_id   = speaker_result.speaker_id
```

Then, just before LLM inference (step 4, after the conversation mode section), add the role-based routing:

```python
        # Role-based routing
        if _speaker_role == SpeakerRole.UNKNOWN and self._speaker_intel.list_speakers():
            # Profiles are enrolled but this voice doesn't match anyone
            clean_input = (
                f"[SYSTEM: Voz no reconocida. Pregúntale quién es y explícale que solo el propietario "
                f"puede dar comandos al sistema. Sé amable pero firme.]"
            )
            await self._bus.emit("debug", {"text": "⚠ Voz desconocida detectada", "level": "warn"})
        elif _speaker_role == SpeakerRole.GUEST:
            # Guest context: prepend note to LLM
            clean_input = f"[INVITADO: {_speaker_id}] {clean_input}"
            await self._bus.emit("debug", {"text": f"👤 Invitado: {_speaker_id}", "level": "info"})
```

- [ ] **Step 6: Add enrollment commands for owner/guest**

In `_on_frontend_command()`, update the `start_enrollment` handler and add new ones:

Replace:
```python
        elif cmd == "start_enrollment":
            if not self._enrollment_active:
                samples = int(payload.get("samples", 5))
                asyncio.create_task(self._run_enrollment(samples=samples))
```

with:

```python
        elif cmd == "start_enrollment":
            # Legacy owner enrollment
            if not self._enrollment_active:
                samples = int(payload.get("samples", 5))
                asyncio.create_task(self._run_enrollment(samples=samples))

        elif cmd == "start_owner_enrollment":
            if not self._enrollment_active:
                samples = int(payload.get("samples", 8))
                asyncio.create_task(self._run_neural_enrollment(SpeakerRole.OWNER, "owner", samples))

        elif cmd == "start_guest_enrollment":
            if not self._enrollment_active:
                name    = str(payload.get("name", "guest")).strip().lower()
                samples = int(payload.get("samples", 5))
                asyncio.create_task(self._run_neural_enrollment(SpeakerRole.GUEST, name, samples))

        elif cmd == "remove_speaker":
            sid = str(payload.get("speaker_id", "")).strip()
            if sid:
                self._speaker_intel.remove_speaker(sid)
                speakers = self._speaker_intel.list_speakers()
                await self._bus.emit("speaker_profiles", {"speakers": speakers})
                await self._bus.emit("debug", {"text": f"✗ Perfil de voz eliminado: {sid}", "level": "warn"})

        elif cmd == "list_speakers":
            speakers = self._speaker_intel.list_speakers()
            await self._bus.emit("speaker_profiles", {"speakers": speakers})

        elif cmd == "record_tts_reference":
            if not self._enrollment_active:
                asyncio.create_task(self._record_tts_reference())
```

- [ ] **Step 7: Add `_run_neural_enrollment()` method**

Add this method to `JARVISEngine` after `_run_enrollment()`:

```python
    async def _run_neural_enrollment(self, role: "SpeakerRole", name: str, samples: int = 5) -> None:
        """Record samples and enroll speaker with ECAPA-TDNN."""
        self._enrollment_active = True
        self._audio_in.request_stop()
        await asyncio.sleep(0.5)

        role_str = "propietario" if role == SpeakerRole.OWNER else f"invitado '{name}'"
        intro = f"Enrollamiento neural para {role_str}. Voy a pedirte que hables {samples} veces. Habla con naturalidad."

        await self._bus.emit("enrollment", {"step": "start", "total": samples, "role": role.value, "name": name})
        await self._bus.emit("status", {"state": "speaking"})
        await self._bus.emit("response", {"text": intro, "language": "es"})
        async with self._audio_lock:
            try:
                ab, mime = await self._tts.synthesise(intro)
                if ab:
                    await self._audio_out.play_wav(ab) if mime == "audio/wav" else await self._play_mp3(ab)
            except Exception:
                pass

        pcm_samples: list[bytes] = []
        for i in range(1, samples + 1):
            await self._bus.emit("enrollment", {"step": "prompt", "sample": i, "total": samples})
            async with self._audio_lock:
                try:
                    ab, mime = await self._tts.synthesise(f"Muestra {i}.")
                    if ab:
                        await self._audio_out.play_wav(ab) if mime == "audio/wav" else await self._play_mp3(ab)
                except Exception:
                    pass
            await asyncio.sleep(0.3)
            try:
                pcm = await self._audio_in.record_utterance()
                if pcm:
                    pcm_samples.append(pcm)
                await self._bus.emit("enrollment", {"step": "result", "sample": i, "heard": f"Muestra {i} {'OK' if pcm else '(silencio)'}"})
            except Exception as exc:
                logger.warning(f"[JARVIS] Neural enrollment recording failed: {exc}")

        if pcm_samples:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self._speaker_intel.enroll(role, name, pcm_samples),
                )
                speakers = self._speaker_intel.list_speakers()
                await self._bus.emit("speaker_profiles", {"speakers": speakers})
                summary = f"Perfil de voz registrado para {role_str} con {len(pcm_samples)} muestras."
                await self._bus.emit("debug", {"text": f"✓ {summary}", "level": "ok"})
            except Exception as exc:
                summary = f"No se pudo registrar el perfil: {exc}"
                logger.warning(f"[JARVIS] Neural enrollment failed: {exc}")
        else:
            summary = "No se detectó audio. Intenta en un ambiente más silencioso."

        await self._bus.emit("enrollment", {"step": "done", "added": [name] if pcm_samples else []})
        await self._bus.emit("status", {"state": "speaking"})
        async with self._audio_lock:
            try:
                ab, mime = await self._tts.synthesise(summary)
                if ab:
                    await self._audio_out.play_wav(ab) if mime == "audio/wav" else await self._play_mp3(ab)
            except Exception:
                pass

        self._enrollment_active = False
        await self._bus.emit("status", {"state": "idle"})
        await self._bus.emit("enrollment", {"step": "idle"})
```

- [ ] **Step 8: Add `_record_tts_reference()` method**

Add after `_run_neural_enrollment()`:

```python
    async def _record_tts_reference(self) -> None:
        """Record 20s of voice as XTTS cloning reference."""
        self._enrollment_active = True
        self._audio_in.request_stop()
        await asyncio.sleep(0.3)

        ref_dir  = self._cfg.project_root / "data" / "tts"
        ref_dir.mkdir(parents=True, exist_ok=True)
        ref_path = ref_dir / "reference_voice.wav"

        intro = "Voy a grabar tu voz como referencia para la síntesis. Habla durante 20 segundos sobre cualquier tema."
        await self._bus.emit("status", {"state": "speaking"})
        async with self._audio_lock:
            try:
                ab, mime = await self._tts.synthesise(intro)
                if ab:
                    await self._audio_out.play_wav(ab) if mime == "audio/wav" else await self._play_mp3(ab)
            except Exception:
                pass

        await asyncio.sleep(0.5)
        await self._bus.emit("debug", {"text": "🎙 Grabando referencia TTS (20s)...", "level": "info"})

        pcm_chunks: list[bytes] = []
        target_bytes = 16000 * 2 * 20  # 20 seconds at 16kHz int16
        collected = 0
        while collected < target_bytes:
            try:
                pcm = await self._audio_in.record_utterance()
                if pcm:
                    pcm_chunks.append(pcm)
                    collected += len(pcm)
            except Exception:
                break

        if pcm_chunks:
            import wave as _wave
            combined = b"".join(pcm_chunks)
            with _wave.open(str(ref_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(combined)
            self._xtts.set_reference(str(ref_path))
            await self._bus.emit("debug", {"text": f"✓ Referencia TTS guardada: {ref_path.name}", "level": "ok"})
            summary = "Referencia de voz guardada. La síntesis de voz ahora usará tu voz como modelo."
        else:
            summary = "No se detectó audio para la referencia."

        await self._bus.emit("status", {"state": "speaking"})
        async with self._audio_lock:
            try:
                ab, mime = await self._tts.synthesise(summary)
                if ab:
                    await self._audio_out.play_wav(ab) if mime == "audio/wav" else await self._play_mp3(ab)
            except Exception:
                pass

        self._enrollment_active = False
        await self._bus.emit("status", {"state": "idle"})
```

- [ ] **Step 9: Verify the engine starts without errors**

```bash
python -c "from backend.core.cyrus_engine import JARVISEngine; e = JARVISEngine(); print('Engine init OK')"
```

Expected: `Engine init OK`

- [ ] **Step 10: Commit**

```bash
git add backend/core/cyrus_engine.py
git commit -m "feat(engine): wire Denoiser, SpeakerIntelligence, and role-based response into pipeline"
```

---

## Task 8: Frontend Enrollment UI

**Files:**
- Modify: `frontend/src/views/ControlView.tsx`

Add a "Perfiles de Voz" section to the Control view that allows:
- Enrollar propietario (8 samples)
- Enrollar invitado (name input + 5 samples)
- Grabar referencia TTS
- Ver y eliminar perfiles

- [ ] **Step 1: Add `speakerProfiles` to the Zustand store**

In `frontend/src/store/useJARVISStore.ts`, add to the store interface:

```typescript
  speakerProfiles: { id: string; role: string }[]
  setSpeakerProfiles: (profiles: { id: string; role: string }[]) => void
```

And add the initial state and action:

```typescript
  speakerProfiles: [],
  setSpeakerProfiles: (profiles) => set({ speakerProfiles: profiles }),
```

- [ ] **Step 2: Handle `speaker_profiles` WebSocket event in the WS client**

In the WebSocket client file (wherever other events like `wake_words` are handled), add:

```typescript
case 'speaker_profiles':
  useJARVISStore.getState().setSpeakerProfiles(data.speakers ?? [])
  break
```

- [ ] **Step 3: Add `VoiceProfilesSection` component to `ControlView.tsx`**

Find the existing enrollment section in `ControlView.tsx` and add this new component before the closing of the page, alongside the existing enrollment UI:

```tsx
function VoiceProfilesSection({ sendCommand }: { sendCommand: (cmd: string, payload?: object) => void }) {
  const speakerProfiles = useJARVISStore(s => s.speakerProfiles)
  const enrollmentStep  = useJARVISStore(s => s.enrollmentStep)
  const [guestName, setGuestName] = useState('')
  const busy = enrollmentStep !== 'idle'

  return (
    <div className="border border-cyan-900/30 rounded p-4 space-y-3">
      <p className="font-mono text-xs tracking-widest text-cyan-400/60">PERFILES DE VOZ</p>

      {/* Enrolled speakers list */}
      {speakerProfiles.length > 0 && (
        <div className="space-y-1">
          {speakerProfiles.map(sp => (
            <div key={sp.id} className="flex items-center justify-between font-mono text-xs">
              <span style={{ color: sp.role === 'owner' ? '#00ff88' : '#00d4ff' }}>
                {sp.role === 'owner' ? '★' : '◆'} {sp.id} ({sp.role})
              </span>
              <button
                onClick={() => sendCommand('remove_speaker', { speaker_id: sp.id })}
                className="text-red-400/60 hover:text-red-400 px-2"
                style={{ fontSize: 10, background: 'none', border: 'none', cursor: 'pointer' }}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      {speakerProfiles.length === 0 && (
        <p className="font-mono text-xs text-cyan-900/60">Sin perfiles enrollados</p>
      )}

      {/* Enroll owner */}
      <button
        disabled={busy}
        onClick={() => sendCommand('start_owner_enrollment', { samples: 8 })}
        className="w-full font-mono text-xs border border-green-500/40 text-green-400/80 hover:text-green-400 rounded px-3 py-2 disabled:opacity-40"
        style={{ background: 'none', cursor: busy ? 'not-allowed' : 'pointer' }}
      >
        ENROLLAR PROPIETARIO (8 muestras)
      </button>

      {/* Enroll guest */}
      <div className="flex gap-2">
        <input
          value={guestName}
          onChange={e => setGuestName(e.target.value)}
          placeholder="nombre invitado"
          className="flex-1 font-mono text-xs bg-transparent border border-cyan-900/40 rounded px-2 py-1 text-cyan-300/70 outline-none"
          style={{ fontSize: 10 }}
        />
        <button
          disabled={busy || !guestName.trim()}
          onClick={() => sendCommand('start_guest_enrollment', { name: guestName.trim(), samples: 5 })}
          className="font-mono text-xs border border-cyan-500/40 text-cyan-400/80 hover:text-cyan-400 rounded px-3 py-1 disabled:opacity-40"
          style={{ background: 'none', cursor: busy || !guestName.trim() ? 'not-allowed' : 'pointer', fontSize: 10 }}
        >
          ENROLLAR
        </button>
      </div>

      {/* Record TTS reference */}
      <button
        disabled={busy}
        onClick={() => sendCommand('record_tts_reference')}
        className="w-full font-mono text-xs border border-orange-500/40 text-orange-400/80 hover:text-orange-400 rounded px-3 py-2 disabled:opacity-40"
        style={{ background: 'none', cursor: busy ? 'not-allowed' : 'pointer' }}
      >
        GRABAR VOZ DE REFERENCIA TTS (20s)
      </button>
    </div>
  )
}
```

- [ ] **Step 4: Mount `VoiceProfilesSection` in the Control view**

In `ControlView.tsx`, find where the enrollment section is rendered and add `VoiceProfilesSection` alongside it:

```tsx
<VoiceProfilesSection sendCommand={sendCommand} />
```

Also add a `useEffect` to request current speaker profiles on mount:

```tsx
useEffect(() => {
  if (wsConnected) {
    sendCommand('list_speakers')
  }
}, [wsConnected])
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/ControlView.tsx frontend/src/store/useJARVISStore.ts
git commit -m "feat(ui): add voice profile enrollment UI with owner/guest/TTS reference recording"
```

---

## Final Verification

- [ ] **Start the backend and confirm startup logs**

```bash
python -m backend.core.cyrus_engine
```

Expected log lines:
```
[JARVIS] ASR: loading whisper/small on cpu (int8)...
[JARVIS] SpeakerIntelligence: loading ECAPA-TDNN...
[JARVIS] SpeakerIntelligence: ECAPA-TDNN ready
[JARVIS] All models initialised
```

- [ ] **Run full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: All existing tests pass + new tests pass

- [ ] **Final commit**

```bash
git add -A
git commit -m "feat(voice): Voice Intelligence v2 complete — denoiser, ECAPA-TDNN speaker recognition, XTTS voice cloning"
```
