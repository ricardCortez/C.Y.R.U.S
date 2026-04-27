"""
JARVIS — Tests for TriggerDetector.

These tests are purely logic-based and require no hardware or models.
"""

import pytest
from backend.modules.nlp.trigger_detector import TriggerDetector


@pytest.fixture
def detector() -> TriggerDetector:
    return TriggerDetector(
        wake_words=["hola jarvis", "oye jarvis", "hey jarvis", "jarvis"],
        threshold=85,
        fuzzy_matching=True,
    )


class TestExactMatches:
    def test_hola_cyrus_detected(self, detector: TriggerDetector):
        triggered, clean = detector.detect("Hola JARVIS, ¿qué hora es?")
        assert triggered is True

    def test_hey_cyrus_detected(self, detector: TriggerDetector):
        triggered, _ = detector.detect("Hey Cyrus, what time is it?")
        assert triggered is True

    def test_standalone_cyrus(self, detector: TriggerDetector):
        triggered, _ = detector.detect("Cyrus")
        assert triggered is True

    def test_oye_cyrus_detected(self, detector: TriggerDetector):
        triggered, _ = detector.detect("Oye Cyrus, enciende las luces")
        assert triggered is True

    def test_case_insensitive(self, detector: TriggerDetector):
        triggered, _ = detector.detect("HOLA JARVIS")
        assert triggered is True

    def test_no_wake_word(self, detector: TriggerDetector):
        triggered, clean = detector.detect("What is the weather today?")
        assert triggered is False
        assert clean == ""

    def test_empty_transcript(self, detector: TriggerDetector):
        triggered, clean = detector.detect("")
        assert triggered is False
        assert clean == ""


class TestInputExtraction:
    def test_extracts_intent_after_hola_cyrus(self, detector: TriggerDetector):
        _, clean = detector.detect("Hola cyrus, ¿qué hora es?")
        assert "hora" in clean.lower()

    def test_extracts_intent_after_hey_cyrus(self, detector: TriggerDetector):
        _, clean = detector.detect("Hey cyrus what time is it")
        assert "time" in clean.lower()

    def test_standalone_cyrus_empty_intent(self, detector: TriggerDetector):
        triggered, _ = detector.detect("jarvis")
        assert triggered is True

    def test_clean_has_no_wake_word(self, detector: TriggerDetector):
        _, clean = detector.detect("hola jarvis open the garage")
        assert "jarvis" not in clean.lower()

    def test_long_sentence_intent_preserved(self, detector: TriggerDetector):
        _, clean = detector.detect("Hey cyrus, please turn off all the lights in the living room")
        assert "lights" in clean.lower() or "living" in clean.lower()


class TestFuzzyMatching:
    def test_fuzzy_typo(self, detector: TriggerDetector):
        # "hola cirrus" is close enough
        triggered, _ = detector.detect("hola cirrus, help me")
        assert triggered is True

    def test_fuzzy_disabled(self):
        strict = TriggerDetector(
            wake_words=["hola jarvis"],
            threshold=85,
            fuzzy_matching=False,
        )
        triggered, _ = strict.detect("hola cirrus help")
        assert triggered is False

    def test_very_different_string_not_triggered(self, detector: TriggerDetector):
        triggered, _ = detector.detect("turn off the lights please")
        assert triggered is False


class TestEdgeCases:
    def test_none_raises(self, detector: TriggerDetector):
        from backend.utils.exceptions import TriggerDetectionError
        with pytest.raises(TriggerDetectionError):
            detector.detect(None)  # type: ignore

    def test_whitespace_only(self, detector: TriggerDetector):
        triggered, clean = detector.detect("   ")
        assert triggered is False

    def test_add_wake_word(self, detector: TriggerDetector):
        detector.add_wake_word("yo cyrus")
        triggered, _ = detector.detect("Yo cyrus, hola")
        assert triggered is True
