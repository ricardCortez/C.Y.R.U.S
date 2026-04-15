"""
C.Y.R.U.S — Kokoro TTS local synthesis.

Uses the ``kokoro`` Python package for offline British-English TTS.
The model is lazy-loaded on first use.
"""

from __future__ import annotations

import io
import wave
from typing import Optional

import numpy as np

from backend.utils.exceptions import KokoroUnavailableError, TTSError
from backend.utils.logger import get_logger

logger = get_logger("cyrus.tts.kokoro")

try:
    from kokoro import KPipeline
    _KOKORO_AVAILABLE = True
except ImportError:
    _KOKORO_AVAILABLE = False
    logger.warning("[C.Y.R.U.S] kokoro package not installed; local TTS unavailable")


class KokoroTTS:
    """Kokoro offline TTS synthesis.

    Args:
        voice: Kokoro voice ID (e.g. ``"af_sarah"``, ``"bf_emma"``).
        speed: Playback speed multiplier (0.5–2.0).
        sample_rate: Output audio sample rate.
        lang_code: Language code for the pipeline (``"a"`` = American English,
            ``"b"`` = British English).
    """

    def __init__(
        self,
        voice: str = "ef_dora",
        speed: float = 0.90,
        sample_rate: int = 24000,
        lang_code: str = "e",
    ) -> None:
        self._voice = voice
        self._speed = speed
        self._sample_rate = sample_rate
        self._lang_code = lang_code
        self._pipeline: Optional["KPipeline"] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Initialise the Kokoro pipeline (downloads model on first run).

        Raises:
            KokoroUnavailableError: If the package is not installed or load fails.
        """
        if not _KOKORO_AVAILABLE:
            raise KokoroUnavailableError("[C.Y.R.U.S] kokoro package not installed")
        try:
            logger.info(f"[C.Y.R.U.S] TTS: loading Kokoro pipeline (voice={self._voice}, lang={self._lang_code})…")
            self._pipeline = KPipeline(lang_code=self._lang_code, repo_id="hexgrad/Kokoro-82M")
            logger.info("[C.Y.R.U.S] TTS: Kokoro ready")
        except Exception as exc:
            raise KokoroUnavailableError(f"[C.Y.R.U.S] Kokoro load failed: {exc}") from exc

    def unload(self) -> None:
        """Release pipeline resources."""
        self._pipeline = None
        logger.info("[C.Y.R.U.S] TTS: Kokoro unloaded")

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def synthesise(self, text: str) -> bytes:
        """Synthesise *text* to WAV bytes.

        Args:
            text: Input text to speak.

        Returns:
            In-memory WAV file bytes (16-bit PCM, mono, ``sample_rate`` Hz).

        Raises:
            KokoroUnavailableError: If the pipeline is not loaded.
            TTSError: On synthesis failure.
        """
        if self._pipeline is None:
            raise KokoroUnavailableError("[C.Y.R.U.S] Kokoro not loaded; call load() first")
        if not text.strip():
            logger.warning("[C.Y.R.U.S] TTS: empty text; returning silence")
            return self._silence_wav(0.5)

        try:
            audio_segments = []
            generator = self._pipeline(
                text,
                voice=self._voice,
                speed=self._speed,
                split_pattern=r"\n+",
            )
            for _, _, audio in generator:
                if audio is not None:
                    audio_segments.append(audio)

            if not audio_segments:
                raise TTSError("[C.Y.R.U.S] Kokoro returned no audio segments")

            combined = np.concatenate(audio_segments)
            return self._to_wav(combined)
        except (KokoroUnavailableError, TTSError):
            raise
        except Exception as exc:
            raise TTSError(f"[C.Y.R.U.S] Kokoro synthesis error: {exc}") from exc

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _to_wav(self, audio: np.ndarray) -> bytes:
        """Convert a float32 numpy array to 16-bit WAV bytes."""
        audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._sample_rate)
            wf.writeframes(audio_int16.tobytes())
        return buf.getvalue()

    def _silence_wav(self, duration: float) -> bytes:
        """Return WAV bytes containing silence of *duration* seconds."""
        samples = np.zeros(int(self._sample_rate * duration), dtype=np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._sample_rate)
            wf.writeframes(samples.tobytes())
        return buf.getvalue()
