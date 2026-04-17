"""
C.Y.R.U.S — Spectral noise reduction for PCM audio.

Applies stationary noise reduction (noisereduce) to int16 PCM bytes
before VAD and Whisper transcription.
"""
from __future__ import annotations

import numpy as np

from backend.utils.logger import get_logger

logger = get_logger("cyrus.audio.denoiser")

try:
    import noisereduce as nr
    _NR_AVAILABLE = True
except ImportError:
    _NR_AVAILABLE = False
    logger.warning("[C.Y.R.U.S] Denoiser: noisereduce not installed — passthrough mode")


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
            logger.debug(f"[C.Y.R.U.S] Denoiser: failed ({exc}) — passthrough")
            return pcm
