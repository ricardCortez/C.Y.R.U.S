"""
JARVIS — Tests for AudioInput / AudioOutput.

Hardware-dependent tests are skipped unless a real microphone is detected.
"""

import io
import struct
import wave

import pytest

from backend.modules.audio.audio_input import AudioInput
from backend.modules.audio.vad_detector import VADDetector


class TestVADDetector:
    """Unit tests for VADDetector — no hardware required."""

    def _make_pcm(self, n_frames: int, amplitude: int = 0) -> bytes:
        """Generate silent (amplitude=0) or noisy PCM frames."""
        return struct.pack(f"<{n_frames}h", *([amplitude] * n_frames))

    def test_init_valid(self):
        vad = VADDetector(sample_rate=16000, frame_duration_ms=30)
        assert vad.frame_bytes == 960  # 16000 * 0.03 * 2

    def test_init_invalid_rate(self):
        with pytest.raises(ValueError):
            VADDetector(sample_rate=12345)

    def test_init_invalid_frame_ms(self):
        with pytest.raises(ValueError):
            VADDetector(frame_duration_ms=25)

    def test_silence_not_speech(self):
        vad = VADDetector(sample_rate=16000, frame_duration_ms=30)
        silence = self._make_pcm(960, amplitude=0)
        for _ in range(15):
            result = vad.feed(silence)
        assert result is False

    def test_reset_clears_state(self):
        vad = VADDetector(sample_rate=16000, frame_duration_ms=30)
        vad._triggered = True
        vad.reset()
        assert vad._triggered is False


class TestPCMToWAV:
    """Test the PCM→WAV helper (no hardware)."""

    def test_pcm_to_wav_valid(self):
        ai = AudioInput(sample_rate=16000)
        pcm = b"\x00\x00" * 16000  # 1 second of silence
        wav = ai.pcm_to_wav(pcm)
        buf = io.BytesIO(wav)
        with wave.open(buf, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000

    def test_pcm_to_wav_empty(self):
        ai = AudioInput()
        wav = ai.pcm_to_wav(b"")
        assert len(wav) > 0  # Still valid WAV header


class TestAudioInputDeviceList:
    """List devices (no recording, no hardware failures expected)."""

    def test_list_devices_returns_list(self):
        ai = AudioInput()
        try:
            devices = ai.list_devices()
            assert isinstance(devices, list)
        except Exception:
            pytest.skip("PyAudio not available in this environment")


class TestDenoiser:
    """Unit tests for Denoiser — spectral noise reduction."""

    def test_denoiser_returns_same_length(self):
        from backend.modules.audio.denoiser import Denoiser
        import numpy as np
        d = Denoiser(sample_rate=16000)
        pcm = (np.random.randn(16000) * 100).astype(np.int16).tobytes()
        result = d.process(pcm)
        assert len(result) == len(pcm)

    def test_denoiser_handles_empty(self):
        from backend.modules.audio.denoiser import Denoiser
        d = Denoiser(sample_rate=16000)
        result = d.process(b"")
        assert result == b""

    def test_denoiser_reduces_noise(self):
        from backend.modules.audio.denoiser import Denoiser
        import numpy as np
        d = Denoiser(sample_rate=16000)
        # Create pure noise signal
        noise = (np.random.randn(16000) * 500).astype(np.int16)
        pcm = noise.tobytes()
        result = d.process(pcm)
        result_arr = np.frombuffer(result, dtype=np.int16).astype(np.float32)
        noise_arr = noise.astype(np.float32)
        # RMS of result should be lower than input noise RMS
        assert np.sqrt(np.mean(result_arr**2)) < np.sqrt(np.mean(noise_arr**2))
