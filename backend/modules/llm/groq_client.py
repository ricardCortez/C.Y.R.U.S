"""
CYRUS — Groq API client.

Groq implements the OpenAI Chat Completions API — this is a thin subclass
that points OpenAIClient at the Groq endpoint.
"""

from __future__ import annotations

from backend.modules.llm.openai_client import OpenAIClient

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqClient(OpenAIClient):
    """OpenAI-compatible client targeting the Groq inference API.

    Args:
        api_key: Groq API key (from console.groq.com).
        model: Model ID (e.g. 'llama-3.3-70b-versatile').
        max_tokens: Maximum tokens to generate.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "llama-3.3-70b-versatile",
        max_tokens: int = 500,
        timeout: int = 60,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=_GROQ_BASE_URL,
            max_tokens=max_tokens,
            timeout=timeout,
        )
