"""
JARVIS — Faster-Whisper ASR module.

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
    logger.warning("[JARVIS] faster-whisper not installed; ASR unavailable")


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
        initial_prompt: Optional[str] = None,
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._language = language
        self._beam_size = beam_size
        self._vad_filter = vad_filter
        self._initial_prompt = initial_prompt or "Habla en español. JARVIS es un asistente de IA personal."
        self._model: Optional["WhisperModel"] = None  # lazy load

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # CUDA + cuDNN probe
    # ------------------------------------------------------------------

    @staticmethod
    def _cuda_usable() -> bool:
        """Return True when ctranslate2 can use CUDA.

        ctranslate2 4.x bundles cudnn64_8.dll inside its own package directory.
        We add that directory to the DLL search path before the check so the
        older probe for the system-level cudnn_ops_infer64_8.dll is no longer
        needed.
        """
        try:
            import ctranslate2 as _ct2, os
            ct2_dir = os.path.dirname(_ct2.__file__)
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(ct2_dir)
            return _ct2.get_cuda_device_count() > 0
        except Exception:
            return False

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

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Download (on first run) and load the Whisper model into memory.

        Auto-selects CPU when the configured device is ``cuda`` but cuDNN 8.x
        is not present — avoids a silent failure during first inference.

        Raises:
            ASRError: If the model cannot be loaded.
        """
        if not _WHISPER_AVAILABLE:
            raise ASRError("[JARVIS] faster-whisper is not installed")

        device       = self._device
        compute_type = self._compute_type
        model_size   = self._model_size

        # "auto" triggers hardware-aware selection — overrides config values
        if model_size == "auto":
            model_size, device, compute_type = self._select_model_and_device()
        elif device == "cuda" and not self._cuda_usable():
            logger.warning(
                "[JARVIS] ASR: CUDA requested but cuDNN not available — "
                "falling back to CPU/int8 (install cuDNN to enable GPU)"
            )
            model_size, device, compute_type = self._select_model_and_device(force_cpu=True)
            self._device       = device
            self._compute_type = compute_type

        try:
            logger.info(
                f"[JARVIS] ASR: loading whisper/{model_size} on {device} ({compute_type})..."
            )
            self._model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
            )
            logger.info("[JARVIS] ASR: model ready")
        except Exception as exc:
            if device == "cuda":
                logger.warning(
                    f"[JARVIS] ASR: CUDA load failed ({exc}); retrying on CPU with int8"
                )
                try:
                    self._model        = WhisperModel(model_size, device="cpu", compute_type="int8")
                    self._device       = "cpu"
                    self._compute_type = "int8"
                    logger.info("[JARVIS] ASR: model ready (CPU fallback)")
                except Exception as exc2:
                    raise ASRError(f"[JARVIS] ASR: model load failed: {exc2}") from exc2
            else:
                raise ASRError(f"[JARVIS] ASR: model load failed: {exc}") from exc

    def unload(self) -> None:
        """Release the model from memory."""
        self._model = None
        logger.info("[JARVIS] ASR: model unloaded")

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
            raise ASRModelNotLoadedError("[JARVIS] ASR: call load() before transcribe()")

        if not pcm_bytes:
            logger.warning("[JARVIS] ASR: empty audio; skipping transcription")
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
                initial_prompt=self._initial_prompt,
            )
            try:
                text = " ".join(seg.text.strip() for seg in segments).strip()
            except Exception as vad_exc:
                # Silero VAD model download may fail on offline machines; retry without VAD
                logger.warning(f"[JARVIS] ASR: segment iteration failed ({vad_exc}); retrying vad_filter=False")
                wav_buf.seek(0)
                segments2, info = self._model.transcribe(
                    wav_buf,
                    language=self._language,
                    beam_size=self._beam_size,
                    vad_filter=False,
                    initial_prompt=self._initial_prompt,
                )
                text = " ".join(seg.text.strip() for seg in segments2).strip()
                self._vad_filter = False  # disable permanently to avoid repeated failures
            lang = info.language if info.language else "es"
            logger.info(f"[JARVIS] ASR: transcript='{text}' lang={lang}")
            return text, lang
        except Exception as exc:
            # CUDA inference may fail even if model loaded — fallback to CPU
            if self._device != "cpu":
                logger.warning(
                    f"[JARVIS] ASR: CUDA transcription failed ({exc}); reloading on CPU"
                )
                try:
                    self._model = WhisperModel(
                        self._model_size, device="cpu", compute_type="int8"
                    )
                    self._device = "cpu"
                    self._compute_type = "int8"
                    logger.info("[JARVIS] ASR: CPU reload OK — retrying transcription")
                    wav_buf.seek(0)
                    segments, info = self._model.transcribe(
                        wav_buf,
                        language=self._language,
                        beam_size=self._beam_size,
                        vad_filter=self._vad_filter,
                        initial_prompt=self._initial_prompt,
                    )
                    text = " ".join(seg.text.strip() for seg in segments).strip()
                    lang = info.language if info.language else "es"
                    logger.info(f"[JARVIS] ASR: transcript='{text}' lang={lang}")
                    return text, lang
                except Exception as exc2:
                    raise ASRError(
                        f"[JARVIS] ASR: transcription failed on CPU too: {exc2}"
                    ) from exc2
            raise ASRError(f"[JARVIS] ASR: transcription failed: {exc}") from exc
