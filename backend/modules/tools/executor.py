"""
JARVIS — Tool Executor (ReAct-style orchestrator).

Implements the PENSAMIENTO → HERRAMIENTA → OBSERVACIÓN loop.
Runs up to MAX_TURNS iterations; returns the RESPUESTA_FINAL when found.

Compatible with qwen3:8b in non-thinking mode (think:false).
"""
from __future__ import annotations

import hashlib
import re
import asyncio
from collections import Counter
from typing import List, Optional

from backend.modules.tools.registry import ToolRegistry, get_registry
from backend.modules.tools.result import ToolResult
from backend.utils.logger import get_logger

logger = get_logger("jarvis.tools.executor")

MAX_TURNS   = 5
_LOOP_LIMIT = 2   # block a (tool, args) pair after this many identical calls


# ── Prompt blocks ─────────────────────────────────────────────────────────────

ORCHESTRATOR_INSTRUCTIONS = """
Cuando necesites información externa o ejecutar una acción, usa el formato:

HERRAMIENTA: <nombre_herramienta>
PARÁMETROS: <param1>=<valor1> | <param2>=<valor2>

Cuando tengas suficiente información para responder, usa:
RESPUESTA_FINAL: <tu respuesta aquí>

Reglas:
- Solo usa herramientas cuando el usuario realmente lo necesite
- Si puedes responder directamente, usa RESPUESTA_FINAL sin herramientas
- Responde siempre en español
- Las respuestas de voz deben ser concisas (1-3 oraciones)
"""


