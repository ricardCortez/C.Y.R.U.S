"""
JARVIS — LLM Manager.

Orchestrates LOCAL (Ollama) and API (Claude) backends with automatic
fallback.  Injects the system prompt from ``soul.md`` and the conversation
context template from ``prompts.yaml``.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List, Optional

from backend.modules.llm.claude_client import ClaudeClient
from backend.modules.llm.ollama_client import OllamaClient
from backend.modules.vision.models import VisionContext
from backend.utils.exceptions import LLMError, OllamaUnavailableError
from backend.utils.helpers import retry_async
from backend.utils.logger import get_logger

logger = get_logger("jarvis.llm.manager")


class LLMManager:
    """Unified LLM interface with LOCAL → API fallback.

    Args:
        ollama: Pre-configured :class:`OllamaClient`.
        claude: Pre-configured :class:`ClaudeClient` (used as fallback).
        soul_text: Raw markdown from ``soul.md`` — the JARVIS personality.
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

        logger.info(f"[JARVIS] LLM: complexity={complexity} max_tokens={routed_max_tokens}")

        # Try local Ollama first — retry up to 2 times on transient errors (e.g.
        # HTTP 500 during cold model load which can take 30+ seconds).
        _MAX_ATTEMPTS = 3
        _RETRY_DELAY  = 5.0   # seconds between retries
        for _attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                logger.info(
                    f"[JARVIS] LLM: attempting local Ollama inference"
                    f"{f' (attempt {_attempt}/{_MAX_ATTEMPTS})' if _attempt > 1 else ''}…"
                )
                raw = await self._ollama.chat(
                    messages,
                    system_prompt=system_prompt,
                    temperature=self._temperature,
                    max_tokens=routed_max_tokens,
                )
                if raw.strip():
                    logger.info(f"[JARVIS] LLM: Ollama responded ({len(raw)} chars)")
                    return self._split_response(raw.strip())
                logger.warning("[JARVIS] LLM: Ollama returned empty response")
                break   # empty response is not a transient error — skip retries
            except OllamaUnavailableError as exc:
                logger.warning(f"[JARVIS] LLM: Ollama unavailable — {exc}")
                break   # connection refused → no point retrying immediately
            except LLMError as exc:
                logger.warning(f"[JARVIS] LLM: Ollama error — {exc}")
                if _attempt < _MAX_ATTEMPTS:
                    logger.info(
                        f"[JARVIS] LLM: retrying in {_RETRY_DELAY:.0f}s "
                        f"(model may still be loading)…"
                    )
                    await asyncio.sleep(_RETRY_DELAY)

        # Fallback to Claude API (only in HYBRID mode)
        if self._mode == "HYBRID":
            return await self._claude_fallback(messages, system_prompt)

        # Graceful degradation
        canned = self._prompts.get("canned", {}).get(
            "llm_unavailable",
            "Lo siento, en este momento no puedo procesar tu solicitud. "
            "Mi motor de razonamiento parece estar fuera de línea.",
        )
        logger.error("[JARVIS] LLM: all backends failed; returning canned response")
        return canned, canned

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
