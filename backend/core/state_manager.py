"""
JARVIS — Session State Manager.

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

logger = get_logger("jarvis.state")


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


_COMPRESS_AFTER = 20   # compress history when we exceed this many turns


class StateManager:
    """Centralised mutable state for the current JARVIS session.

    All write access should go through the provided methods so listeners
    (e.g. the WebSocket broadcaster) can be notified.
    """

    def __init__(self, max_history: int = 10) -> None:
        self._lock = asyncio.Lock()
        self.status: SystemStatus = SystemStatus.IDLE
        self.max_history = max_history
        self.history: List[Turn] = []
        self.session_summary: str = ""     # compressed summary of older turns
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
        logger.debug(f"[JARVIS] State: {prev.name} → {status.name}")

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

        If a rolling summary exists, it is prepended as a system-style user
        message so the LLM has context beyond the active window.

        Returns:
            List of ``{"role": ..., "content": ...}`` dicts.
        """
        msgs = [{"role": t.role, "content": t.content} for t in self.history]
        if self.session_summary:
            msgs = [{"role": "user",      "content": f"[RESUMEN DE CONVERSACIÓN ANTERIOR]\n{self.session_summary}"},
                    {"role": "assistant", "content": "Entendido, tengo el contexto anterior."}] + msgs
        return msgs

    async def maybe_compress(self, ollama_client) -> None:
        """Compress old turns into a rolling summary when history grows large.

        Called once per turn. When the raw turn count exceeds _COMPRESS_AFTER,
        the oldest half of turns is summarised via Ollama and replaced by the
        summary string stored in self.session_summary.
        """
        async with self._lock:
            if len(self.history) <= _COMPRESS_AFTER:
                return
            # Split: compress the older half, keep the recent half in full
            split = len(self.history) // 2
            old_turns = self.history[:split]
            self.history = self.history[split:]

        # Build text block of old turns for summarisation
        block = "\n".join(
            f"{t.role.upper()}: {t.content}" for t in old_turns
        )
        prompt = (
            "Resume en 5 puntos clave (bullet •) la siguiente conversación entre "
            "Ricardo y JARVIS. Sé conciso, incluye decisiones tomadas, preferencias "
            "expresadas y contexto técnico relevante.\n\n" + block
        )
        try:
            summary = await ollama_client.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="Eres un asistente que resume conversaciones en español.",
                temperature=0.3,
                max_tokens=300,
            )
            async with self._lock:
                # Prepend to existing summary
                if self.session_summary:
                    self.session_summary = self.session_summary + "\n\n" + summary
                else:
                    self.session_summary = summary
            logger.info("[JARVIS] State: session history compressed into rolling summary")
        except Exception as exc:
            logger.warning(f"[JARVIS] State: compression failed — {exc}")

    async def clear_history(self) -> None:
        """Wipe conversation history (e.g. on session reset)."""
        async with self._lock:
            self.history.clear()
            self.session_summary = ""
            self.turn_count = 0
        logger.info("[JARVIS] State: conversation history cleared")
