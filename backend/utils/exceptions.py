"""JARVIS — Custom exception hierarchy."""

from __future__ import annotations


class JARVISError(Exception):
    """Base exception for all JARVIS errors."""


# ── Audio ─────────────────────────────────────────────────────────────────────

class AudioInputError(JARVISError):
    """Raised when the microphone cannot be opened or read."""


class AudioOutputError(JARVISError):
    """Raised when the speaker/stream cannot be written."""


# ── ASR ───────────────────────────────────────────────────────────────────────

class ASRError(JARVISError):
    """Raised when Whisper transcription fails."""


class ASRModelNotLoadedError(ASRError):
    """Raised when the Whisper model has not been initialised yet."""


# ── Trigger ───────────────────────────────────────────────────────────────────

class TriggerDetectionError(JARVISError):
    """Raised on unexpected trigger-detection failures."""


# ── LLM ───────────────────────────────────────────────────────────────────────

class LLMError(JARVISError):
    """Base LLM error."""


class OllamaUnavailableError(LLMError):
    """Raised when the local Ollama service is unreachable."""


class LLMAPIError(LLMError):
    """Raised when the Claude API returns an unexpected error."""


# ── TTS ───────────────────────────────────────────────────────────────────────

class TTSError(JARVISError):
    """Base TTS error."""


class KokoroUnavailableError(TTSError):
    """Raised when Kokoro TTS cannot synthesise audio."""


class TTSAPIError(TTSError):
    """Raised when the TTS API call fails."""


# ── Configuration ─────────────────────────────────────────────────────────────

class ConfigError(JARVISError):
    """Raised for missing or malformed configuration values."""


# ── WebSocket ─────────────────────────────────────────────────────────────────

class WebSocketError(JARVISError):
    """Raised when the WebSocket server encounters a fatal error."""
