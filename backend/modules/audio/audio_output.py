"""
C.Y.R.U.S — Audio Output (speaker playback).

Plays PCM or WAV bytes through the system speaker using PyAudio.
Supports volume control and async non-blocking playback.
"""

from __future__ import annotations

import asyncio
import io
import wave
from typing import Optional

import numpy as np
import pyaudio

from backend.utils.exceptions import AudioOutputError
from backend.utils.logger import get_logger

logger = get_logger("cyrus.audio.output")


class AudioOutput:
    """PyAudio-based speaker playback.

    Args:
        volume: Playback volume multiplier 0.0–1.0.
        sample_rate: Default output sample rate (overridden by WAV header).
        channels: Number of output channels.
        chunk_size: Frames per write call.
        device_name: Substring of target device name; ``"default"`` picks system default.
    """

    def __init__(
        self,
        volume: float = 0.85,
        sample_rate: int = 24000,
        channels: int = 1,
        chunk_size: int = 1024,
        device_name: str = "default",
    ) -> None:
        self.volume = max(0.0, min(1.0, volume))
        self._sample_rate = sample_rate
        self._channels = channels
        self._chunk_size = chunk_size
        self._device_name = device_name
        self._pa: Optional[pyaudio.PyAudio] = None
        self._device_index: Optional[int] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Initialise PyAudio."""
        self._pa = pyaudio.PyAudio()
        self._device_index = self._resolve_device()
        logger.info(f"[C.Y.R.U.S] AudioOutput: opened device index={self._device_index}")

    def close(self) -> None:
        """Terminate PyAudio."""
        if self._pa:
            self._pa.terminate()
            self._pa = None

    def __enter__(self) -> "AudioOutput":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _resolve_device(self) -> Optional[int]:
        assert self._pa is not None
        if self._device_name == "default":
            return None
        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            if (
                self._device_name.lower() in info["name"].lower()
                and info["maxOutputChannels"] > 0
            ):
                return i
        logger.warning(f"[C.Y.R.U.S] AudioOutput: '{self._device_name}' not found; using default")
        return None

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    async def play_wav(self, wav_bytes: bytes) -> None:
        """Play WAV-format audio bytes asynchronously.

        Args:
            wav_bytes: In-memory WAV file bytes.

        Raises:
            AudioOutputError: If the stream cannot be opened or wav_bytes is invalid.
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._play_wav_sync, wav_bytes)

    async def play_pcm(self, pcm_bytes: bytes, sample_rate: int | None = None) -> None:
        """Play raw PCM int16 mono audio bytes.

        Args:
            pcm_bytes: Raw PCM bytes.
            sample_rate: Sample rate; defaults to ``self._sample_rate``.
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, self._play_pcm_sync, pcm_bytes, sample_rate or self._sample_rate
        )

    def _play_wav_sync(self, wav_bytes: bytes) -> None:
        """Synchronous WAV playback (runs in executor)."""
        if self._pa is None:
            raise AudioOutputError("[C.Y.R.U.S] AudioOutput not opened")
        try:
            buf = io.BytesIO(wav_bytes)
            with wave.open(buf, "rb") as wf:
                rate = wf.getframerate()
                channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                pa_format = self._pa.get_format_from_width(sampwidth)

                stream = self._pa.open(
                    format=pa_format,
                    channels=channels,
                    rate=rate,
                    output=True,
                    output_device_index=self._device_index,
                )
                try:
                    chunk = self._chunk_size
                    data = wf.readframes(chunk)
                    while data:
                        data = self._apply_volume(data, sampwidth)
                        stream.write(data)
                        data = wf.readframes(chunk)
                finally:
                    stream.stop_stream()
                    stream.close()
        except wave.Error as exc:
            raise AudioOutputError(f"[C.Y.R.U.S] Invalid WAV data: {exc}") from exc
        except OSError as exc:
            raise AudioOutputError(f"[C.Y.R.U.S] AudioOutput stream error: {exc}") from exc

    def _play_pcm_sync(self, pcm_bytes: bytes, sample_rate: int) -> None:
        """Synchronous PCM playback (runs in executor)."""
        if self._pa is None:
            raise AudioOutputError("[C.Y.R.U.S] AudioOutput not opened")
        stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self._channels,
            rate=sample_rate,
            output=True,
            output_device_index=self._device_index,
        )
        try:
            for offset in range(0, len(pcm_bytes), self._chunk_size * 2):
                chunk = pcm_bytes[offset : offset + self._chunk_size * 2]
                stream.write(self._apply_volume(chunk, 2))
        finally:
            stream.stop_stream()
            stream.close()

    def _apply_volume(self, pcm: bytes, sampwidth: int) -> bytes:
        """Scale PCM amplitude by ``self.volume``."""
        if self.volume == 1.0:
            return pcm
        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        arr = np.clip(arr * self.volume, -32768, 32767).astype(np.int16)
        return arr.tobytes()
