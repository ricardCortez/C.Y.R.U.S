"""
C.Y.R.U.S — Lightweight speaker verification.

Builds a voice fingerprint from PCM enrollment samples using a mean
power-spectral-density vector (no external ML dependencies — numpy only).
Cosine similarity against the stored fingerprint gates barge-in detection
so only the enrolled user's voice interrupts CYRUS mid-speech.

Usage::

    profile = SpeakerProfile.from_pcm_samples(pcm_list, sample_rate=16000)
    profile.save(Path("config/voice_profile.npy"))

    profile = SpeakerProfile.load(Path("config/voice_profile.npy"))
    if profile.is_match(pcm_chunk, sample_rate=16000):
        ...
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np

from backend.utils.logger import get_logger

logger = get_logger("cyrus.audio.speaker")

# Tuning
_N_FFT          = 512          # FFT size for spectral analysis
_FRAME_LEN      = 512          # ~32 ms at 16 kHz
_HOP_LEN        = 256          # 50 % overlap
_MIN_SAMPLES_S  = 0.12         # minimum utterance length to produce a fingerprint (s)
_DEFAULT_THRESH = 0.80         # cosine similarity threshold for a "match"


def _compute_fingerprint(pcm: bytes, sample_rate: int) -> Optional[np.ndarray]:
    """Return a normalised mean-PSD vector for *pcm*, or None if too short."""
    arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if len(arr) < sample_rate * _MIN_SAMPLES_S:
        return None

    # Pre-emphasis (boost high frequencies → better formant representation)
    arr = np.append(arr[0], arr[1:] - 0.97 * arr[:-1])

    # Framing + Hann window
    frames = [
        arr[i : i + _FRAME_LEN] * np.hanning(_FRAME_LEN)
        for i in range(0, len(arr) - _FRAME_LEN, _HOP_LEN)
    ]
    if not frames:
        return None

    # Mean power spectrum across all frames
    psd = np.mean(
        [np.abs(np.fft.rfft(f, n=_N_FFT)) ** 2 for f in frames],
        axis=0,
    )

    # Unit-vector normalisation for cosine comparison
    norm = np.linalg.norm(psd)
    if norm < 1e-10:
        return None
    return (psd / norm).astype(np.float32)


class SpeakerProfile:
    """Per-user voice fingerprint.

    Internally stores the *mean* of all enrollment fingerprints plus the
    individual vectors so a fresh call to :meth:`is_match` can compare
    against the centroid.

    Args:
        fingerprints: List of unit-norm PSD vectors collected during enrollment.
        sample_rate:  Sample rate used when the fingerprints were computed.
        threshold:    Cosine similarity required to declare a match.
    """

    def __init__(
        self,
        fingerprints: List[np.ndarray],
        sample_rate: int = 16000,
        threshold: float = _DEFAULT_THRESH,
    ) -> None:
        if not fingerprints:
            raise ValueError("[C.Y.R.U.S] SpeakerProfile: need at least one fingerprint")
        self._sample_rate = sample_rate
        self._threshold   = threshold
        self._centroid    = np.mean(fingerprints, axis=0).astype(np.float32)
        # Re-normalise centroid so dot-product == cosine similarity
        norm = np.linalg.norm(self._centroid)
        if norm > 1e-10:
            self._centroid /= norm

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_pcm_samples(
        cls,
        pcm_list: List[bytes],
        sample_rate: int = 16000,
        threshold: float = _DEFAULT_THRESH,
    ) -> "SpeakerProfile":
        """Build a profile from a list of raw PCM utterances.

        Args:
            pcm_list:    PCM bytes from enrollment recordings.
            sample_rate: Recording sample rate.
            threshold:   Cosine similarity threshold.

        Returns:
            A :class:`SpeakerProfile` instance.

        Raises:
            ValueError: If no usable audio was found in *pcm_list*.
        """
        fps = [_compute_fingerprint(pcm, sample_rate) for pcm in pcm_list]
        fps = [fp for fp in fps if fp is not None]
        if not fps:
            raise ValueError("[C.Y.R.U.S] SpeakerProfile: no usable audio in enrollment samples")
        logger.info(f"[C.Y.R.U.S] SpeakerProfile: built from {len(fps)} samples")
        return cls(fps, sample_rate=sample_rate, threshold=threshold)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Path) -> None:
        """Save profile centroid to a .npy file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(str(path), self._centroid)
        logger.info(f"[C.Y.R.U.S] SpeakerProfile: saved to {path}")

    @classmethod
    def load(cls, path: Path, sample_rate: int = 16000, threshold: float = _DEFAULT_THRESH) -> "SpeakerProfile":
        """Load a previously saved profile.

        Args:
            path:        Path to the .npy file.
            sample_rate: Sample rate to associate with the profile.
            threshold:   Match threshold.

        Raises:
            FileNotFoundError: If *path* does not exist.
        """
        centroid = np.load(str(path)).astype(np.float32)
        profile = cls.__new__(cls)
        profile._sample_rate = sample_rate
        profile._threshold   = threshold
        profile._centroid    = centroid
        logger.info(f"[C.Y.R.U.S] SpeakerProfile: loaded from {path}")
        return profile

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def match_score(self, pcm: bytes) -> float:
        """Return cosine similarity of *pcm* against the enrolled voice (0–1)."""
        fp = _compute_fingerprint(pcm, self._sample_rate)
        if fp is None:
            return 0.0
        score = float(np.dot(fp, self._centroid))
        return max(0.0, min(1.0, score))

    def is_match(self, pcm: bytes) -> bool:
        """Return True if *pcm* resembles the enrolled voice."""
        score = self.match_score(pcm)
        logger.debug(f"[C.Y.R.U.S] SpeakerProfile: similarity={score:.3f} threshold={self._threshold}")
        return score >= self._threshold
