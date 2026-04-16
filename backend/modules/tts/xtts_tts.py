"""
C.Y.R.U.S — XTTS v2 TTS backend (Coqui AI).

Offline neural TTS with voice cloning support.  Requires the ``TTS`` package
(``pip install TTS``).  Downloads the model on first use (~1.8 GB).

Speakers bundled with xtts_v2 for Spanish:
    Requires a reference WAV file for voice cloning, OR one of the built-in
    speaker names (e.g. "Claribel Dervla", "Sofia Hellen", "Tammie Ema").

Usage::

    tts = XTTTS(language="es", speaker="Tammie Ema")
    tts.load()
    wav_bytes = tts.synthesise("Hola, soy CYRUS.")
"""

from __future__ import annotations

import io
import wave
from pathlib import Path
from typing import Optional

from backend.utils.exceptions import TTSError
from backend.utils.logger import get_logger

logger = get_logger("cyrus.tts.xtts")

_XTTS_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"


class XTTTS:
    """XTTS v2 speech synthesiser.

    Args:
        language:         BCP-47 language code (e.g. ``"es"``).
        speaker:          Built-in speaker name OR path to a reference WAV file
                          for voice cloning.  Defaults to ``"Tammie Ema"``.
        speed:            Speaking rate multiplier (1.0 = normal).
        device:           PyTorch device (``"cuda"`` | ``"cpu"``).  Auto-detected
                          when ``None``.
    """

    def __init__(
        self,
        language: str = "es",
        speaker: str = "Tammie Ema",
        speed: float = 1.0,
        device: Optional[str] = None,
    ) -> None:
        self._language = language
        self._speaker  = speaker
        self._speed    = speed
        self._device   = device
        self._tts = None   # TTS instance — loaded lazily
        self._available = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Download (first time) and load the XTTS v2 model."""
        try:
            from TTS.api import TTS as CoquiTTS
            import torch

            dev = self._device or ("cuda" if torch.cuda.is_available() else "cpu")
            logger.info(f"[C.Y.R.U.S] TTS XTTS: loading {_XTTS_MODEL} on {dev}…")
            self._tts = CoquiTTS(_XTTS_MODEL).to(dev)
            self._available = True
            logger.info("[C.Y.R.U.S] TTS XTTS: ready")
        except ImportError:
            logger.warning("[C.Y.R.U.S] TTS XTTS: TTS package not installed — run: pip install TTS")
        except Exception as exc:
            logger.warning(f"[C.Y.R.U.S] TTS XTTS: load failed — {exc}")

    @property
    def available(self) -> bool:
        return self._available

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def synthesise(self, text: str) -> bytes:
        """Synthesise *text* and return WAV bytes.

        Args:
            text: Clean speech text (no markdown).

        Returns:
            In-memory WAV file bytes (16-bit PCM, 24 kHz, mono).

        Raises:
            TTSError: If synthesis fails or the model is not loaded.
        """
        if not self._available or self._tts is None:
            raise TTSError("[C.Y.R.U.S] XTTS: model not loaded")

        try:
            # Determine whether _speaker is a file path or a name
            speaker_wav: Optional[str] = None
            speaker_name: Optional[str] = None

            sp = str(self._speaker)
            if Path(sp).is_file():
                speaker_wav = sp
            else:
                speaker_name = sp

            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                if speaker_wav:
                    self._tts.tts_to_file(
                        text=text,
                        speaker_wav=speaker_wav,
                        language=self._language,
                        file_path=tmp_path,
                        speed=self._speed,
                    )
                else:
                    self._tts.tts_to_file(
                        text=text,
                        speaker=speaker_name,
                        language=self._language,
                        file_path=tmp_path,
                        speed=self._speed,
                    )
                with open(tmp_path, "rb") as f:
                    wav_bytes = f.read()
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            logger.info(f"[C.Y.R.U.S] TTS XTTS: {len(wav_bytes)} bytes synthesised")
            return wav_bytes

        except TTSError:
            raise
        except Exception as exc:
            raise TTSError(f"[C.Y.R.U.S] XTTS synthesis failed: {exc}") from exc
