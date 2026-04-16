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
        """Download (first time ~1.8 GB) and load the XTTS v2 model."""
        try:
            import os as _os
            import torch
            from TTS.tts.configs.xtts_config import XttsConfig
            from TTS.tts.models.xtts import Xtts
            from TTS.utils.manage import ModelManager

            # Accept CPML non-commercial license automatically (no interactive prompt)
            _os.environ.setdefault("COQUI_TOS_AGREED", "1")

            dev = self._device or ("cuda" if torch.cuda.is_available() else "cpu")
            logger.info(f"[C.Y.R.U.S] TTS XTTS: loading {_XTTS_MODEL} on {dev}...")

            # Download model files if not cached
            manager = ModelManager()
            model_path, config_path, _ = manager.download_model(_XTTS_MODEL)

            config = XttsConfig()
            config.load_json(config_path)
            self._tts = Xtts.init_from_config(config)
            self._tts.load_checkpoint(config, checkpoint_dir=model_path, eval=True)
            self._tts.to(dev)
            self._available = True
            logger.info(f"[C.Y.R.U.S] TTS XTTS: ready on {dev}")
        except ImportError as exc:
            logger.warning(f"[C.Y.R.U.S] TTS XTTS: TTS package not available ({exc})")
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
            import io, wave, os, tempfile
            import numpy as np

            sp = str(self._speaker)
            speaker_wav: Optional[str] = sp if Path(sp).is_file() else None

            # XTTS v2 requires a reference WAV for voice cloning; use a built-in
            # speaker embedding when no reference file is given.
            if speaker_wav:
                gpt_cond_latent, speaker_embedding = self._tts.get_conditioning_latents(
                    audio_path=[speaker_wav]
                )
            else:
                # Use default speaker from config (first available)
                gpt_cond_latent, speaker_embedding = self._tts.get_conditioning_latents(
                    audio_path=[]
                )

            out = self._tts.inference(
                text=text,
                language=self._language,
                gpt_cond_latent=gpt_cond_latent,
                speaker_embedding=speaker_embedding,
                speed=self._speed,
            )

            # Convert float32 tensor -> 16-bit WAV bytes
            audio = out["wav"]
            if hasattr(audio, "cpu"):
                audio = audio.cpu().numpy()
            audio = np.clip(audio, -1.0, 1.0)
            pcm = (audio * 32767).astype(np.int16)

            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(pcm.tobytes())
            wav_bytes = buf.getvalue()

            logger.info(f"[C.Y.R.U.S] TTS XTTS: {len(wav_bytes)} bytes synthesised")
            return wav_bytes

        except TTSError:
            raise
        except Exception as exc:
            raise TTSError(f"[C.Y.R.U.S] XTTS synthesis failed: {exc}") from exc
