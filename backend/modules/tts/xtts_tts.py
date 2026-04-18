"""
C.Y.R.U.S — XTTS v2 TTS backend (Coqui AI) with voice cloning and latent caching.

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

logger = get_logger("cyrus.tts.xtts")

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
            logger.info(f"[C.Y.R.U.S] TTS XTTS: loading {_XTTS_MODEL} on {dev}...")

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
            logger.info(f"[C.Y.R.U.S] TTS XTTS: ready on {dev}")

            # Pre-compute latents if reference WAV already configured
            if self._reference_wav and Path(self._reference_wav).is_file():
                self._precompute_latents()

        except ImportError as exc:
            logger.warning(f"[C.Y.R.U.S] TTS XTTS: TTS package not available ({exc})")
        except Exception as exc:
            logger.warning(f"[C.Y.R.U.S] TTS XTTS: load failed — {exc}")

    def unload(self) -> None:
        """Release model and cached latents from memory."""
        self._tts            = None
        self._available      = False
        self._cached_latents = None
        logger.info("[C.Y.R.U.S] TTS XTTS: unloaded")

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
        logger.info(f"[C.Y.R.U.S] TTS XTTS: reference voice set to {wav_path}")
        if self._available:
            self._precompute_latents()

    def _precompute_latents(self) -> None:
        """Pre-compute and cache conditioning latents from the reference WAV."""
        if not self._available or self._tts is None:
            return
        if not self._reference_wav or not Path(self._reference_wav).is_file():
            logger.warning(f"[C.Y.R.U.S] TTS XTTS: reference WAV not found: {self._reference_wav}")
            return
        try:
            gpt_cond_latent, speaker_embedding = self._tts.get_conditioning_latents(
                audio_path=[self._reference_wav]
            )
            self._cached_latents = (gpt_cond_latent, speaker_embedding)
            logger.info("[C.Y.R.U.S] TTS XTTS: conditioning latents cached from reference WAV")
        except Exception as exc:
            logger.warning(f"[C.Y.R.U.S] TTS XTTS: latent precompute failed ({exc})")
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
            raise TTSError("[C.Y.R.U.S] XTTS: model not loaded")

        try:
            # Use cached latents (fast) or compute on demand
            if self._cached_latents is not None:
                gpt_cond_latent, speaker_embedding = self._cached_latents
            elif self._reference_wav and Path(self._reference_wav).is_file():
                self._precompute_latents()
                if self._cached_latents:
                    gpt_cond_latent, speaker_embedding = self._cached_latents
                else:
                    raise TTSError("[C.Y.R.U.S] XTTS: no reference voice set. Use record_tts_reference command first.")
            else:
                raise TTSError("[C.Y.R.U.S] XTTS: no reference voice set. Use record_tts_reference command first.")

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
            logger.info(f"[C.Y.R.U.S] TTS XTTS: {len(wav_bytes)} bytes synthesised")
            return wav_bytes

        except TTSError:
            raise
        except Exception as exc:
            raise TTSError(f"[C.Y.R.U.S] XTTS synthesis failed: {exc}") from exc
