"""
C.Y.R.U.S — LLM Manager.

Orchestrates LOCAL (Ollama) and API (Claude) backends with automatic
fallback.  Injects the system prompt from ``soul.md`` and the conversation
context template from ``prompts.yaml``.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from backend.modules.llm.claude_client import ClaudeClient
from backend.modules.llm.ollama_client import OllamaClient
from backend.modules.vision.models import VisionContext
from backend.utils.exceptions import LLMError, OllamaUnavailableError
from backend.utils.helpers import retry_async
from backend.utils.logger import get_logger

logger = get_logger("cyrus.llm.manager")


class LLMManager:
    """Unified LLM interface with LOCAL → API fallback.

    Args:
        ollama: Pre-configured :class:`OllamaClient`.
        claude: Pre-configured :class:`ClaudeClient` (used as fallback).
        soul_text: Raw markdown from ``soul.md`` — the C.Y.R.U.S personality.
        prompts: Parsed ``prompts.yaml`` dict.
        mode: ``"LOCAL"`` or ``"HYBRID"`` (enables API fallback).
        temperature: Default sampling temperature.
        max_tokens: Default max response tokens.
    """

    def __init__(
        self,
        ollama: OllamaClient,
        claude: ClaudeClient,
        soul_text: str = "",
        prompts: dict | None = None,
        mode: str = "LOCAL",
        temperature: float = 0.7,
        max_tokens: int = 300,
    ) -> None:
        self._ollama = ollama
        self._claude = claude
        self._soul_text = soul_text
        self._prompts = prompts or {}
        self._mode = mode.upper()
        self._temperature = temperature
        self._max_tokens = max_tokens

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        user_input: str,
        history: List[dict] | None = None,
        language: str = "en",
        turn_count: int = 0,
        vision_context: Optional[VisionContext] = None,
        memory_context: str = "",
    ) -> str:
        """Generate a response to *user_input*.

        Args:
            user_input: Cleaned user intent text.
            history: Prior conversation turns (OpenAI-style message list).
            language: Detected language code (for context injection).
            turn_count: Conversation turn number.
            vision_context: Optional live camera scene description.
            memory_context: Relevant past turns from semantic memory search.

        Returns:
            C.Y.R.U.S response string.

        Raises:
            LLMError: If both local and API backends fail.
        """
        system_prompt = self._build_system_prompt(language, turn_count, vision_context, memory_context)
        messages = list(history or [])
        messages.append({"role": "user", "content": user_input})

        # Try local Ollama first
        try:
            logger.info("[C.Y.R.U.S] LLM: attempting local Ollama inference…")
            response = await self._ollama.chat(
                messages,
                system_prompt=system_prompt,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            if response.strip():
                logger.info(f"[C.Y.R.U.S] LLM: Ollama responded ({len(response)} chars)")
                return response.strip()
            logger.warning("[C.Y.R.U.S] LLM: Ollama returned empty response")
        except OllamaUnavailableError as exc:
            logger.warning(f"[C.Y.R.U.S] LLM: Ollama unavailable — {exc}")
        except LLMError as exc:
            logger.warning(f"[C.Y.R.U.S] LLM: Ollama error — {exc}")

        # Fallback to Claude API (only in HYBRID mode)
        if self._mode == "HYBRID":
            return await self._claude_fallback(messages, system_prompt)

        # Graceful degradation
        canned = self._prompts.get("canned", {}).get(
            "llm_unavailable",
            "I'm sorry, I'm currently unable to process your request. "
            "My reasoning engine appears to be offline.",
        )
        logger.error("[C.Y.R.U.S] LLM: all backends failed; returning canned response")
        return canned

    async def _claude_fallback(self, messages: List[dict], system_prompt: str) -> str:
        """Attempt Claude API with retry."""
        try:
            logger.info("[C.Y.R.U.S] LLM: falling back to Claude API…")
            response = await self._claude.chat(
                messages,
                system_prompt=system_prompt,
                temperature=self._temperature,
            )
            logger.info("[C.Y.R.U.S] LLM: Claude API responded")
            return response.strip()
        except Exception as exc:
            logger.error(f"[C.Y.R.U.S] LLM: Claude API also failed — {exc}")
            return (
                "I'm sorry, I'm experiencing difficulties with both my local and cloud "
                "reasoning engines. Please try again shortly."
            )

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_system_prompt(
        self,
        language: str,
        turn_count: int,
        vision_context: Optional[VisionContext] = None,
        memory_context: str = "",
    ) -> str:
        """Combine soul.md + context template + memory + vision into system prompt."""
        override = self._prompts.get("system_prompt_override")
        base = override if override else self._soul_text

        context_tpl: str = self._prompts.get("context_template", "")
        context = context_tpl.format(
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            language=language,
            turn_count=turn_count,
            system_mode=self._mode,
        ) if context_tpl else ""

        parts = [base, context]
        if memory_context:
            parts.append(memory_context)
        if vision_context:
            parts.append(vision_context.to_prompt_text())

        return "\n\n".join(p for p in parts if p.strip())
