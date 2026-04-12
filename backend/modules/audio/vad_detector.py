"""
C.Y.R.U.S — Voice Activity Detector.

Uses WebRTC VAD (webrtcvad) for frame-level speech / silence classification.
Provides a simple streaming API: feed PCM chunks, receive True/False.
"""

from __future__ import annotations

import struct
from collections import deque
from typing import Deque

import webrtcvad

from backend.utils.logger import get_logger

logger = get_logger("cyrus.audio.vad")

# webrtcvad only accepts specific frame durations at specific rates.
_VALID_FRAME_MS = {10, 20, 30}
_VALID_RATES = {8000, 16000, 32000, 48000}


class VADDetector:
    """Frame-level voice-activity detector.

    Args:
        sample_rate: Input sample rate in Hz (must be in 8k/16k/32k/48k).
        frame_duration_ms: Frame duration in milliseconds (10, 20, or 30).
        aggressiveness: WebRTC VAD aggressiveness 0–3 (3 = most aggressive).
        speech_ratio: Fraction of frames in the ring buffer that must be
            speech-positive to declare speech is ongoing.
        ring_buffer_len: Number of most-recent frames to consider.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        aggressiveness: int = 2,
        speech_ratio: float = 0.75,
        ring_buffer_len: int = 15,
    ) -> None:
        if sample_rate not in _VALID_RATES:
            raise ValueError(f"[C.Y.R.U.S] VAD: sample_rate must be one of {_VALID_RATES}")
        if frame_duration_ms not in _VALID_FRAME_MS:
            raise ValueError(f"[C.Y.R.U.S] VAD: frame_duration_ms must be one of {_VALID_FRAME_MS}")

        self._vad = webrtcvad.Vad(aggressiveness)
        self._sample_rate = sample_rate
        self._frame_duration_ms = frame_duration_ms
        self._frame_bytes = int(sample_rate * frame_duration_ms / 1000) * 2  # 16-bit PCM
        self._speech_ratio = speech_ratio
        self._ring: Deque[bool] = deque(maxlen=ring_buffer_len)
        self._triggered = False
        self._buffer = b""

    @property
    def frame_bytes(self) -> int:
        """Number of bytes expected per frame."""
        return self._frame_bytes

    def is_speech(self, pcm_frame: bytes) -> bool:
        """Classify a single PCM frame.

        Args:
            pcm_frame: Raw PCM bytes (int16, mono) of exactly ``frame_bytes`` length.

        Returns:
            ``True`` if the frame contains speech.
        """
        if len(pcm_frame) != self._frame_bytes:
            return False
        try:
            return self._vad.is_speech(pcm_frame, self._sample_rate)
        except Exception:
            return False

    def feed(self, pcm_chunk: bytes) -> bool:
        """Feed a chunk of arbitrary size; return smoothed speech/silence.

        Internally splits into fixed-size frames, maintains a ring buffer,
        and applies a majority-vote smoothing to reduce false transitions.

        Args:
            pcm_chunk: Raw PCM int16 bytes (any length).

        Returns:
            ``True`` if the smoothed decision is speech is active.
        """
        self._buffer += pcm_chunk
        while len(self._buffer) >= self._frame_bytes:
            frame = self._buffer[: self._frame_bytes]
            self._buffer = self._buffer[self._frame_bytes :]
            self._ring.append(self.is_speech(frame))

        if not self._ring:
            return self._triggered

        ratio = sum(self._ring) / len(self._ring)
        if ratio >= self._speech_ratio:
            self._triggered = True
        elif ratio < (1 - self._speech_ratio):
            self._triggered = False

        return self._triggered

    def reset(self) -> None:
        """Reset internal state (call between utterances)."""
        self._triggered = False
        self._ring.clear()
        self._buffer = b""
