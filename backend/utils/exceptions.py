"""C.Y.R.U.S — Custom exception hierarchy."""

from __future__ import annotations


class CYRUSError(Exception):
    """Base exception for all C.Y.R.U.S errors."""


# ── Audio ─────────────────────────────────────────────────────────────────────

class AudioInputError(CYRUSError):
    """Raised when the microphone cannot be opened or read."""


class AudioOutputError(CYRUSError):
    """Raised when the speaker/stream cannot be written."""


# ── ASR ───────────────────────────────────────────────────────────────────────

class ASRError(CYRUSError):
    """Raised when Whisper transcription fails."""


class ASRModelNotLoadedError(ASRError):
    """Raised when the Whisper model has not been initialised yet."""


# ── Trigger ───────────────────────────────────────────────────────────────────

class TriggerDetectionError(CYRUSError):
    """Raised on unexpected trigger-detection failures."""


# ── LLM ───────────────────────────────────────────────────────────────────────

class LLMError(CYRUSError):
    """Base LLM error."""


class OllamaUnavailableError(LLMError):
    """Raised when the local Ollama service is unreachable."""


class LLMAPIError(LLMError):
    """Raised when the Claude API returns an unexpected error."""


# ── TTS ───────────────────────────────────────────────────────────────────────

class TTSError(CYRUSError):
    """Base TTS error."""


class KokoroUnavailableError(TTSError):
    """Raised when Kokoro TTS cannot synthesise audio."""


class TTSAPIError(TTSError):
    """Raised when the TTS API call fails."""


# ── Configuration ─────────────────────────────────────────────────────────────

class ConfigError(CYRUSError):
    """Raised for missing or malformed configuration values."""


# ── WebSocket ─────────────────────────────────────────────────────────────────

class WebSocketError(CYRUSError):
    """Raised when the WebSocket server encounters a fatal error."""
