"""
C.Y.R.U.S — Neural speaker recognition with role-based access control.

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

logger = get_logger("cyrus.audio.speaker_intelligence")

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
    logger.warning("[C.Y.R.U.S] SpeakerIntelligence: speechbrain not installed — fallback to UNKNOWN")


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
            logger.warning("[C.Y.R.U.S] SpeakerIntelligence: speechbrain/torch unavailable — UNKNOWN fallback active")
            return
        try:
            logger.info("[C.Y.R.U.S] SpeakerIntelligence: loading ECAPA-TDNN...")
            self._model_dir.mkdir(parents=True, exist_ok=True)
            self._classifier = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir=str(self._model_dir),
                run_opts={"device": "cpu"},  # embedder always on CPU to save VRAM
            )
            logger.info("[C.Y.R.U.S] SpeakerIntelligence: ECAPA-TDNN ready")
        except Exception as exc:
            logger.warning(f"[C.Y.R.U.S] SpeakerIntelligence: load failed ({exc}) — UNKNOWN fallback")
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
            logger.debug(f"[C.Y.R.U.S] SpeakerIntelligence: embed error ({exc})")
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
            raise ValueError(f"[C.Y.R.U.S] SpeakerIntelligence: no usable audio for '{name}'")

        centroid = np.mean(embeddings, axis=0).astype(np.float32)
        norm = np.linalg.norm(centroid)
        if norm > 1e-8:
            centroid /= norm

        speaker_id = name.lower().strip()
        self._profiles[speaker_id] = {"role": role, "embedding": centroid}
        logger.info(f"[C.Y.R.U.S] SpeakerIntelligence: enrolled '{speaker_id}' as {role.value} ({len(embeddings)} samples)")
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
            logger.debug(f"[C.Y.R.U.S] SpeakerIntelligence: best={best_score:.3f} < {self._threshold} → UNKNOWN")
            return unknown

        profile = self._profiles[best_id]
        role    = profile["role"]
        logger.info(f"[C.Y.R.U.S] SpeakerIntelligence: '{best_id}' ({role.value}) score={best_score:.3f}")

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
            logger.info(f"[C.Y.R.U.S] SpeakerIntelligence: removed '{sid}'")

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self) -> None:
        """Persist all speaker embeddings to data_dir/*.npz."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        for sid, profile in self._profiles.items():
            path = self._data_dir / f"{sid}.npz"
            np.savez(str(path), embedding=profile["embedding"], role=profile["role"].value)
        logger.debug(f"[C.Y.R.U.S] SpeakerIntelligence: saved {len(self._profiles)} profiles")

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
                logger.info(f"[C.Y.R.U.S] SpeakerIntelligence: loaded '{sid}' ({role.value})")
            except Exception as exc:
                logger.warning(f"[C.Y.R.U.S] SpeakerIntelligence: could not load {npz_path}: {exc}")
