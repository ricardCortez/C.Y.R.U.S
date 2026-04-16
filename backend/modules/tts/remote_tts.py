"""
C.Y.R.U.S — Remote TTS backend.

Calls an external TTS HTTP server (e.g. xtts-api-server) and returns WAV bytes.
Decouples heavy TTS ML dependencies from the main C.Y.R.U.S process.

Supported server formats
------------------------
1. xtts-api-server (daswer123/xtts-api-server)
     POST /tts_to_audio
     body: {"text": "...", "speaker_wav": "...", "language": "es"}
     response: audio/wav bytes

2. OpenAI-compatible TTS (/v1/audio/speech)
     POST /v1/audio/speech
     body: {"model": "tts-1", "input": "...", "voice": "alloy"}
     response: audio bytes

Installation (separate Python env recommended):
    pip install xtts-api-server
    xtts-server --port 8020 --device cuda
"""

from __future__ import annotations

from typing import Optional

from backend.utils.exceptions import TTSError
from backend.utils.logger import get_logger

logger = get_logger("cyrus.tts.remote")

try:
    import httpx
    _HTTPX_OK = True
except ImportError:
    _HTTPX_OK = False


class RemoteTTS:
    """HTTP client for a remote TTS synthesis server.

    Args:
        host:     Base URL of the TTS server (e.g. ``http://localhost:8020``).
        language: BCP-47 language code forwarded to the server (e.g. ``"es"``).
        speaker:  Speaker name or path to reference WAV for voice cloning.
                  Pass empty string to use the server default.
        timeout:  HTTP request timeout in seconds.
    """

    def __init__(
        self,
        host: str = "http://localhost:8020",
        language: str = "es",
        speaker: str = "",
        timeout: float = 60.0,
    ) -> None:
        self._host = host.rstrip("/")
        self._language = language
        self._speaker = speaker
        self._timeout = timeout
        self._available: Optional[bool] = None   # None = not yet checked

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def check_health(self) -> bool:
        """Probe the server and cache the result in ``self._available``.

        Returns:
            ``True`` if the server is reachable and healthy.
        """
        if not _HTTPX_OK:
            logger.warning("[C.Y.R.U.S] RemoteTTS: httpx not installed")
            self._available = False
            return False

        endpoints = ["/speakers", "/docs", "/health", "/"]
        async with httpx.AsyncClient(timeout=5.0) as client:
            for ep in endpoints:
                try:
                    r = await client.get(f"{self._host}{ep}")
                    if r.status_code < 500:
                        self._available = True
                        logger.info(f"[C.Y.R.U.S] RemoteTTS: server online at {self._host} (probe {ep} → {r.status_code})")
                        return True
                except Exception:
                    continue

        self._available = False
        logger.warning(f"[C.Y.R.U.S] RemoteTTS: server not reachable at {self._host}")
        return False

    @property
    def available(self) -> bool:
        """``True`` after a successful :meth:`check_health` call."""
        return bool(self._available)

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    async def synthesise(self, text: str) -> bytes:
        """Synthesise *text* via the remote TTS server.

        Tries xtts-api-server format first, then OpenAI-compatible format.

        Args:
            text: Clean speech text (no markdown).

        Returns:
            WAV or MP3 audio bytes returned by the server.

        Raises:
            TTSError: If the server is unreachable or returns an error.
        """
        if not _HTTPX_OK:
            raise TTSError("[C.Y.R.U.S] RemoteTTS: httpx not installed")
        if not text.strip():
            return b""

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # ── xtts-api-server format ────────────────────────────────────
            try:
                payload: dict = {"text": text, "language": self._language}
                if self._speaker:
                    payload["speaker_wav"] = self._speaker
                r = await client.post(
                    f"{self._host}/tts_to_audio",
                    json=payload,
                )
                if r.status_code == 200 and r.content:
                    logger.info(f"[C.Y.R.U.S] RemoteTTS: xtts-api-server → {len(r.content)} bytes")
                    self._available = True
                    return r.content
                if r.status_code not in (404, 405):
                    raise TTSError(f"[C.Y.R.U.S] RemoteTTS: server returned {r.status_code}: {r.text[:200]}")
            except TTSError:
                raise
            except Exception as exc:
                logger.debug(f"[C.Y.R.U.S] RemoteTTS: xtts-api-server endpoint failed ({exc}), trying OpenAI format")

            # ── OpenAI-compatible format ──────────────────────────────────
            try:
                r = await client.post(
                    f"{self._host}/v1/audio/speech",
                    json={
                        "model": "tts-1",
                        "input": text,
                        "voice": self._speaker or "alloy",
                    },
                )
                if r.status_code == 200 and r.content:
                    logger.info(f"[C.Y.R.U.S] RemoteTTS: OpenAI-compat → {len(r.content)} bytes")
                    self._available = True
                    return r.content
                raise TTSError(f"[C.Y.R.U.S] RemoteTTS: OpenAI endpoint returned {r.status_code}: {r.text[:200]}")
            except TTSError:
                raise
            except Exception as exc:
                self._available = False
                raise TTSError(f"[C.Y.R.U.S] RemoteTTS: all endpoints failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Runtime configuration
    # ------------------------------------------------------------------

    def set_speaker(self, speaker: str) -> None:
        """Update the speaker at runtime."""
        self._speaker = speaker
        logger.info(f"[C.Y.R.U.S] RemoteTTS: speaker → '{speaker}'")

    def set_language(self, language: str) -> None:
        """Update the synthesis language at runtime."""
        self._language = language
        logger.info(f"[C.Y.R.U.S] RemoteTTS: language → '{language}'")
