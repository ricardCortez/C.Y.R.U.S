"""
C.Y.R.U.S — Microphone capture with VAD, noise gate, and speaker gate.

Uses sounddevice (WASAPI shared mode on Windows) to eliminate mic monitoring
echo. Adds adaptive noise floor calibration and optional speaker verification.
"""
from __future__ import annotations

import asyncio
import io
import threading
import time
import wave
from typing import Optional

import numpy as np
import sounddevice as sd

from backend.modules.audio.vad_detector import VADDetector
from backend.utils.exceptions import AudioInputError
from backend.utils.logger import get_logger

logger = get_logger("cyrus.audio.input")

_SpeakerProfile = None


class AudioInput:
    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        channels: int = 1,
        silence_duration: float = 1.5,
        silence_threshold: int = 400,
        device_name: str = "default",
        noise_gate_factor: float = 3.5,
        noise_calibration_secs: float = 2.0,
        speaker_gate_enabled: bool = True,
    ) -> None:
        self._sample_rate = sample_rate
        self._chunk_size = chunk_size
        self._channels = channels
        self._silence_frames = int(sample_rate / chunk_size * silence_duration)
        self._silence_threshold = silence_threshold
        self._device_name = device_name
        self._noise_gate_factor = noise_gate_factor
        self._noise_calibration_secs = noise_calibration_secs
        self._speaker_gate_enabled = speaker_gate_enabled

        self._device_index: Optional[int] = None
        self._vad = VADDetector(sample_rate=sample_rate, aggressiveness=3)
        self._stop_flag = threading.Event()
        self._muted_until: float = 0.0
        self._voice_profile = None

        # Noise gate — calibrated at open()
        self._noise_floor: float = 0.0
        self._last_speech_at: float = 0.0
        self._RECALIB_IDLE_SECS: float = 300.0  # 5 min

    # ── Stream helper ─────────────────────────────────────────────────────────
    def _is_wasapi_device(self) -> bool:
        """Return True if the resolved device belongs to the WASAPI host API."""
        try:
            idx = self._device_index if self._device_index is not None else sd.default.device[0]
            hostapi_idx = sd.query_devices(idx)["hostapi"]
            return "wasapi" in sd.query_hostapis(hostapi_idx)["name"].lower()
        except Exception:
            return False

    def _open_input_stream(self, **extra_kwargs) -> sd.InputStream:
        """Open an InputStream with the best available settings for the device.

        WASAPI extra_settings are only applied when the device is actually a
        WASAPI device — applying them to MME/DirectSound devices causes
        PaErrorCode -9984 (incompatible host API stream info).
        For non-WASAPI devices (MME, DirectSound) no extra settings are needed;
        Windows resamples to the requested sample rate automatically.
        """
        base: dict = dict(
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype="int16",
            blocksize=self._chunk_size,
            device=self._device_index,
            **extra_kwargs,
        )
        attempts: list[dict] = []
        if self._is_wasapi_device():
            try:
                attempts.append({"extra_settings": sd.WasapiSettings(exclusive=True)})
            except Exception:
                pass
            try:
                attempts.append({"extra_settings": sd.WasapiSettings(exclusive=False)})
            except Exception:
                pass
        attempts.append({})  # plain — always works for MME/DirectSound

        last_exc: Exception = RuntimeError("no attempts made")
        for extra in attempts:
            try:
                return sd.InputStream(**{**base, **extra})
            except Exception as exc:
                last_exc = exc
        raise AudioInputError(f"[C.Y.R.U.S] Cannot open microphone: {last_exc}") from last_exc

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def open(self) -> None:
        self._device_index = self._resolve_device()
        logger.info(f"[C.Y.R.U.S] AudioInput: opened device index={self._device_index}")
        self._calibrate_noise_floor()

    def close(self) -> None:
        logger.info("[C.Y.R.U.S] AudioInput: closed")

    def __enter__(self) -> "AudioInput":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ── Device resolution ─────────────────────────────────────────────────────
    def _resolve_device(self) -> Optional[int]:
        if self._device_name in ("default", ""):
            return None
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if (self._device_name.lower() in dev["name"].lower()
                    and dev["max_input_channels"] > 0):
                logger.info(f"[C.Y.R.U.S] AudioInput: matched '{dev['name']}' at index {i}")
                return i
        logger.warning(
            f"[C.Y.R.U.S] AudioInput: device '{self._device_name}' not found; using default"
        )
        return None

    def list_devices(self) -> list[dict]:
        return [
            {"index": i, "name": d["name"]}
            for i, d in enumerate(sd.query_devices())
            if d["max_input_channels"] > 0
        ]

    # ── Noise floor calibration ───────────────────────────────────────────────
    def _calibrate_noise_floor(self, duration: Optional[float] = None) -> None:
        secs = duration or self._noise_calibration_secs
        n_frames = int(self._sample_rate * secs)
        logger.info(f"[C.Y.R.U.S] AudioInput: calibrating noise floor ({secs:.1f}s)…")
        try:
            stream = self._open_input_stream()
            with stream:
                data, _ = stream.read(n_frames)
            pcm = data.tobytes()
            self._noise_floor = self._rms(pcm)
            logger.info(f"[C.Y.R.U.S] AudioInput: noise floor = {self._noise_floor:.1f} RMS")
            if self._noise_floor == 0.0:
                logger.warning(
                    "[C.Y.R.U.S] AudioInput: noise floor is ZERO — microphone may be muted, "
                    "powered off, or the USB wireless headset is not connected to its dongle. "
                    "Check that the headset is turned on and paired."
                )
        except Exception as exc:
            logger.warning(f"[C.Y.R.U.S] AudioInput: calibration failed ({exc}) — using config threshold")
            self._noise_floor = 0.0

    @property
    def _effective_threshold(self) -> float:
        """Dynamic threshold = max(config, noise_floor × gate_factor)."""
        gate = self._noise_floor * self._noise_gate_factor
        return max(self._silence_threshold, gate)

    # ── Control ───────────────────────────────────────────────────────────────
    def request_stop(self) -> None:
        self._stop_flag.set()

    def mute_for(self, seconds: float) -> None:
        self._muted_until = time.monotonic() + seconds
        logger.debug(f"[C.Y.R.U.S] AudioInput: muted for {seconds:.1f}s")

    def set_voice_profile(self, profile: object) -> None:
        self._voice_profile = profile
        logger.info("[C.Y.R.U.S] AudioInput: voice profile attached")

    def verify_speaker(self, pcm: bytes) -> bool:
        """Returns True if pcm matches enrolled voice, or no profile loaded."""
        if not self._speaker_gate_enabled or self._voice_profile is None:
            return True
        return self._voice_profile.is_match(pcm)

    # ── Recording ─────────────────────────────────────────────────────────────
    async def record_utterance(self) -> bytes:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._record_sync)

    def _record_sync(self) -> bytes:
        # Auto-recalibrate if idle too long
        now = time.monotonic()
        if (self._last_speech_at > 0
                and now - self._last_speech_at > self._RECALIB_IDLE_SECS):
            self._calibrate_noise_floor(duration=1.0)
            self._last_speech_at = now

        threshold = self._effective_threshold
        stream = self._open_input_stream()

        # ── Diagnostic: log device info once per open ────────────────────
        try:
            dev_info = sd.query_devices(self._device_index)
            host_api = sd.query_hostapis(dev_info["hostapi"])["name"]
            logger.info(
                f"[C.Y.R.U.S] AudioInput: stream opened — device='{dev_info['name']}' "
                f"idx={self._device_index} api={host_api} "
                f"sr={self._sample_rate} threshold={threshold:.0f}"
            )
        except Exception:
            pass

        stream.start()

        self._vad.reset()
        self._stop_flag.clear()
        frames: list[bytes] = []
        silence_count = 0
        speech_started = False
        pre_roll: list[bytes] = []
        max_pre_roll = int(self._sample_rate / self._chunk_size * 0.3)

        # Diagnostic counters
        _diag_chunks = 0
        _diag_max_rms = 0
        _diag_vad_hits = 0
        _DIAG_INTERVAL = 50  # log summary every ~3 seconds (50×1024/16000)

        try:
            while True:
                if self._stop_flag.is_set():
                    self._stop_flag.clear()
                    break

                raw, overflowed = stream.read(self._chunk_size)
                data = raw.tobytes()
                is_speech = self._vad.feed(data)
                rms = self._rms(data)

                _diag_chunks += 1
                _diag_max_rms = max(_diag_max_rms, rms)
                if is_speech:
                    _diag_vad_hits += 1

                # Periodic diagnostic log — INFO so it always appears
                if _diag_chunks % _DIAG_INTERVAL == 0:
                    muted = time.monotonic() < self._muted_until
                    logger.info(
                        f"[C.Y.R.U.S] AudioInput: chunks={_diag_chunks} "
                        f"max_rms={_diag_max_rms} vad_hits={_diag_vad_hits} "
                        f"threshold={threshold:.0f} muted={muted} speech_started={speech_started}"
                    )
                    if _diag_max_rms == 0 and _diag_chunks <= _DIAG_INTERVAL * 3:
                        logger.warning(
                            "[C.Y.R.U.S] AudioInput: ZERO audio — headset apagado/sin conexión "
                            "al dongle, mute físico activo, o nivel de entrada en 0% en Windows."
                        )
                    _diag_max_rms = 0
                    _diag_vad_hits = 0

                if not speech_started:
                    pre_roll.append(data)
                    if len(pre_roll) > max_pre_roll:
                        pre_roll.pop(0)

                if time.monotonic() < self._muted_until:
                    continue

                if is_speech and rms > threshold:
                    if not speech_started:
                        speech_started = True
                        frames.extend(pre_roll)
                        self._last_speech_at = time.monotonic()
                        logger.info(
                            f"[C.Y.R.U.S] AudioInput: speech onset "
                            f"rms={rms} threshold={threshold:.0f} vad=True"
                        )
                    silence_count = 0
                    frames.append(data)
                elif speech_started:
                    frames.append(data)
                    silence_count += 1
                    if silence_count >= self._silence_frames:
                        logger.info(
                            f"[C.Y.R.U.S] AudioInput: utterance end "
                            f"frames={len(frames)} bytes={len(frames)*self._chunk_size*2}"
                        )
                        break
        finally:
            stream.stop()
            stream.close()

        return b"".join(frames)

    # ── Barge-in detection ────────────────────────────────────────────────────
    async def detect_speech_onset(self, timeout: float = 30.0) -> bool:
        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self._detect_onset_sync),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return False

    def _detect_onset_sync(self) -> bool:
        barge_rms = self._effective_threshold * 2.0
        CONSECUTIVE_REQUIRED = 4
        consecutive = 0
        collected: list[bytes] = []
        vad = VADDetector(sample_rate=self._sample_rate, aggressiveness=3, speech_ratio=0.85)

        try:
            stream = self._open_input_stream()
            stream.start()
        except Exception as exc:
            logger.warning(f"[C.Y.R.U.S] AudioInput: barge-in stream failed: {exc}")
            return False

        try:
            while True:
                if self._stop_flag.is_set():
                    return False
                raw, _ = stream.read(self._chunk_size)
                data = raw.tobytes()

                if time.monotonic() < self._muted_until:
                    consecutive = 0
                    collected.clear()
                    continue

                is_speech = vad.feed(data)
                rms = self._rms(data)

                if is_speech and rms > barge_rms:
                    consecutive += 1
                    collected.append(data)
                    if consecutive >= CONSECUTIVE_REQUIRED:
                        if self._voice_profile is not None:
                            if not self._voice_profile.is_match(b"".join(collected)):
                                consecutive = 0
                                collected.clear()
                                vad.reset()
                                continue
                        return True
                else:
                    if consecutive > 0:
                        consecutive -= 1
                    if consecutive == 0:
                        collected.clear()
        finally:
            stream.stop()
            stream.close()

    # ── Utilities ─────────────────────────────────────────────────────────────
    @staticmethod
    def _rms(pcm: bytes) -> float:
        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        if arr.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(arr ** 2)))

    def pcm_to_wav(self, pcm: bytes) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self._channels)
            wf.setsampwidth(2)
            wf.setframerate(self._sample_rate)
            wf.writeframes(pcm)
        return buf.getvalue()
