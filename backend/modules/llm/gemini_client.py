"""
CYRUS — Google Gemini API client.

Uses google-generativeai SDK. Converts OpenAI-style message lists to
Gemini's Content format (roles: user / model).
"""

from __future__ import annotations

import asyncio
import time
from typing import List

from backend.utils.exceptions import LLMAPIError
from backend.utils.logger import get_logger

logger = get_logger("jarvis.llm.gemini")

try:
    import google.generativeai as genai
    _GEMINI_AVAILABLE = True
except ImportError:
    _GEMINI_AVAILABLE = False
    logger.warning("[CYRUS] google-generativeai not installed; Gemini API unavailable")


class GeminiClient:
    """Async wrapper around the Google Gemini GenerativeModel API.

    Args:
        api_key: Google AI Studio API key.
        model: Model ID (e.g. 'gemini-2.0-flash').
        max_tokens: Maximum output tokens.
        timeout: Request timeout in seconds (applied via asyncio.wait_for).
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "gemini-2.0-flash",
        max_tokens: int = 500,
        timeout: int = 60,
    ) -> None:
        self._api_key = api_key
        self._model_name = model
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._model = None

    def _get_model(self):
        if not _GEMINI_AVAILABLE:
            raise LLMAPIError("[CYRUS] google-generativeai not installed — run: pip install google-generativeai")
        if not self._api_key:
            raise LLMAPIError("[CYRUS] Gemini API key not set")
        if self._model is None:
            genai.configure(api_key=self._api_key)
            self._model = genai.GenerativeModel(self._model_name)
        return self._model

    @staticmethod
    def _convert_messages(messages: List[dict], system_prompt: str) -> tuple[list, str]:
        """Convert OpenAI-style messages to Gemini Content list.

        Returns:
            (gemini_history, last_user_message)
        """
        history = []
        last_user = ""
        for m in messages:
            role = m["role"]
            content = m["content"]
            if role == "system":
                continue
            gemini_role = "user" if role == "user" else "model"
            if role == "user":
                last_user = content
            history.append({"role": gemini_role, "parts": [content]})
        # Pop last user message — it goes to send_message, not history
        if history and history[-1]["role"] == "user":
            history = history[:-1]
        return history, last_user

    async def chat(
        self,
        messages: List[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> str:
        """Send a chat request to Gemini and return the response text.

        Args:
            messages: OpenAI-style list of {role, content} dicts.
            system_prompt: Prepended as system_instruction on the model.
            temperature: Sampling temperature.

        Returns:
            Response text string.

        Raises:
            LLMAPIError: On API errors or missing credentials.
        """
        model = self._get_model()
        if system_prompt:
            genai.configure(api_key=self._api_key)
            model = genai.GenerativeModel(
                self._model_name,
                system_instruction=system_prompt,
            )

        history, last_user = self._convert_messages(messages, system_prompt)
        if not last_user:
            raise LLMAPIError("[CYRUS] Gemini: no user message found")

        gen_config = genai.GenerationConfig(
            max_output_tokens=self._max_tokens,
            temperature=temperature,
        )
        try:
            chat_session = model.start_chat(history=history)
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: chat_session.send_message(last_user, generation_config=gen_config),
                ),
                timeout=self._timeout,
            )
            text = response.text or ""
            logger.info(f"[CYRUS] Gemini: response received ({len(text)} chars)")
            return text
        except asyncio.TimeoutError:
            raise LLMAPIError(f"[CYRUS] Gemini timeout after {self._timeout}s")
        except Exception as exc:
            raise LLMAPIError(f"[CYRUS] Gemini API error: {exc}") from exc

    async def test_connectivity(self) -> dict:
        """Send a minimal ping to verify API key and connectivity.

        Returns:
            {"ok": bool, "latency_ms": int, "error": str}
        """
        start = time.monotonic()
        try:
            await self.chat(
                messages=[{"role": "user", "content": "ping"}],
                system_prompt="",
                temperature=0,
            )
            return {"ok": True, "latency_ms": int((time.monotonic() - start) * 1000), "error": ""}
        except LLMAPIError as exc:
            return {"ok": False, "latency_ms": 0, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "latency_ms": 0, "error": str(exc)}
