"""
C.Y.R.U.S — TTS Manager.

Orchestrates Kokoro (local) → Edge-TTS (API fallback) with automatic
error handling.  Returns WAV or MP3 bytes ready for :class:`AudioOutput`.
"""

from __future__ import annotations

from backend.modules.tts.kokoro_tts import KokoroTTS
from backend.modules.tts.voiceforge_tts import VoiceforgeTTS
from backend.utils.exceptions import KokoroUnavailableError, TTSAPIError, TTSError
from backend.utils.logger import get_logger

logger = get_logger("cyrus.tts.manager")


class TTSManager:
    """Unified TTS interface with LOCAL → API fallback.

    Args:
        kokoro: Pre-configured :class:`KokoroTTS` instance (local).
        voiceforge: Pre-configured :class:`VoiceforgeTTS` instance (API fallback).
        mode: ``"LOCAL"`` or ``"HYBRID"``.
    """

    def __init__(
        self,
        kokoro: KokoroTTS,
        voiceforge: VoiceforgeTTS,
        mode: str = "LOCAL",
    ) -> None:
        self._kokoro = kokoro
        self._voiceforge = voiceforge
        self._mode = mode.upper()

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    async def synthesise(self, text: str) -> tuple[bytes, str]:
        """Synthesise *text* with fallback logic.

        Returns:
            ``(audio_bytes, mime_type)`` where mime_type is ``"audio/wav"``
            or ``"audio/mpeg"``.

        Raises:
            TTSError: If all backends fail.
        """
        if not text.strip():
            logger.warning("[C.Y.R.U.S] TTS: empty text passed to synthesise()")
            return b"", "audio/wav"

        # Try Kokoro local first
        try:
            wav = self._kokoro.synthesise(text)
            logger.info(f"[C.Y.R.U.S] TTS: Kokoro synthesised {len(wav)} bytes")
            return wav, "audio/wav"
        except KokoroUnavailableError as exc:
            logger.warning(f"[C.Y.R.U.S] TTS: Kokoro unavailable — {exc}")
        except TTSError as exc:
            logger.warning(f"[C.Y.R.U.S] TTS: Kokoro error — {exc}")

        # Fallback to Edge-TTS (available in both LOCAL and HYBRID)
        try:
            logger.info("[C.Y.R.U.S] TTS: falling back to Edge-TTS…")
            mp3 = await self._voiceforge.synthesise(text)
            if mp3:
                logger.info(f"[C.Y.R.U.S] TTS: Edge-TTS synthesised {len(mp3)} bytes")
                return mp3, "audio/mpeg"
        except TTSAPIError as exc:
            logger.error(f"[C.Y.R.U.S] TTS: Edge-TTS also failed — {exc}")

        raise TTSError("[C.Y.R.U.S] TTS: all synthesis backends failed")
