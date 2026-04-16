"""
C.Y.R.U.S — Microphone capture with integrated VAD.

Opens the system microphone using PyAudio, streams PCM frames through the
:class:`VADDetector`, and buffers a full utterance (speech onset → silence).
Call :meth:`AudioInput.record_utterance` from an async context.
"""

from __future__ import annotations

import asyncio
import io
import threading
import time
import wave
from pathlib import Path
from typing import AsyncIterator, Optional

import numpy as np
import pyaudio

from backend.modules.audio.vad_detector import VADDetector
from backend.utils.exceptions import AudioInputError
from backend.utils.logger import get_logger

logger = get_logger("cyrus.audio.input")

# PyAudio format map
_FORMAT_MAP = {"int16": pyaudio.paInt16}


class AudioInput:
    """Async microphone capture with voice-activity gating.

    Args:
        sample_rate: PCM sample rate (Hz).
        chunk_size: PyAudio chunk size in samples.
        channels: Number of channels (1 = mono).
        silence_duration: Seconds of post-speech silence that ends an utterance.
        silence_threshold: RMS amplitude below which a frame is considered silent
            (used as a secondary check alongside VAD).
        device_name: Exact substring of the device name to use; ``"default"``
            picks the system default input.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        channels: int = 1,
        silence_duration: float = 1.5,
        silence_threshold: int = 500,
        device_name: str = "default",
    ) -> None:
        self._sample_rate = sample_rate
        self._chunk_size = chunk_size
        self._channels = channels
        self._silence_frames = int(sample_rate / chunk_size * silence_duration)
        self._silence_threshold = silence_threshold
        self._device_name = device_name
        self._pa: Optional[pyaudio.PyAudio] = None
        self._device_index: Optional[int] = None
        self._vad = VADDetector(sample_rate=sample_rate)
        self._stop_flag = threading.Event()    # set to interrupt a live recording
        self._muted_until: float = 0.0         # monotonic timestamp — ignore input before this

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Initialise PyAudio and resolve the device index."""
        self._pa = pyaudio.PyAudio()
        self._device_index = self._resolve_device()
        logger.info(f"[C.Y.R.U.S] AudioInput: opened device index={self._device_index}")

    def close(self) -> None:
        """Release PyAudio resources."""
        if self._pa:
            self._pa.terminate()
            self._pa = None
        logger.info("[C.Y.R.U.S] AudioInput: closed")

    def __enter__(self) -> "AudioInput":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Device resolution
    # ------------------------------------------------------------------

    def _resolve_device(self) -> Optional[int]:
        """Return device index matching ``_device_name``, or None for default."""
        assert self._pa is not None
        if self._device_name == "default":
            return None  # PyAudio uses system default

        count = self._pa.get_device_count()
        for i in range(count):
            info = self._pa.get_device_info_by_index(i)
            if (
                self._device_name.lower() in info["name"].lower()
                and info["maxInputChannels"] > 0
            ):
                logger.debug(f"[C.Y.R.U.S] AudioInput: matched device '{info['name']}' at index {i}")
                return i

        logger.warning(
            f"[C.Y.R.U.S] AudioInput: device '{self._device_name}' not found; using system default"
        )
        return None

    def list_devices(self) -> list[dict]:
        """Return a list of available input devices."""
        pa = pyaudio.PyAudio()
        devices = []
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                devices.append({"index": i, "name": info["name"]})
        pa.terminate()
        return devices

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def request_stop(self) -> None:
        """Signal the current recording to stop at the next chunk boundary."""
        self._stop_flag.set()

    async def detect_speech_onset(self, timeout: float = 30.0) -> bool:
        """Return True as soon as the user starts speaking (barge-in detection).

        Opens a second mic stream concurrently with playback.  Designed to run
        as an asyncio task while ``play_wav`` runs in another executor thread.

        Args:
            timeout: Maximum seconds to wait before giving up (default 30 s).

        Returns:
            True if speech onset detected; False on timeout or stop_flag.
        """
        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self._detect_onset_sync),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return False

    def _detect_onset_sync(self) -> bool:
        """Synchronous speech-onset detector (runs in thread-pool executor)."""
        if self._pa is None:
            return False
        try:
            stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=self._channels,
                rate=self._sample_rate,
                input=True,
                input_device_index=self._device_index,
                frames_per_buffer=self._chunk_size,
            )
        except OSError as exc:
            logger.warning(f"[C.Y.R.U.S] AudioInput: barge-in stream failed: {exc}")
            return False

        vad = VADDetector(sample_rate=self._sample_rate)
        try:
            while True:
                if self._stop_flag.is_set():
                    return False
                data = stream.read(self._chunk_size, exception_on_overflow=False)
                # Ignore during mute window (echo guard)
                if time.monotonic() < self._muted_until:
                    continue
                if vad.feed(data) and self._rms(data) > self._silence_threshold:
                    logger.debug("[C.Y.R.U.S] AudioInput: barge-in speech onset detected")
                    return True
        finally:
            stream.stop_stream()
            stream.close()

    def mute_for(self, seconds: float) -> None:
        """Suppress voice detection for *seconds* — prevents mic from picking up TTS output."""
        self._muted_until = time.monotonic() + seconds
        logger.debug(f"[C.Y.R.U.S] AudioInput: muted for {seconds:.1f}s (echo prevention)")

    async def record_utterance(self) -> bytes:
        """Block until a full voice utterance is captured.

        Listens continuously.  Returns as soon as speech is detected and then
        ``silence_duration`` seconds of silence follow it.

        Returns:
            Raw PCM bytes (int16, mono, 16 kHz) of the utterance.

        Raises:
            AudioInputError: If the microphone stream cannot be opened.
        """
        if self._pa is None:
            raise AudioInputError("[C.Y.R.U.S] AudioInput not opened; call open() first")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._record_sync)

    def _record_sync(self) -> bytes:
        """Synchronous inner loop — runs in a thread pool executor."""
        assert self._pa is not None
        try:
            stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=self._channels,
                rate=self._sample_rate,
                input=True,
                input_device_index=self._device_index,
                frames_per_buffer=self._chunk_size,
            )
        except OSError as exc:
            raise AudioInputError(f"[C.Y.R.U.S] Cannot open microphone: {exc}") from exc

        logger.debug("[C.Y.R.U.S] AudioInput: listening for speech…")
        self._vad.reset()
        self._stop_flag.clear()
        frames: list[bytes] = []
        silence_count = 0
        speech_started = False
        pre_roll: list[bytes] = []  # capture a short pre-roll before speech onset
        max_pre_roll = int(self._sample_rate / self._chunk_size * 0.3)  # 300 ms

        try:
            while True:
                if self._stop_flag.is_set():
                    self._stop_flag.clear()
                    logger.debug("[C.Y.R.U.S] AudioInput: recording interrupted by stop flag")
                    break
                data = stream.read(self._chunk_size, exception_on_overflow=False)
                is_speech = self._vad.feed(data)
                rms = self._rms(data)

                if not speech_started:
                    pre_roll.append(data)
                    if len(pre_roll) > max_pre_roll:
                        pre_roll.pop(0)

                # Ignore audio while muted (post-TTS echo window)
                if time.monotonic() < self._muted_until:
                    continue

                if is_speech and rms > self._silence_threshold:
                    if not speech_started:
                        speech_started = True
                        frames.extend(pre_roll)
                        logger.debug("[C.Y.R.U.S] AudioInput: speech onset detected")
                    silence_count = 0
                    frames.append(data)
                elif speech_started:
                    frames.append(data)
                    silence_count += 1
                    if silence_count >= self._silence_frames:
                        logger.debug("[C.Y.R.U.S] AudioInput: silence end — utterance complete")
                        break
        finally:
            stream.stop_stream()
            stream.close()

        return b"".join(frames)

    @staticmethod
    def _rms(pcm: bytes) -> float:
        """Compute RMS amplitude of a PCM int16 frame."""
        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        if arr.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(arr ** 2)))

    def pcm_to_wav(self, pcm: bytes) -> bytes:
        """Wrap raw PCM bytes in a WAV container.

        Args:
            pcm: Raw int16 mono PCM bytes.

        Returns:
            In-memory WAV file bytes.
        """
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self._channels)
            wf.setsampwidth(2)  # int16 = 2 bytes
            wf.setframerate(self._sample_rate)
            wf.writeframes(pcm)
        return buf.getvalue()
