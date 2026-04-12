"""
C.Y.R.U.S — Anthropic Claude API fallback client.

Used when the local Ollama service is unavailable (HYBRID mode).
Requires the ``CLAUDE_API_KEY`` environment variable.
"""

from __future__ import annotations

import os
from typing import AsyncIterator, List, Optional

from backend.utils.exceptions import LLMAPIError
from backend.utils.logger import get_logger

logger = get_logger("cyrus.llm.claude")

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False
    logger.warning("[C.Y.R.U.S] anthropic package not installed; Claude API fallback unavailable")


class ClaudeClient:
    """Async wrapper around the Anthropic Messages API.

    Args:
        api_key: Anthropic API key (defaults to ``CLAUDE_API_KEY`` env var).
        model: Claude model ID.
        max_tokens: Maximum tokens to generate.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-opus-4-1",
        max_tokens: int = 500,
        timeout: int = 60,
    ) -> None:
        self._api_key = api_key or os.getenv("CLAUDE_API_KEY", "")
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._client: Optional["anthropic.AsyncAnthropic"] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _get_client(self) -> "anthropic.AsyncAnthropic":
        if not _ANTHROPIC_AVAILABLE:
            raise LLMAPIError("[C.Y.R.U.S] anthropic package not installed")
        if not self._api_key:
            raise LLMAPIError(
                "[C.Y.R.U.S] CLAUDE_API_KEY not set; Claude API fallback unavailable"
            )
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(
                api_key=self._api_key,
                timeout=self._timeout,
            )
        return self._client

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: List[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> str:
        """Send a request to the Claude API and return the response text.

        Args:
            messages: OpenAI-style list of ``{"role": ..., "content": ...}`` dicts.
            system_prompt: System instruction (placed in ``system`` parameter).
            temperature: Sampling temperature.

        Returns:
            Response text string.

        Raises:
            LLMAPIError: On API errors or missing credentials.
        """
        client = self._get_client()
        # Convert to Anthropic format (no "system" in messages list)
        anthropic_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] in ("user", "assistant")
        ]
        try:
            response = await client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt or "You are C.Y.R.U.S, a helpful AI assistant.",
                messages=anthropic_messages,
                temperature=temperature,
            )
            text = response.content[0].text if response.content else ""
            logger.info(f"[C.Y.R.U.S] Claude API: response received ({len(text)} chars)")
            return text
        except Exception as exc:
            raise LLMAPIError(f"[C.Y.R.U.S] Claude API error: {exc}") from exc

    async def chat_stream(
        self,
        messages: List[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """Stream tokens from the Claude API.

        Yields:
            Token strings as they arrive.
        """
        client = self._get_client()
        anthropic_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] in ("user", "assistant")
        ]
        try:
            async with client.messages.stream(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt or "You are C.Y.R.U.S, a helpful AI assistant.",
                messages=anthropic_messages,
                temperature=temperature,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:
            raise LLMAPIError(f"[C.Y.R.U.S] Claude API stream error: {exc}") from exc
