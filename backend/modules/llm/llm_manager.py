"""
CYRUS — LLM Manager.

Orchestrates LOCAL (Ollama) and API (Claude/OpenAI/Groq/Gemini) backends.
Active provider is configurable at runtime via set_provider().
Injects the system prompt from ``soul.md`` and the conversation
context template from ``prompts.yaml``.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List, Optional

from backend.modules.llm.claude_client import ClaudeClient
from backend.modules.llm.ollama_client import OllamaClient
from backend.modules.llm.openai_client import OpenAIClient
from backend.modules.llm.groq_client import GroqClient
from backend.modules.llm.gemini_client import GeminiClient
from backend.modules.vision.models import VisionContext
from backend.utils.exceptions import LLMError, OllamaUnavailableError
from backend.utils.helpers import retry_async
from backend.utils.logger import get_logger

logger = get_logger("jarvis.llm.manager")

_API_PROVIDERS = {"openai", "anthropic", "groq", "gemini"}


class LLMManager:
    """Unified LLM interface with configurable active provider.

    Active provider defaults to 'ollama'. Call set_provider() at runtime
    to switch to an API provider without restarting.

    Args:
        ollama: Pre-configured :class:`OllamaClient`.
        claude: Pre-configured :class:`ClaudeClient`.
        soul_text: Raw markdown from ``soul.md`` — the CYRUS personality.
        prompts: Parsed ``prompts.yaml`` dict.
        mode: ``"LOCAL"`` or ``"HYBRID"`` (enables Ollama → API fallback).
        temperature: Default sampling temperature.
        max_tokens: Default max response tokens.
        initial_provider: Starting provider name (from config).
        initial_api_key: API key for the initial provider.
        initial_api_model: Model for the initial provider.
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
        initial_provider: str = "ollama",
        initial_api_key: str = "",
        initial_api_model: str = "",
    ) -> None:
        self._ollama = ollama
        self._claude = claude
        self._soul_text = soul_text
        self._prompts = prompts or {}
        self._mode = mode.upper()
        self._temperature = temperature
        self._max_tokens = max_tokens

        # Active provider state
        self._active_provider: str = "ollama"
        self._api_client: Optional[object] = None  # current API client instance

        # Initialize from config if a non-ollama provider is set
        if initial_provider in _API_PROVIDERS and initial_api_key:
            try:
                self.set_provider(initial_provider, initial_api_key, initial_api_model)
            except Exception as exc:
                logger.warning(f"[CYRUS] LLM: failed to init provider '{initial_provider}': {exc}")

    # ------------------------------------------------------------------
    # Provider management
    # ------------------------------------------------------------------

    def set_provider(self, provider: str, api_key: str, model: str) -> dict:
        """Switch the active LLM provider.

        Args:
            provider: One of 'ollama', 'openai', 'anthropic', 'groq', 'gemini'.
            api_key: API key (ignored for 'ollama').
            model: Model ID to use.

        Returns:
            {"ok": bool, "error": str}
        """
        provider = provider.lower().strip()
        if provider == "ollama":
            self._active_provider = "ollama"
            self._api_client = None
            if model:
                self._ollama._model = model
            logger.info(f"[CYRUS] LLM: active provider → ollama ({self._ollama._model})")
            return {"ok": True, "error": ""}

        if provider not in _API_PROVIDERS:
            return {"ok": False, "error": f"Provider desconocido: {provider}"}
        if not api_key:
            return {"ok": False, "error": "API key requerida"}
        if not model:
            return {"ok": False, "error": "Modelo requerido"}

        try:
            client = self._build_api_client(provider, api_key, model)
            self._api_client = client
            self._active_provider = provider
            logger.info(f"[CYRUS] LLM: active provider → {provider} ({model})")
            return {"ok": True, "error": ""}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def test_connectivity(self, provider: str, api_key: str, model: str) -> dict:
        """Test connectivity for a provider without changing the active one.

        Args:
            provider: Provider name.
            api_key: API key to test.
            model: Model to test.

        Returns:
            {"ok": bool, "latency_ms": int, "error": str}
        """
        if provider == "ollama":
            available = await self._ollama.is_available()
            return {
                "ok": available,
                "latency_ms": 0,
                "error": "" if available else "Ollama no está corriendo en localhost:11434",
            }
        try:
            client = self._build_api_client(provider, api_key, model)
            return await client.test_connectivity()
        except Exception as exc:
            return {"ok": False, "latency_ms": 0, "error": str(exc)}

    def get_active_provider(self) -> str:
        return self._active_provider

    def get_active_model(self) -> str:
        if self._active_provider == "ollama":
            return self._ollama._model
        if hasattr(self._api_client, "_model"):
            return self._api_client._model
        if hasattr(self._api_client, "_model_name"):
            return self._api_client._model_name
        return ""

    @staticmethod
    def _build_api_client(provider: str, api_key: str, model: str):
        """Instantiate the correct API client for the given provider."""
        if provider == "openai":
            return OpenAIClient(api_key=api_key, model=model)
        if provider == "anthropic":
            return ClaudeClient(api_key=api_key, model=model)
        if provider == "groq":
            return GroqClient(api_key=api_key, model=model)
        if provider == "gemini":
            return GeminiClient(api_key=api_key, model=model)
        raise ValueError(f"Unknown provider: {provider}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    # ── Query complexity routing ───────────────────────────────────────────

    @staticmethod
    def _classify_complexity(text: str) -> str:
        """Classify query as 'simple', 'medium', or 'complex'.

        Simple  → short, conversational, no technical depth needed
        Medium  → factual questions, moderate length
        Complex → code, multi-step reasoning, technical configuration
        """
        low  = text.lower().strip()
        wlen = len(low.split())

        # Always complex if technical keywords present
        complex_signals = [
            "código", "código", "script", "función", "configura", "instala",
            "error", "bug", "depura", "implementa", "arquitectura", "diseña",
            "explica cómo", "cómo funciona", "por qué falla",
        ]
        if any(s in low for s in complex_signals):
            return "complex"

        # Simple: very short, greetings, status checks
        simple_signals = [
            "hola", "gracias", "ok", "bien", "perfecto", "entendido",
            "qué hora", "qué día", "cómo estás", "qué tal",
        ]
        if wlen <= 6 or any(s in low for s in simple_signals):
            return "simple"

        if wlen <= 20:
            return "medium"
        return "complex"

    async def generate(
        self,
        user_input: str,
        history: List[dict] | None = None,
        language: str = "en",
        turn_count: int = 0,
        vision_context: Optional[VisionContext] = None,
        memory_context: str = "",
    ) -> tuple[str, str]:
        """Generate a response to *user_input*.

        Args:
            user_input: Cleaned user intent text.
            history: Prior conversation turns (OpenAI-style message list).
            language: Detected language code (for context injection).
            turn_count: Conversation turn number.
            vision_context: Optional live camera scene description.
            memory_context: Relevant past turns from semantic memory search.

        Returns:
            Tuple of ``(display_text, speech_text)`` where *display_text* is
            the full markdown-formatted response for the UI and *speech_text*
            is the clean version for TTS synthesis.

        Raises:
            LLMError: If both local and API backends fail.
        """
        complexity = self._classify_complexity(user_input)
        system_prompt = self._build_system_prompt(language, turn_count, vision_context, memory_context)
        messages = list(history or [])
        messages.append({"role": "user", "content": user_input})

        # Routing: simple queries get fewer max_tokens (faster response)
        routed_max_tokens = self._max_tokens
        if complexity == "simple":
            routed_max_tokens = min(self._max_tokens, 120)
        elif complexity == "complex":
            routed_max_tokens = min(self._max_tokens * 2, 600)

        logger.info(f"[CYRUS] LLM: provider={self._active_provider} complexity={complexity} max_tokens={routed_max_tokens}")

        # Route to active provider
        if self._active_provider in _API_PROVIDERS and self._api_client is not None:
            return await self._api_generate(messages, system_prompt)

        # Local Ollama — retry up to 3 times on transient errors
        _MAX_ATTEMPTS = 3
        _RETRY_DELAY  = 5.0
        for _attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                logger.info(
                    f"[CYRUS] LLM: attempting local Ollama inference"
                    f"{f' (attempt {_attempt}/{_MAX_ATTEMPTS})' if _attempt > 1 else ''}…"
                )
                raw = await self._ollama.chat(
                    messages,
                    system_prompt=system_prompt,
                    temperature=self._temperature,
                    max_tokens=routed_max_tokens,
                )
                if raw.strip():
                    logger.info(f"[CYRUS] LLM: Ollama responded ({len(raw)} chars)")
                    return self._split_response(raw.strip())
                logger.warning("[CYRUS] LLM: Ollama returned empty response")
                break
            except OllamaUnavailableError as exc:
                logger.warning(f"[CYRUS] LLM: Ollama unavailable — {exc}")
                break
            except LLMError as exc:
                logger.warning(f"[CYRUS] LLM: Ollama error — {exc}")
                if _attempt < _MAX_ATTEMPTS:
                    logger.info(f"[CYRUS] LLM: retrying in {_RETRY_DELAY:.0f}s…")
                    await asyncio.sleep(_RETRY_DELAY)

        # HYBRID fallback: try API provider if Ollama failed
        if self._mode == "HYBRID":
            if self._api_client is not None:
                return await self._api_generate(messages, system_prompt)
            return await self._claude_fallback(messages, system_prompt)

        # Graceful degradation
        canned = self._prompts.get("canned", {}).get(
            "llm_unavailable",
            "Lo siento, en este momento no puedo procesar tu solicitud. "
            "Mi motor de razonamiento parece estar fuera de línea.",
        )
        logger.error("[CYRUS] LLM: all backends failed; returning canned response")
        return canned, canned

    async def _api_generate(self, messages: List[dict], system_prompt: str) -> tuple[str, str]:
        """Generate using the active API client."""
        try:
            logger.info(f"[CYRUS] LLM: calling {self._active_provider} API…")
            raw = await self._api_client.chat(
                messages,
                system_prompt=system_prompt,
                temperature=self._temperature,
            )
            logger.info(f"[CYRUS] LLM: {self._active_provider} responded ({len(raw)} chars)")
            return self._split_response(raw.strip())
        except Exception as exc:
            logger.error(f"[CYRUS] LLM: {self._active_provider} failed — {exc}")
            msg = (
                "Lo siento, hubo un problema con el servicio de IA. "
                "Por favor intenta de nuevo en un momento."
            )
            return msg, msg

    async def _claude_fallback(self, messages: List[dict], system_prompt: str) -> tuple[str, str]:
        """Attempt Claude API with retry."""
        try:
            logger.info("[JARVIS] LLM: falling back to Claude API…")
            raw = await self._claude.chat(
                messages,
                system_prompt=system_prompt,
                temperature=self._temperature,
            )
            logger.info("[JARVIS] LLM: Claude API responded")
            return self._split_response(raw.strip())
        except Exception as exc:
            logger.error(f"[JARVIS] LLM: Claude API also failed — {exc}")
            msg = (
                "Lo siento, tengo dificultades con mis motores de razonamiento. "
                "Por favor intenta de nuevo en un momento."
            )
            return msg, msg

    # ------------------------------------------------------------------
    # Response splitting
    # ------------------------------------------------------------------

    @staticmethod
    def _split_response(raw: str) -> tuple[str, str]:
        """Parse LLM output into (display_text, speech_text).

        VOZ: markers are legacy — the prompt no longer requests them, but phi3
        sometimes generates them anyway.  Strip any VOZ: suffix so it never
        appears in the display text.

        If the marker is found, display = text before it; speech = text after it.
        If not found, both display and speech come from the cleaned raw text.
        """
        import re
        from backend.utils.text_cleaner import prepare_speech

        # Match "VOZ:" (optional bold markers, optional space before colon)
        # anywhere in the text — search from the right to catch trailing suffixes
        voz_pattern = re.compile(
            r'\*{0,2}VOZ\*{0,2}\s*:',
            re.IGNORECASE,
        )
        match = None
        for m in voz_pattern.finditer(raw):
            match = m   # keep the last match

        if match:
            display = raw[:match.start()].rstrip()
            speech_raw = raw[match.end():].lstrip()
            speech = prepare_speech(speech_raw) if speech_raw else prepare_speech(display)
            if not display:
                display = speech_raw or raw
            logger.debug(f"[JARVIS] LLM: VOZ marker stripped — display {len(display)}ch, speech {len(speech)}ch")
            return display, speech

        # No VOZ marker — use raw as display, clean version for speech
        speech = prepare_speech(raw)
        return raw, speech

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

        now = datetime.now()
        _DAYS_ES   = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
        _MONTHS_ES = ["enero","febrero","marzo","abril","mayo","junio",
                      "julio","agosto","septiembre","octubre","noviembre","diciembre"]
        readable = (
            f"{now.strftime('%H:%M')} hrs  —  "
            f"{_DAYS_ES[now.weekday()]} {now.day} de "
            f"{_MONTHS_ES[now.month - 1]} de {now.year}"
        )
        context_tpl: str = self._prompts.get("context_template", "")
        context = context_tpl.format(
            current_time=readable,
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
