"""
JARVIS — Wake-word / trigger detector.

Scans a transcript for configured wake words using fuzzy string matching
(fuzzywuzzy) and extracts the clean user intent after the trigger phrase.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from fuzzywuzzy import fuzz

from backend.utils.exceptions import TriggerDetectionError
from backend.utils.logger import get_logger

logger = get_logger("jarvis.nlp.trigger")


class TriggerDetector:
    """Detects JARVIS wake words in a transcript.

    Args:
        wake_words: List of wake-word strings to search for.
        threshold: Minimum fuzzywuzzy partial_ratio score (0–100).
        fuzzy_matching: If ``False``, only exact substring match is used.
    """

    def __init__(
        self,
        wake_words: List[str] | None = None,
        threshold: int = 85,
        fuzzy_matching: bool = True,
    ) -> None:
        self._wake_words = [w.lower().strip() for w in (wake_words or [
            "hola jarvis", "oye jarvis", "hey jarvis", "jarvis"
        ])]
        self._threshold = threshold
        self._fuzzy = fuzzy_matching

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, transcript: str) -> Tuple[bool, str]:
        """Detect a wake word in *transcript* and extract the user's intent.

        Args:
            transcript: Raw text from the ASR module.

        Returns:
            ``(is_triggered, clean_input)`` — ``clean_input`` is the transcript
            with the wake-word phrase removed and whitespace stripped.

        Raises:
            TriggerDetectionError: If *transcript* is ``None``.
        """
        if transcript is None:
            raise TriggerDetectionError("[JARVIS] Trigger: transcript cannot be None")

        text = self._normalize(transcript.strip())
        if not text:
            return False, ""

        # Sort wake words longest-first so "hola jarvis" beats "jarvis" on overlap
        for wake_word in sorted(self._wake_words, key=len, reverse=True):
            triggered, clean = self._check_wake_word(text, wake_word, transcript)
            if triggered:
                logger.info(f"[JARVIS] Trigger detected: '{wake_word}' in '{transcript}'")
                return True, clean

        logger.debug(f"[JARVIS] No trigger found in: '{transcript}'")
        return False, ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_wake_word(
        self, lowered: str, wake_word: str, original: str
    ) -> Tuple[bool, str]:
        """Check a single wake word against the lowercased transcript.

        Returns:
            ``(matched, clean_input)``.
        """
        # Fast path: exact substring
        if wake_word in lowered:
            clean = self._strip_wake_word(lowered, wake_word, original)
            return True, clean

        if not self._fuzzy:
            return False, ""

        # Fuzzy partial match
        score = fuzz.partial_ratio(lowered, wake_word)
        if score >= self._threshold:
            clean = self._strip_wake_word(lowered, wake_word, original)
            return True, clean

        # Token-set ratio catches re-ordered words
        score_ts = fuzz.token_set_ratio(lowered, wake_word)
        if score_ts >= self._threshold and len(wake_word.split()) <= 2:
            clean = self._strip_wake_word(lowered, wake_word, original)
            return True, clean

        # WRatio — best-of-all scorer, handles typos well (e.g. "cirrus" → "jarvis")
        score_w = fuzz.WRatio(lowered, wake_word)
        if score_w >= self._threshold:
            clean = self._strip_wake_word(lowered, wake_word, original)
            return True, clean

        return False, ""

    @staticmethod
    def _strip_wake_word(lowered: str, wake_word: str, original: str) -> str:
        """Remove the wake word from the original transcript.

        Tries to preserve original casing for the remaining text.

        Args:
            lowered: Lowercased version of the transcript.
            wake_word: Lowercased wake word phrase.
            original: Original transcript (mixed case).

        Returns:
            Cleaned intent string.
        """
        # Find position in lowercased text and slice original accordingly
        idx = lowered.find(wake_word)
        if idx != -1:
            before = original[:idx].strip()
            after = original[idx + len(wake_word):].strip(" ,.-:!?")
            clean = (before + " " + after).strip() if before else after
        else:
            # Fuzzy hit — fall back to simple regex removal
            pattern = re.compile(re.escape(wake_word), re.IGNORECASE)
            clean = pattern.sub("", original).strip(" ,.-:!?")

        return clean.strip()

    @staticmethod
    def _normalize(text: str) -> str:
        """Lower-case *text* and collapse acronym dots (JARVIS → cyrus)."""
        # Remove dots between single letters: "c.y.r.u.s" → "jarvis"
        normalized = re.sub(r"(?<=[a-zA-Z])\.(?=[a-zA-Z])", "", text)
        return normalized.lower()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def wake_words(self) -> List[str]:
        """Currently registered wake words."""
        return list(self._wake_words)

    def remove_wake_word(self, word: str) -> None:
        """Remove a wake word at runtime."""
        normalised = word.lower().strip()
        if normalised in self._wake_words:
            self._wake_words.remove(normalised)
            logger.info(f"[JARVIS] Trigger: removed wake word '{normalised}'")

    def add_wake_word(self, word: str) -> None:
        """Register an additional wake word at runtime.

        Args:
            word: Wake word phrase to add.
        """
        normalised = word.lower().strip()
        if normalised not in self._wake_words:
            self._wake_words.append(normalised)
            logger.info(f"[JARVIS] Trigger: added wake word '{normalised}'")
