"""
JARVIS — Ollama LLM client.

Communicates with the local Ollama service to run Mistral 7B inference.
Supports streaming responses and detects service unavailability.
"""

from __future__ import annotations

import json
from typing import AsyncIterator, List, Optional

import httpx

from backend.utils.exceptions import OllamaUnavailableError, LLMError
from backend.utils.logger import get_logger

logger = get_logger("jarvis.llm.ollama")


class OllamaClient:
    """Async HTTP client for the Ollama inference API.

    Args:
        host: Base URL of the Ollama service (e.g. ``"http://localhost:11434"``).
        model: Model name (e.g. ``"mistral:latest"``).
        timeout: Request timeout in seconds.
        stream: Whether to use streaming responses.
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "mistral:latest",
        timeout: int = 30,
        stream: bool = True,
    ) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._stream = stream

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        """Return ``True`` if the Ollama service responds to a ping.

        Returns:
            Availability flag.
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._host}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[dict]:
        """Return the list of installed Ollama models.

        Returns:
            A list of model metadata dictionaries.
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._host}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return [item for item in data if isinstance(item, dict)]
                if isinstance(data, dict) and "models" in data and isinstance(data["models"], list):
                    return [item for item in data["models"] if isinstance(item, dict)]
                return []
        except Exception as exc:
            raise OllamaUnavailableError(f"[JARVIS] Could not list Ollama models: {exc}") from exc

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: List[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 300,
    ) -> str:
        """Send a chat request and return the full response text.

        Args:
            messages: OpenAI-style list of ``{"role": ..., "content": ...}`` dicts.
            system_prompt: System instruction prepended to the conversation.
            temperature: Sampling temperature 0.0–1.0.
            max_tokens: Upper bound on response tokens.

        Returns:
            Full response string.

        Raises:
            OllamaUnavailableError: If the service is unreachable.
            LLMError: On API-level errors.
        """
        if self._stream:
            chunks = []
            async for chunk in self.chat_stream(messages, system_prompt, temperature, max_tokens):
                chunks.append(chunk)
            return "".join(chunks)

        payload = self._build_payload(messages, system_prompt, temperature, max_tokens, stream=False)
        try:
            _timeout = httpx.Timeout(connect=10.0, read=self._timeout, write=30.0, pool=5.0)
            async with httpx.AsyncClient(timeout=_timeout) as client:
                resp = await client.post(f"{self._host}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data.get("message", {}).get("content", "")
        except httpx.ConnectError as exc:
            raise OllamaUnavailableError(
                f"[JARVIS] Ollama unavailable at {self._host}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            body = ""
            try:
                body = exc.response.text[:400]
            except Exception:
                pass
            raise LLMError(f"[JARVIS] Ollama HTTP error: {exc} | body: {body}") from exc
        except Exception as exc:
            raise LLMError(f"[JARVIS] Ollama unexpected error: {type(exc).__name__}: {exc}") from exc

    async def chat_stream(
        self,
        messages: List[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 300,
    ) -> AsyncIterator[str]:
        """Stream chat tokens from Ollama.

        Yields:
            Individual token strings as they arrive.

        Raises:
            OllamaUnavailableError: If the service is unreachable.
        """
        payload = self._build_payload(messages, system_prompt, temperature, max_tokens, stream=True)
        try:
            _timeout = httpx.Timeout(connect=10.0, read=self._timeout, write=30.0, pool=5.0)
            async with httpx.AsyncClient(timeout=_timeout) as client:
                async with client.stream("POST", f"{self._host}/api/chat", json=payload) as resp:
                    resp.raise_for_status()
                    _in_think = False
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                # Strip <think>...</think> blocks emitted by reasoning models
                                if "<think>" in token:
                                    _in_think = True
                                if _in_think:
                                    if "</think>" in token:
                                        _in_think = False
                                        token = token[token.index("</think>") + len("</think>"):]
                                    else:
                                        continue
                                if token.strip():
                                    yield token
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError as exc:
            raise OllamaUnavailableError(
                f"[JARVIS] Ollama unavailable at {self._host}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            body = ""
            try:
                body = exc.response.text[:400]
            except Exception:
                pass
            raise LLMError(f"[JARVIS] Ollama HTTP error: {exc} | body: {body}") from exc
        except Exception as exc:
            raise LLMError(f"[JARVIS] Ollama stream error: {type(exc).__name__}: {exc}") from exc

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        messages: List[dict],
        system_prompt: str,
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> dict:
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)
        return {
            "model": self._model,
            "messages": all_messages,
            "stream": stream,
            "think": False,   # disable extended thinking for qwen3/deepseek-r1 — faster on CPU
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
