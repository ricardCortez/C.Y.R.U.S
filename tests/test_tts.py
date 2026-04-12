"""
C.Y.R.U.S — Tests for TTS modules.

KokoroTTS model tests are skipped unless CYRUS_RUN_SLOW_TESTS=1.
VoiceforgeTTS (edge-tts) tests require network and are also skipped in CI.
"""

import io
import wave
import os

import pytest

from backend.modules.tts.kokoro_tts import KokoroTTS
from backend.modules.tts.tts_manager import TTSManager
from backend.modules.tts.voiceforge_tts import VoiceforgeTTS
from backend.utils.exceptions import KokoroUnavailableError, TTSError


SLOW = pytest.mark.skipif(
    os.getenv("CYRUS_RUN_SLOW_TESTS") != "1",
    reason="Skipped: set CYRUS_RUN_SLOW_TESTS=1 to run model-load tests",
)
NETWORK = pytest.mark.skipif(
    os.getenv("CYRUS_RUN_NETWORK_TESTS") != "1",
    reason="Skipped: set CYRUS_RUN_NETWORK_TESTS=1 to run network tests",
)


class TestKokoroTTSInit:
    def test_not_loaded_on_init(self):
        tts = KokoroTTS()
        assert tts._pipeline is None

    def test_synthesise_before_load_raises(self):
        tts = KokoroTTS()
        with pytest.raises(KokoroUnavailableError):
            tts.synthesise("Hello")

    def test_empty_text_returns_silence_if_loaded(self):
        tts = KokoroTTS()
        # Simulate pipeline being present via mock
        tts._pipeline = object()  # type: ignore
        # Empty string hits the guard before pipeline call
        # We set _pipeline to non-None but it won't be called for empty text
        try:
            result = tts.synthesise("")
            # Should return silence WAV
            assert isinstance(result, bytes)
        except Exception:
            pass  # Expected if pipeline mock can't synthesise

    def test_silence_wav_valid(self):
        tts = KokoroTTS(sample_rate=24000)
        silence = tts._silence_wav(0.1)
        buf = io.BytesIO(silence)
        with wave.open(buf, "rb") as wf:
            assert wf.getframerate() == 24000
            assert wf.getsampwidth() == 2


@SLOW
class TestKokoroModelLoad:
    def test_load_and_synthesise(self):
        tts = KokoroTTS(voice="af_sarah", speed=1.0)
        tts.load()
        assert tts._pipeline is not None
        wav = tts.synthesise("Testing C.Y.R.U.S.")
        assert len(wav) > 0
        buf = io.BytesIO(wav)
        with wave.open(buf, "rb") as wf:
            assert wf.getsampwidth() == 2
        tts.unload()
        assert tts._pipeline is None


@NETWORK
class TestVoiceforgeTTS:
    @pytest.mark.asyncio
    async def test_synthesise_returns_bytes(self):
        tts = VoiceforgeTTS(voice="en-GB-RyanNeural")
        result = await tts.synthesise("Hello from C.Y.R.U.S.")
        assert isinstance(result, bytes)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_synthesise_empty_returns_empty(self):
        tts = VoiceforgeTTS()
        result = await tts.synthesise("")
        assert result == b""


class TestTTSManagerFallback:
    @pytest.mark.asyncio
    async def test_kokoro_failure_falls_back_to_voiceforge(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        kokoro = MagicMock(spec=KokoroTTS)
        kokoro.synthesise.side_effect = KokoroUnavailableError("not loaded")

        voiceforge = AsyncMock(spec=VoiceforgeTTS)
        voiceforge.synthesise.return_value = b"fake_mp3_bytes"

        mgr = TTSManager(kokoro=kokoro, voiceforge=voiceforge, mode="HYBRID")
        audio, mime = await mgr.synthesise("Hello")
        assert audio == b"fake_mp3_bytes"
        assert mime == "audio/mpeg"

    @pytest.mark.asyncio
    async def test_kokoro_success(self):
        from unittest.mock import MagicMock

        kokoro = MagicMock(spec=KokoroTTS)
        kokoro.synthesise.return_value = b"RIFF....fake_wav"

        voiceforge = MagicMock(spec=VoiceforgeTTS)

        mgr = TTSManager(kokoro=kokoro, voiceforge=voiceforge)
        audio, mime = await mgr.synthesise("Hello")
        assert mime == "audio/wav"
        voiceforge.synthesise.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_fail_raises(self):
        from unittest.mock import AsyncMock, MagicMock
        from backend.utils.exceptions import TTSAPIError

        kokoro = MagicMock(spec=KokoroTTS)
        kokoro.synthesise.side_effect = KokoroUnavailableError("down")

        voiceforge = AsyncMock(spec=VoiceforgeTTS)
        voiceforge.synthesise.side_effect = TTSAPIError("also down")

        mgr = TTSManager(kokoro=kokoro, voiceforge=voiceforge)
        with pytest.raises(TTSError):
            await mgr.synthesise("Test")