class ToolExecutor:
    """ReAct loop executor.

    Args:
        registry: Tool catalog to resolve names to callables.
        ollama:   OllamaClient for LLM calls within the loop.
        max_turns: Maximum HERRAMIENTA iterations before giving up.
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        ollama=None,
        max_turns: int = MAX_TURNS,
    ) -> None:
        self._registry  = registry or get_registry()
        self._ollama    = ollama
        self._max_turns = max_turns

    # ── Public API ────────────────────────────────────────────────────────────

    async def run(
        self,
        user_input: str,
        messages: List[dict],
        system_prompt: str,
        temperature: float = 0.5,
        max_tokens: int = 300,
    ) -> tuple[str, str]:
        """Run the ReAct loop.

        Returns (display_text, speech_text) — same contract as LLMManager.generate().
        If no tools are triggered, returns (None, None) to signal the caller to
        use the normal LLM path instead.
        """
        if not self._registry.all() or not self._ollama:
            return None, None

        # Check if query likely needs a tool
        if not self._needs_tool(user_input):
            return None, None

        # Build ReAct system prompt
        react_prompt = self._build_react_prompt(system_prompt)

        # Working message list
        work_msgs = list(messages)
        work_msgs.append({"role": "user", "content": user_input})

        # Loop guard: track (tool, args) call counts and recent sequence
        call_counts: Counter = Counter()
        recent_calls: List[str] = []   # last 4 call hashes for ping-pong detection

        for turn in range(1, self._max_turns + 1):
            logger.info(f"[Tools] ReAct turn {turn}/{self._max_turns}")

            response = await self._ollama.chat(
                work_msgs,
                system_prompt=react_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # Check for RESPUESTA_FINAL
            final = self._extract_final(response)
            if final:
                logger.info(f"[Tools] RESPUESTA_FINAL found at turn {turn}")
                return final, final

            # Check for HERRAMIENTA call
            tool_name, raw_params = self._extract_tool_call(response)
            if not tool_name:
                clean = self._strip_react_markers(response)
                if clean.strip():
                    return clean, clean
                return None, None

            # ── Loop guard ────────────────────────────────────────────────
            params = self._parse_params(raw_params)
            call_hash = self._call_hash(tool_name, params)
            call_counts[call_hash] += 1
            recent_calls.append(call_hash)
            if len(recent_calls) > 4:
                recent_calls.pop(0)

            # Identical call repeated too many times
            if call_counts[call_hash] > _LOOP_LIMIT:
                logger.warning(f"[Tools] Loop guard: '{tool_name}' called {call_counts[call_hash]}x — stopping")
                obs = f"Herramienta '{tool_name}' ya fue llamada varias veces con los mismos parámetros. Usa la información ya obtenida para responder."
                work_msgs.append({"role": "assistant", "content": response})
                work_msgs.append({"role": "user",      "content": f"OBSERVACIÓN: {obs}"})
                continue

            # Ping-pong: A→B→A→B pattern
            if len(recent_calls) >= 4 and recent_calls[-4] == recent_calls[-2] and recent_calls[-3] == recent_calls[-1]:
                logger.warning("[Tools] Loop guard: ping-pong pattern detected — stopping")
                return None, None

            # ── Execute tool ──────────────────────────────────────────────
            tool_def = self._registry.get(tool_name)
            if not tool_def:
                obs = f"Herramienta '{tool_name}' no encontrada."
                logger.warning(f"[Tools] Unknown tool: {tool_name}")
            else:
                logger.info(f"[Tools] Calling {tool_name}({params})")
                try:
                    result: ToolResult = await tool_def.fn(**params)
                    obs = result.output
                    logger.info(f"[Tools] {tool_name} → ok={result.ok} ({len(obs)}ch)")
                except Exception as exc:
                    obs = f"Error ejecutando {tool_name}: {exc}"
                    logger.error(f"[Tools] {tool_name} raised: {exc}")

            # Append assistant + observation to working messages
            work_msgs.append({"role": "assistant", "content": response})
            work_msgs.append({"role": "user",      "content": f"OBSERVACIÓN: {obs}"})

        logger.warning("[Tools] Max turns reached without RESPUESTA_FINAL")
        return None, None

    # ── Heuristic: does this query need external tools? ───────────────────────

    def _needs_tool(self, text: str) -> bool:
        low = text.lower()
        triggers = [
            "busca", "búsca", "buscar", "busca en internet", "qué dice",
            "cuánto cuesta", "precio de", "qué es", "quién es",
            "clima", "tiempo en", "temperatura",
            "hora en", "qué hora es en",
            "abre", "ejecuta", "lanza", "inicia",
            "archivo", "fichero", "lista los archivos", "qué hay en",
            "anota", "recuérdame",  # planner already handles these but tools can too
            "traduce", "en inglés", "en español",
            "calcula", "cuánto es",
        ]
        return any(t in low for t in triggers)

    # ── Prompt builder ────────────────────────────────────────────────────────

    def _build_react_prompt(self, base_prompt: str) -> str:
        catalog = self._registry.catalog_prompt()
        return f"{base_prompt}\n\n{catalog}\n\n{ORCHESTRATOR_INSTRUCTIONS}"

    # ── Parsers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_final(text: str) -> Optional[str]:
        m = re.search(r"RESPUESTA_FINAL\s*:\s*(.+)", text, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()
        return None

    @staticmethod
    def _extract_tool_call(text: str) -> tuple[Optional[str], str]:
        m = re.search(r"HERRAMIENTA\s*:\s*(\w+)", text, re.IGNORECASE)
        if not m:
            return None, ""
        name = m.group(1).strip()
        p = re.search(r"PAR[ÁA]METROS\s*:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
        raw = p.group(1).strip() if p else ""
        return name, raw

    @staticmethod
    def _parse_params(raw: str) -> dict:
        """Parse 'key=value | key2=value2' into a dict."""
        params: dict = {}
        if not raw:
            return params
        for part in raw.split("|"):
            part = part.strip()
            if "=" in part:
                k, _, v = part.partition("=")
                params[k.strip()] = v.strip()
        return params

    @staticmethod
    def _call_hash(tool_name: str, params: dict) -> str:
        """Stable hash of a (tool_name, sorted_params) pair for loop detection."""
        key = tool_name + "|" + "|".join(f"{k}={v}" for k, v in sorted(params.items()))
        return hashlib.md5(key.encode()).hexdigest()[:8]

    @staticmethod
    def _strip_react_markers(text: str) -> str:
        """Remove PENSAMIENTO/HERRAMIENTA/PARÁMETROS lines from a response."""
        lines = []
        for line in text.splitlines():
            low = line.lower().lstrip()
            if any(low.startswith(p) for p in ["pensamiento:", "herramienta:", "parámetros:", "parametros:", "observación:"]):
                continue
            lines.append(line)
        return "\n".join(lines).strip()
