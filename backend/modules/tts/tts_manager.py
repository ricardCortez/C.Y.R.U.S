"""
C.Y.R.U.S — TTS Manager.

Orchestrates the TTS backend chain with automatic fallback:

  Piper (local, best quality)
    → Kokoro (local, good quality)
      → Edge-TTS (API fallback)

Returns WAV or MP3 bytes ready for :class:`AudioOutput`.

Adding a new TTS engine:
  1. Create a class in ``backend/modules/tts/`` with a ``synthesise(text) → bytes`` method.
  2. Instantiate it in ``CYRUSEngine.__init__``.
  3. Pass it to ``TTSManager`` and add it to ``_try_backends``.
"""

from __future__ import annotations

from typing import Optional

from backend.modules.tts.kokoro_tts import KokoroTTS
from backend.modules.tts.piper_tts import PiperTTS
from backend.modules.tts.voiceforge_tts import VoiceforgeTTS
from backend.utils.exceptions import KokoroUnavailableError, TTSAPIError, TTSError
from backend.utils.logger import get_logger

logger = get_logger("cyrus.tts.manager")


class TTSManager:
    """Unified TTS interface with backend fallback chain.

    Backend priority (first available wins):
      1. Piper   — offline, highest quality, best Spanish naturalness
      2. Kokoro  — offline, good quality
      3. Edge-TTS — online, always-available fallback

    Args:
        kokoro: Pre-configured :class:`KokoroTTS` instance.
        voiceforge: Pre-configured :class:`VoiceforgeTTS` instance (Edge-TTS).
        mode: ``"LOCAL"`` uses only offline backends; ``"HYBRID"`` also
            allows the Edge-TTS API fallback.
        piper: Optional :class:`PiperTTS` instance (preferred backend).
    """

    def __init__(
        self,
        kokoro: KokoroTTS,
        voiceforge: VoiceforgeTTS,
        mode: str = "LOCAL",
        piper: Optional[PiperTTS] = None,
    ) -> None:
        self._piper = piper
        self._kokoro = kokoro
        self._voiceforge = voiceforge
        self._mode = mode.upper()

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    async def synthesise(self, text: str) -> tuple[bytes, str]:
        """Synthesise *text* with automatic backend fallback.

        Args:
            text: Clean speech text (markdown and technical notation already
                processed by :func:`~backend.utils.text_cleaner.prepare_speech`).

        Returns:
            ``(audio_bytes, mime_type)`` where mime_type is ``"audio/wav"``
            or ``"audio/mpeg"``.

        Raises:
            TTSError: If all backends fail.
        """
        if not text.strip():
            logger.warning("[C.Y.R.U.S] TTS: empty text — returning silence")
            return b"", "audio/wav"

        # ── 1. Piper (best quality) ────────────────────────────────────
        if self._piper and self._piper.available:
            try:
                wav = self._piper.synthesise(text)
                logger.info(f"[C.Y.R.U.S] TTS: Piper → {len(wav)} bytes")
                return wav, "audio/wav"
            except TTSError as exc:
                logger.warning(f"[C.Y.R.U.S] TTS: Piper failed ({exc}); trying Kokoro…")

        # ── 2. Kokoro (offline fallback) ───────────────────────────────
        try:
            wav = self._kokoro.synthesise(text)
            logger.info(f"[C.Y.R.U.S] TTS: Kokoro → {len(wav)} bytes")
            return wav, "audio/wav"
        except KokoroUnavailableError as exc:
            logger.warning(f"[C.Y.R.U.S] TTS: Kokoro unavailable ({exc})")
        except TTSError as exc:
            logger.warning(f"[C.Y.R.U.S] TTS: Kokoro error ({exc}); trying Edge-TTS…")

        # ── 3. Edge-TTS (API — available in LOCAL and HYBRID) ─────────
        try:
            logger.info("[C.Y.R.U.S] TTS: falling back to Edge-TTS…")
            mp3 = await self._voiceforge.synthesise(text)
            if mp3:
                logger.info(f"[C.Y.R.U.S] TTS: Edge-TTS → {len(mp3)} bytes")
                return mp3, "audio/mpeg"
        except TTSAPIError as exc:
            logger.error(f"[C.Y.R.U.S] TTS: Edge-TTS also failed ({exc})")

        raise TTSError("[C.Y.R.U.S] TTS: all synthesis backends failed")

    # ------------------------------------------------------------------
    # Runtime configuration
    # ------------------------------------------------------------------

    def set_speed(self, speed: float) -> None:
        """Update speaking rate on all loaded backends."""
        speed = max(0.25, min(4.0, speed))
        if self._piper:
            self._piper._speed = speed
        self._kokoro._speed = speed
        logger.info(f"[C.Y.R.U.S] TTS: speed set to {speed}")

    def set_voice(self, voice: str) -> None:
        """Update Kokoro voice ID at runtime."""
        self._kokoro._voice = voice
        logger.info(f"[C.Y.R.U.S] TTS: Kokoro voice set to '{voice}'")

    @property
    def active_backend(self) -> str:
        """Return the name of the first available backend."""
        if self._piper and self._piper.available:
            return "piper"
        try:
            # Kokoro is loaded if its pipeline is not None
            if self._kokoro._pipeline is not None:
                return "kokoro"
        except AttributeError:
            pass
        return "edge-tts"
