"""
C.Y.R.U.S — Session State Manager.

Holds per-session state (conversation history, system status) that modules
read and write.  Thread-safe via asyncio.Lock.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import List

from backend.utils.logger import get_logger

logger = get_logger("cyrus.state")


class SystemStatus(Enum):
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    SPEAKING = auto()
    ERROR = auto()


@dataclass
class Turn:
    """One conversational exchange."""
    role: str          # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    language: str = "en"


class StateManager:
    """Centralised mutable state for the current C.Y.R.U.S session.

    All write access should go through the provided methods so listeners
    (e.g. the WebSocket broadcaster) can be notified.
    """

    def __init__(self, max_history: int = 10) -> None:
        self._lock = asyncio.Lock()
        self.status: SystemStatus = SystemStatus.IDLE
        self.max_history = max_history
        self.history: List[Turn] = []
        self.turn_count: int = 0
        self.last_transcript: str = ""
        self.last_response: str = ""
        self.language_detected: str = "en"

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def set_status(self, status: SystemStatus) -> None:
        """Update system status.

        Args:
            status: New :class:`SystemStatus` value.
        """
        async with self._lock:
            prev = self.status
            self.status = status
        logger.debug(f"[C.Y.R.U.S] State: {prev.name} → {status.name}")

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    async def add_turn(self, role: str, content: str, language: str = "en") -> None:
        """Append a turn to conversation history, respecting max_history.

        Args:
            role: ``"user"`` or ``"assistant"``.
            content: Text of the turn.
            language: Detected language code (e.g. ``"es"``, ``"en"``).
        """
        turn = Turn(role=role, content=content, language=language)
        async with self._lock:
            self.history.append(turn)
            if len(self.history) > self.max_history * 2:
                # Keep last N *pairs* (user + assistant)
                self.history = self.history[-(self.max_history * 2):]
            self.turn_count += 1
            if role == "user":
                self.last_transcript = content
                self.language_detected = language
            else:
                self.last_response = content

    def get_history_for_llm(self) -> List[dict]:
        """Return history formatted as OpenAI-style messages list.

        Returns:
            List of ``{"role": ..., "content": ...}`` dicts.
        """
        return [{"role": t.role, "content": t.content} for t in self.history]

    async def clear_history(self) -> None:
        """Wipe conversation history (e.g. on session reset)."""
        async with self._lock:
            self.history.clear()
            self.turn_count = 0
        logger.info("[C.Y.R.U.S] State: conversation history cleared")
