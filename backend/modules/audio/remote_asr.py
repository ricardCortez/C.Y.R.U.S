"""
JARVIS — Remote ASR backend.

HTTP client for the JARVIS ASR microservice (services/asr_server).
Compatible with the OpenAI /v1/audio/transcriptions API format.

Usage
-----
Configure in config.yaml:
    services:
      asr:
        enabled: true
        host: http://localhost:8000
        language: es

The engine then calls transcribe() / atranscribe() the same way as WhisperASR.
"""

from __future__ import annotations

import base64
import io
import wave
from typing import Optional, Tuple

from backend.utils.exceptions import ASRError
from backend.utils.logger import get_logger

logger = get_logger("cyrus.asr.remote")

try:
    import httpx
    _HTTPX_OK = True
except ImportError:
    _HTTPX_OK = False


class RemoteASR:
    """HTTP client for the JARVIS ASR microservice.

    Args:
        host:        Base URL (e.g. ``http://localhost:8000``).
        language:    Force language code (e.g. ``"es"``); ``None`` = auto.
        timeout:     HTTP request timeout in seconds.
        sample_rate: PCM sample rate (used when wrapping raw PCM → WAV).
    """

    def __init__(
        self,
        host: str = "http://localhost:8000",
        language: Optional[str] = "es",
        timeout: float = 30.0,
        sample_rate: int = 16000,
    ) -> None:
        self._host = host.rstrip("/")
        self._language = language
        self._timeout = timeout
        self._sample_rate = sample_rate
        self._available: Optional[bool] = None

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def check_health(self) -> bool:
        if not _HTTPX_OK:
            self._available = False
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self._host}/health")
                self._available = r.status_code == 200
                if self._available:
                    data = r.json()
                    logger.info(f"[JARVIS] RemoteASR: server ready — model={data.get('model','?')}")
                return self._available
        except Exception as exc:
            logger.warning(f"[JARVIS] RemoteASR: server not reachable at {self._host} ({exc})")
            self._available = False
            return False

    @property
    def available(self) -> bool:
        return bool(self._available)

    # ------------------------------------------------------------------
    # Transcription — async (preferred)
    # ------------------------------------------------------------------

    async def atranscribe(self, pcm_bytes: bytes, sample_rate: Optional[int] = None) -> Tuple[str, str]:
        """Async transcription via remote server.

        Args:
            pcm_bytes:   Raw int16 mono PCM bytes.
            sample_rate: Override sample rate (defaults to instance value).

        Returns:
            ``(transcript_text, language_code)``

        Raises:
            ASRError: On server error or network failure.
        """
        if not _HTTPX_OK:
            raise ASRError("[JARVIS] RemoteASR: httpx not installed")

        sr = sample_rate or self._sample_rate
        wav_bytes = self._pcm_to_wav(pcm_bytes, sr)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
                data: dict = {"model": "whisper-1"}
                if self._language:
                    data["language"] = self._language

                r = await client.post(
                    f"{self._host}/v1/audio/transcriptions",
                    files=files,
                    data=data,
                )
                if r.status_code != 200:
                    raise ASRError(f"[JARVIS] RemoteASR: server returned {r.status_code}: {r.text[:200]}")

                result = r.json()
                text = result.get("text", "").strip()
                lang = result.get("language", self._language or "es")
                logger.info(f"[JARVIS] RemoteASR: '{text[:60]}' (lang={lang})")
                self._available = True
                return text, lang

        except ASRError:
            raise
        except Exception as exc:
            self._available = False
            raise ASRError(f"[JARVIS] RemoteASR: request failed: {exc}") from exc

    def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> Tuple[str, str]:
        """Sync wrapper — runs the async version in a new event loop.
        Use ``atranscribe`` when already inside an async context.
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context — create a concurrent future
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, self.atranscribe(pcm_bytes, sample_rate))
                    return future.result(timeout=self._timeout + 5)
            else:
                return loop.run_until_complete(self.atranscribe(pcm_bytes, sample_rate))
        except ASRError:
            raise
        except Exception as exc:
            raise ASRError(f"[JARVIS] RemoteASR sync wrapper failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int) -> bytes:
        """Wrap raw int16 PCM in a WAV container."""
        if pcm_bytes[:4] == b"RIFF":
            return pcm_bytes   # already WAV
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        return buf.getvalue()
