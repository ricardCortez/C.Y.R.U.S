"""
C.Y.R.U.S — Piper TTS local synthesis.

High-quality offline TTS using Piper (https://github.com/rhasspy/piper).
Produces significantly more natural-sounding Spanish than Kokoro.

Installation (choose one):
  pip install piper-tts                   # Python package
  # OR download piper.exe from https://github.com/rhasspy/piper/releases

Recommended Spanish voice models (download .onnx + .onnx.json):
  es_MX-claude-high   — Mexican Spanish, high quality  ← best for CYRUS
  es_MX-ald-medium    — Mexican Spanish, medium quality
  es_ES-davefx-medium — Castilian Spanish, medium quality

Download voices from:
  https://huggingface.co/rhasspy/piper-voices/tree/main/es
"""

from __future__ import annotations

import io
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional

import numpy as np

from backend.utils.exceptions import TTSError
from backend.utils.logger import get_logger

logger = get_logger("cyrus.tts.piper")

try:
    from piper import PiperVoice as _PiperVoice
    _PIPER_PACKAGE = True
    logger.debug("[C.Y.R.U.S] piper-tts Python package available")
except ImportError:
    _PIPER_PACKAGE = False
    logger.debug("[C.Y.R.U.S] piper-tts package not installed; will use subprocess fallback")


class PiperTTS:
    """Piper offline TTS — natural, fast, fully local.

    Supports two backends (tried in order):
    1. ``piper-tts`` Python package (zero subprocess overhead, preferred)
    2. ``piper`` / ``piper.exe`` executable via subprocess (universal fallback)

    Args:
        model_path: Path to the ``.onnx`` voice model file.
            Companion ``.onnx.json`` must exist in the same directory.
        speed: Speaking rate multiplier — 1.0 is normal, 0.85 is slightly
            slower and typically more natural for a JARVIS-style assistant.
        sample_rate: Output WAV sample rate in Hz (model-dependent, usually 22050).
        speaker_id: Speaker index for multi-speaker models; ``None`` for
            single-speaker voices.
        executable: Path to the ``piper`` binary (used only if the Python
            package is unavailable).
    """

    def __init__(
        self,
        model_path: str = "",
        speed: float = 0.95,
        sample_rate: int = 22050,
        speaker_id: Optional[int] = None,
        executable: str = "piper",
    ) -> None:
        self._model_path = Path(model_path).resolve() if model_path else None
        self._speed = max(0.25, min(4.0, speed))
        self._sample_rate = sample_rate
        self._speaker_id = speaker_id
        self._executable = executable
        self._voice: Optional[object] = None   # PiperVoice instance
        self._use_package: bool = False
        self._use_subprocess: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load and validate the Piper voice model.

        Raises:
            TTSError: If neither the Python package nor the executable is
                available, or if the model file is missing.
        """
        if self._model_path is None or not self._model_path.exists():
            raise TTSError(
                f"[C.Y.R.U.S] Piper model not found: {self._model_path}. "
                "Download from https://huggingface.co/rhasspy/piper-voices"
            )

        # Try Python package first
        if _PIPER_PACKAGE:
            try:
                logger.info(f"[C.Y.R.U.S] TTS Piper: loading {self._model_path.name}…")
                self._voice = _PiperVoice.load(str(self._model_path))
                self._use_package = True
                logger.info("[C.Y.R.U.S] TTS Piper: ready (Python package)")
                return
            except Exception as exc:
                logger.warning(
                    f"[C.Y.R.U.S] TTS Piper: package load failed ({exc}); "
                    "falling back to subprocess"
                )

        # Try subprocess fallback
        try:
            result = subprocess.run(
                [self._executable, "--version"],
                capture_output=True,
                timeout=5,
            )
            self._use_subprocess = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._use_subprocess = False

        if not self._use_subprocess:
            raise TTSError(
                "[C.Y.R.U.S] Piper unavailable: neither piper-tts package nor "
                f"'{self._executable}' executable found. "
                "Run: pip install piper-tts"
            )
        logger.info(f"[C.Y.R.U.S] TTS Piper: ready (subprocess → {self._executable})")

    def unload(self) -> None:
        """Release model resources."""
        self._voice = None
        self._use_package = False
        self._use_subprocess = False
        logger.info("[C.Y.R.U.S] TTS Piper: unloaded")

    @property
    def available(self) -> bool:
        """True if load() completed successfully."""
        return self._use_package or self._use_subprocess

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def synthesise(self, text: str) -> bytes:
        """Synthesise *text* to WAV bytes.

        Args:
            text: Clean plain text (no markdown, no code blocks).

        Returns:
            In-memory 16-bit mono WAV bytes.

        Raises:
            TTSError: If Piper is not loaded or synthesis fails.
        """
        if not self.available:
            raise TTSError("[C.Y.R.U.S] Piper not loaded; call load() first")
        if not text.strip():
            return self._silence_wav(0.3)

        if self._use_package:
            return self._via_package(text)
        return self._via_subprocess(text)

    def _via_package(self, text: str) -> bytes:
        """Synthesise using the piper-tts Python package (v1.4+ API).

        piper-tts ≥1.4 returns Iterable[AudioChunk] from synthesize().
        Each chunk carries sample_rate, sample_width, sample_channels,
        and audio_int16_bytes.
        """
        from piper.voice import SynthesisConfig  # available in 1.4+

        length_scale = round(1.0 / self._speed, 3)
        syn_cfg = SynthesisConfig(length_scale=length_scale)

        pcm_parts: list[bytes] = []
        sample_rate = self._sample_rate
        sample_width = 2
        channels = 1

        for chunk in self._voice.synthesize(text, syn_cfg):  # type: ignore[union-attr]
            pcm_parts.append(chunk.audio_int16_bytes)
            # Read actual params from first chunk
            sample_rate = chunk.sample_rate
            sample_width = chunk.sample_width
            channels = chunk.sample_channels

        if not pcm_parts:
            logger.warning("[C.Y.R.U.S] TTS Piper: no audio chunks produced")
            return self._silence_wav(0.5)

        pcm_all = b"".join(pcm_parts)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_all)
        wav_bytes = buf.getvalue()
        logger.debug(f"[C.Y.R.U.S] TTS Piper (pkg): synthesised {len(wav_bytes)} bytes @ {sample_rate}Hz")
        return wav_bytes

    def _via_subprocess(self, text: str) -> bytes:
        """Synthesise using the piper executable via subprocess."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            cmd = [
                self._executable,
                "--model", str(self._model_path),
                "--output_file", str(tmp_path),
                "--length_scale", str(round(1.0 / self._speed, 3)),
            ]
            if self._speaker_id is not None:
                cmd += ["--speaker", str(self._speaker_id)]

            proc = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=30,
            )
            if proc.returncode != 0:
                stderr = proc.stderr.decode(errors="replace").strip()
                raise TTSError(f"[C.Y.R.U.S] Piper subprocess error: {stderr}")

            wav_bytes = tmp_path.read_bytes()
            logger.debug(f"[C.Y.R.U.S] TTS Piper (exe): synthesised {len(wav_bytes)} bytes")
            return wav_bytes
        except subprocess.TimeoutExpired as exc:
            raise TTSError(f"[C.Y.R.U.S] Piper subprocess timed out: {exc}") from exc
        finally:
            tmp_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _silence_wav(self, duration: float) -> bytes:
        """Return WAV bytes containing *duration* seconds of silence."""
        n = int(self._sample_rate * duration)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._sample_rate)
            wf.writeframes(np.zeros(n, dtype=np.int16).tobytes())
        return buf.getvalue()
