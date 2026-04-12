"""
C.Y.R.U.S — Edge-TTS fallback (Microsoft Azure TTS via edge-tts package).

Used when Kokoro is unavailable.  edge-tts requires no API key — it uses
Microsoft's free TTS endpoint used by the Edge browser.
"""

from __future__ import annotations

import asyncio
import io
import wave
from typing import Optional

from backend.utils.exceptions import TTSAPIError, TTSError
from backend.utils.logger import get_logger

logger = get_logger("cyrus.tts.edge")

try:
    import edge_tts
    _EDGE_TTS_AVAILABLE = True
except ImportError:
    _EDGE_TTS_AVAILABLE = False
    logger.warning("[C.Y.R.U.S] edge-tts not installed; API TTS fallback unavailable")


class VoiceforgeTTS:
    """Edge-TTS (Microsoft) synthesis fallback.

    The class name ``VoiceforgeTTS`` is kept for consistency with the spec;
    internally it delegates to ``edge_tts``.

    Args:
        voice: Edge-TTS voice name (e.g. ``"en-GB-RyanNeural"``).
        rate: Speaking rate adjustment (e.g. ``"+0%"``).
        volume: Volume adjustment (e.g. ``"+0%"``).
    """

    def __init__(
        self,
        voice: str = "en-GB-RyanNeural",
        rate: str = "+0%",
        volume: str = "+0%",
    ) -> None:
        self._voice = voice
        self._rate = rate
        self._volume = volume

    async def synthesise(self, text: str) -> bytes:
        """Synthesise *text* using Edge-TTS.

        Args:
            text: Input text.

        Returns:
            Raw MP3 audio bytes (edge-tts output format).

        Raises:
            TTSAPIError: If edge-tts is unavailable or the API call fails.
        """
        if not _EDGE_TTS_AVAILABLE:
            raise TTSAPIError("[C.Y.R.U.S] edge-tts package not installed")
        if not text.strip():
            return b""

        try:
            communicate = edge_tts.Communicate(
                text,
                voice=self._voice,
                rate=self._rate,
                volume=self._volume,
            )
            mp3_chunks: list[bytes] = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_chunks.append(chunk["data"])
            data = b"".join(mp3_chunks)
            logger.info(f"[C.Y.R.U.S] TTS (edge): synthesised {len(data)} bytes")
            return data
        except Exception as exc:
            raise TTSAPIError(f"[C.Y.R.U.S] Edge-TTS error: {exc}") from exc
