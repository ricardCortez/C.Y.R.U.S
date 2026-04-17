"""Tests for SpeakerIntelligence ECAPA-TDNN module."""
import numpy as np
import pytest
from pathlib import Path
import tempfile


def _make_pcm(seconds: float = 2.0, sr: int = 16000) -> bytes:
    """Generate synthetic speech-like PCM (sine wave burst)."""
    t = np.linspace(0, seconds, int(sr * seconds))
    wave = (np.sin(2 * np.pi * 200 * t) * 8000).astype(np.int16)
    return wave.tobytes()


def test_speaker_intelligence_imports():
    from backend.modules.audio.speaker_intelligence import (
        SpeakerIntelligence, SpeakerRole, SpeakerResult
    )
    assert SpeakerRole.OWNER.value == "owner"
    assert SpeakerRole.GUEST.value == "guest"
    assert SpeakerRole.UNKNOWN.value == "unknown"


def test_identify_returns_unknown_without_profiles(tmp_path):
    from backend.modules.audio.speaker_intelligence import (
        SpeakerIntelligence, SpeakerRole
    )
    si = SpeakerIntelligence(
        data_dir=str(tmp_path),
        model_dir=str(tmp_path / "model"),
        threshold=0.82,
    )
    # Don't load the real model — test the fallback path
    pcm = _make_pcm()
    result = si.identify(pcm)
    assert result.role == SpeakerRole.UNKNOWN
    assert result.confidence == 0.0


def test_list_speakers_empty(tmp_path):
    from backend.modules.audio.speaker_intelligence import SpeakerIntelligence
    si = SpeakerIntelligence(
        data_dir=str(tmp_path),
        model_dir=str(tmp_path / "model"),
        threshold=0.82,
    )
    assert si.list_speakers() == []


def test_remove_nonexistent_speaker_does_not_raise(tmp_path):
    from backend.modules.audio.speaker_intelligence import SpeakerIntelligence
    si = SpeakerIntelligence(
        data_dir=str(tmp_path),
        model_dir=str(tmp_path / "model"),
        threshold=0.82,
    )
    si.remove_speaker("nobody")  # should not raise


def test_enroll_and_identify_owner(tmp_path, monkeypatch):
    """Enroll owner, then identify should return OWNER with mocked embedder."""
    from backend.modules.audio.speaker_intelligence import (
        SpeakerIntelligence, SpeakerRole
    )
    import numpy as np

    si = SpeakerIntelligence(
        data_dir=str(tmp_path),
        model_dir=str(tmp_path / "model"),
        threshold=0.60,
    )

    # Mock _embed to return a deterministic unit vector
    fixed_embed = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    monkeypatch.setattr(si, "_embed", lambda pcm: fixed_embed)

    # Enroll owner with 3 samples
    pcm_samples = [_make_pcm() for _ in range(3)]
    si.enroll(SpeakerRole.OWNER, "owner", pcm_samples)

    # Identify with same fixed embedding
    result = si.identify(_make_pcm())
    assert result.role == SpeakerRole.OWNER
    assert result.speaker_id == "owner"
    assert result.confidence >= 0.99


def test_enroll_guest_identified_as_guest(tmp_path, monkeypatch):
    from backend.modules.audio.speaker_intelligence import (
        SpeakerIntelligence, SpeakerRole
    )
    import numpy as np

    si = SpeakerIntelligence(
        data_dir=str(tmp_path),
        model_dir=str(tmp_path / "model"),
        threshold=0.60,
    )

    owner_embed = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    guest_embed = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    call_count = {"n": 0}

    def mock_embed(pcm):
        call_count["n"] += 1
        return guest_embed

    monkeypatch.setattr(si, "_embed", mock_embed)
    si.enroll(SpeakerRole.OWNER, "owner", [_make_pcm()])

    # Override owner embedding manually to owner vector
    si._profiles["owner"]["embedding"] = owner_embed

    si.enroll(SpeakerRole.GUEST, "carlos", [_make_pcm()])
    result = si.identify(_make_pcm())
    assert result.role == SpeakerRole.GUEST
    assert result.speaker_id == "carlos"
