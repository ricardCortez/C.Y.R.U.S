"""
C.Y.R.U.S — Faster-Whisper ASR module.

Loads the Whisper TINY model on CUDA (or CPU as fallback) and transcribes
raw PCM utterances.  The model is lazy-loaded on first use.
"""

from __future__ import annotations

import io
import wave
from pathlib import Path
from typing import Optional, Tuple

from backend.utils.exceptions import ASRError, ASRModelNotLoadedError
from backend.utils.logger import get_logger

logger = get_logger("cyrus.asr")

try:
    from faster_whisper import WhisperModel
    _WHISPER_AVAILABLE = True
except ImportError:
    _WHISPER_AVAILABLE = False
    logger.warning("[C.Y.R.U.S] faster-whisper not installed; ASR unavailable")


class WhisperASR:
    """Faster-Whisper transcription wrapper.

    Args:
        model_size: Whisper model variant (``"tiny"`` | ``"base"`` | ``"small"``).
        device: ``"cuda"`` or ``"cpu"``.
        compute_type: ``"float16"`` (GPU) or ``"int8"`` (CPU).
        language: Force a language code (e.g. ``"es"``); ``None`` = auto-detect.
        beam_size: Beam search width (higher = more accurate, slower).
        vad_filter: Use built-in VAD to suppress non-speech segments.
    """

    def __init__(
        self,
        model_size: str = "tiny",
        device: str = "cuda",
        compute_type: str = "float16",
        language: Optional[str] = None,
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._language = language
        self._beam_size = beam_size
        self._vad_filter = vad_filter
        self._model: Optional["WhisperModel"] = None  # lazy load

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Download (on first run) and load the Whisper model into memory.

        Falls back to CPU with int8 if CUDA is unavailable.

        Raises:
            ASRError: If the model cannot be loaded.
        """
        if not _WHISPER_AVAILABLE:
            raise ASRError("[C.Y.R.U.S] faster-whisper is not installed")

        device = self._device
        compute_type = self._compute_type

        try:
            logger.info(
                f"[C.Y.R.U.S] ASR: loading whisper/{self._model_size} on {device} ({compute_type})…"
            )
            self._model = WhisperModel(
                self._model_size,
                device=device,
                compute_type=compute_type,
            )
            logger.info("[C.Y.R.U.S] ASR: model ready")
        except Exception as exc:
            if device == "cuda":
                logger.warning(
                    f"[C.Y.R.U.S] ASR: CUDA load failed ({exc}); retrying on CPU with int8"
                )
                try:
                    self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
                    logger.info("[C.Y.R.U.S] ASR: model ready (CPU fallback)")
                except Exception as exc2:
                    raise ASRError(f"[C.Y.R.U.S] ASR: model load failed: {exc2}") from exc2
            else:
                raise ASRError(f"[C.Y.R.U.S] ASR: model load failed: {exc}") from exc

    def unload(self) -> None:
        """Release the model from memory."""
        self._model = None
        logger.info("[C.Y.R.U.S] ASR: model unloaded")

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> Tuple[str, str]:
        """Transcribe raw PCM bytes.

        Args:
            pcm_bytes: Raw int16 mono PCM.
            sample_rate: PCM sample rate.

        Returns:
            Tuple of ``(transcript_text, detected_language_code)``.

        Raises:
            ASRModelNotLoadedError: If :meth:`load` has not been called.
            ASRError: On transcription failure.
        """
        if self._model is None:
            raise ASRModelNotLoadedError("[C.Y.R.U.S] ASR: call load() before transcribe()")

        if not pcm_bytes:
            logger.warning("[C.Y.R.U.S] ASR: empty audio; skipping transcription")
            return "", "en"

        # faster-whisper can accept a file path or a numpy array.
        # We wrap PCM in a WAV buffer and pass the file-like object.
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        wav_buf.seek(0)

        try:
            segments, info = self._model.transcribe(
                wav_buf,
                language=self._language,
                beam_size=self._beam_size,
                vad_filter=self._vad_filter,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            lang = info.language if info.language else "en"
            logger.info(f"[C.Y.R.U.S] ASR: transcript='{text}' lang={lang}")
            return text, lang
        except Exception as exc:
            raise ASRError(f"[C.Y.R.U.S] ASR: transcription failed: {exc}") from exc
