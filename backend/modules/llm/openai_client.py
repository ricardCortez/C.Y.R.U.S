"""
CYRUS — OpenAI API client.

Compatible with any OpenAI-style endpoint (OpenAI, Groq, etc.).
Subclass and override base_url to target a different provider.
"""

from __future__ import annotations

import time
from typing import List, Optional

from backend.utils.exceptions import LLMAPIError
from backend.utils.logger import get_logger

logger = get_logger("jarvis.llm.openai")

try:
    from openai import AsyncOpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False
    logger.warning("[CYRUS] openai package not installed; OpenAI API unavailable")


class OpenAIClient:
    """Async wrapper around the OpenAI Chat Completions API.

    Args:
        api_key: OpenAI API key.
        model: Model ID (e.g. 'gpt-4o-mini').
        base_url: Override endpoint URL (for Groq or other compatible APIs).
        max_tokens: Maximum tokens to generate.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
        max_tokens: int = 500,
        timeout: int = 60,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> "AsyncOpenAI":
        if not _OPENAI_AVAILABLE:
            raise LLMAPIError("[CYRUS] openai package not installed — run: pip install openai")
        if not self._api_key:
            raise LLMAPIError("[CYRUS] OpenAI API key not set")
        if self._client is None:
            kwargs: dict = {"api_key": self._api_key, "timeout": self._timeout}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    def _invalidate_client(self) -> None:
        self._client = None

    async def chat(
        self,
        messages: List[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> str:
        """Send a chat completion request and return response text.

        Args:
            messages: OpenAI-style list of {role, content} dicts.
            system_prompt: Injected as the first system message.
            temperature: Sampling temperature.

        Returns:
            Response text string.

        Raises:
            LLMAPIError: On API errors or missing credentials.
        """
        client = self._get_client()
        openai_messages: List[dict] = []
        if system_prompt:
            openai_messages.append({"role": "system", "content": system_prompt})
        openai_messages.extend(
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] in ("user", "assistant")
        )
        try:
            response = await client.chat.completions.create(
                model=self._model,
                messages=openai_messages,
                max_tokens=self._max_tokens,
                temperature=temperature,
            )
            text = response.choices[0].message.content or ""
            logger.info(f"[CYRUS] OpenAI: response received ({len(text)} chars)")
            return text
        except Exception as exc:
            raise LLMAPIError(f"[CYRUS] OpenAI API error: {exc}") from exc

    async def test_connectivity(self) -> dict:
        """Send a minimal ping request to verify credentials and connectivity.

        Returns:
            {"ok": bool, "latency_ms": int, "error": str}
        """
        start = time.monotonic()
        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
                temperature=0,
            )
            latency = int((time.monotonic() - start) * 1000)
            _ = response.choices[0].message.content
            return {"ok": True, "latency_ms": latency, "error": ""}
        except LLMAPIError as exc:
            return {"ok": False, "latency_ms": 0, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "latency_ms": 0, "error": str(exc)}
