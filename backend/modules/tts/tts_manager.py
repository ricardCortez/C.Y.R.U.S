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
from backend.modules.tts.remote_tts import RemoteTTS
from backend.modules.tts.voiceforge_tts import VoiceforgeTTS
from backend.modules.tts.xtts_tts import XTTTS
from backend.utils.exceptions import KokoroUnavailableError, TTSAPIError, TTSError
from backend.utils.logger import get_logger

logger = get_logger("cyrus.tts.manager")


class TTSManager:
    """Unified TTS interface with backend fallback chain.

    Backend priority (first available wins):
      1. Piper      — offline subprocess, highest quality, best Spanish naturalness
      2. RemoteTTS  — external TTS server (xtts-api-server or OpenAI-compat)
      3. XTTS v2    — offline in-process, high quality (optional, heavy)
      4. Kokoro     — offline in-process, good quality
      5. Edge-TTS   — online, always-available fallback

    Args:
        kokoro:    Pre-configured :class:`KokoroTTS` instance.
        voiceforge: Pre-configured :class:`VoiceforgeTTS` instance (Edge-TTS).
        mode:      ``"LOCAL"`` uses only offline backends; ``"HYBRID"`` also
                   allows the Edge-TTS API fallback.
        piper:     Optional :class:`PiperTTS` instance (preferred backend).
        xtts:      Optional :class:`XTTTS` instance (in-process XTTS v2).
        remote:    Optional :class:`RemoteTTS` instance (external TTS server).
    """

    def __init__(
        self,
        kokoro: KokoroTTS,
        voiceforge: VoiceforgeTTS,
        mode: str = "LOCAL",
        piper: Optional[PiperTTS] = None,
        xtts: Optional[XTTTS] = None,
        remote: Optional[RemoteTTS] = None,
    ) -> None:
        self._piper = piper
        self._remote = remote
        self._xtts = xtts
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

        forced = getattr(self, "_forced_backend", None)

        # ── 1. Piper ──────────────────────────────────────────────────
        if (forced == "piper" or forced is None) and self._piper and self._piper.available:
            try:
                wav = self._piper.synthesise(text)
                logger.info(f"[C.Y.R.U.S] TTS: Piper -> {len(wav)} bytes")
                return wav, "audio/wav"
            except TTSError as exc:
                logger.warning(f"[C.Y.R.U.S] TTS: Piper failed ({exc}); trying RemoteTTS...")
        elif forced == "piper":
            logger.warning("[C.Y.R.U.S] TTS: Piper forced but unavailable — falling back")

        # ── 2. RemoteTTS ──────────────────────────────────────────────
        if (forced in ("remote-tts", None)) and self._remote and self._remote.available:
            try:
                wav = await self._remote.synthesise(text)
                logger.info(f"[C.Y.R.U.S] TTS: RemoteTTS -> {len(wav)} bytes")
                return wav, "audio/wav"
            except TTSError as exc:
                logger.warning(f"[C.Y.R.U.S] TTS: RemoteTTS failed ({exc}); trying XTTS...")
        elif forced == "remote-tts":
            logger.warning("[C.Y.R.U.S] TTS: RemoteTTS forced but unavailable — falling back")

        # ── 3. XTTS v2 ────────────────────────────────────────────────
        if (forced == "xtts" or forced is None) and self._xtts and self._xtts.available:
            try:
                wav = self._xtts.synthesise(text)
                logger.info(f"[C.Y.R.U.S] TTS: XTTS v2 -> {len(wav)} bytes")
                return wav, "audio/wav"
            except TTSError as exc:
                logger.warning(f"[C.Y.R.U.S] TTS: XTTS failed ({exc}); trying Kokoro...")
        elif forced == "xtts":
            logger.warning("[C.Y.R.U.S] TTS: XTTS forced but unavailable — falling back")

        # ── 4. Kokoro ─────────────────────────────────────────────────
        if forced in ("kokoro", None) or forced not in ("piper", "remote-tts", "xtts", "edge-tts"):
            try:
                wav = self._kokoro.synthesise(text)
                logger.info(f"[C.Y.R.U.S] TTS: Kokoro -> {len(wav)} bytes")
                return wav, "audio/wav"
            except KokoroUnavailableError as exc:
                logger.warning(f"[C.Y.R.U.S] TTS: Kokoro unavailable ({exc})")
            except TTSError as exc:
                logger.warning(f"[C.Y.R.U.S] TTS: Kokoro error ({exc}); trying Edge-TTS...")
        if self._mode != "LOCAL":
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

    def set_forced_backend(self, backend: str | None) -> None:
        """Pin synthesis to a specific backend, or None to restore auto priority.

        Args:
            backend: ``"piper"``, ``"kokoro"``, ``"edge-tts"``, or ``None``.
        """
        self._forced_backend = backend
        logger.info(f"[C.Y.R.U.S] TTS: forced backend → {backend or 'auto'}")

    def set_voice_preset(self, preset: str) -> None:
        """Apply a named voice preset (adjusts speed and Kokoro voice).

        Presets:
          ``"natural"``  — default speed (0.92), neutral voice
          ``"dramatic"`` — slower (0.82), more deliberate delivery
          ``"suave"``    — gentle (0.78), softer pace
        """
        presets = {
            "natural":  {"speed": 0.92, "voice": None},
            "dramatic": {"speed": 0.82, "voice": None},
            "suave":    {"speed": 0.78, "voice": None},
        }
        cfg = presets.get(preset, presets["natural"])
        self.set_speed(cfg["speed"])
        if cfg["voice"]:
            self.set_voice(cfg["voice"])
        logger.info(f"[C.Y.R.U.S] TTS: preset '{preset}' → speed={cfg['speed']}")

    @property
    def active_backend(self) -> str:
        """Return the name of the first available backend."""
        forced = getattr(self, "_forced_backend", None)
        if forced:
            return forced
        if self._piper and self._piper.available:
            return "piper"
        if self._remote and self._remote.available:
            return "remote-tts"
        if self._xtts and self._xtts.available:
            return "xtts-v2"
        try:
            if self._kokoro._pipeline is not None:
                return "kokoro"
        except AttributeError:
            pass
        return "edge-tts"
