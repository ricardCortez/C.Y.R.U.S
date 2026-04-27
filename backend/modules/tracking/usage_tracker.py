"""
JARVIS — Usage & cost tracker.

Logs every LLM call to data/usage.jsonl and provides voice-readable summaries.
Pricing: Anthropic claude-haiku-4-5 — $0.80/MTok in, $4.00/MTok out.
         Ollama (local) — $0.00.
"""
from __future__ import annotations

import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from backend.utils.logger import get_logger

logger = get_logger("jarvis.tracking")

# Anthropic pricing (USD per million tokens) — update as needed
_PRICING: dict[str, dict] = {
    "claude-haiku-4-5-20251001": {"in": 0.80, "out": 4.00},
    "claude-sonnet-4-6":        {"in": 3.00, "out": 15.00},
    "claude-opus-4-7":          {"in": 15.00, "out": 75.00},
    "default_api":               {"in": 0.80, "out": 4.00},
    "ollama":                    {"in": 0.00, "out": 0.00},
}


class UsageTracker:
    def __init__(self, log_path: str = "data/usage.jsonl") -> None:
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._session_input  = 0
        self._session_output = 0
        self._session_calls  = 0
        self._session_cost   = 0.0
        self._session_start  = datetime.now()

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        source: str = "ollama",  # "ollama" | "claude"
    ) -> float:
        """Record one LLM call. Returns cost in USD."""
        pricing = _PRICING.get(model, _PRICING.get(
            "default_api" if source == "claude" else "ollama"
        ))
        cost = (input_tokens * pricing["in"] + output_tokens * pricing["out"]) / 1_000_000

        entry = {
            "ts":             datetime.now().isoformat(),
            "model":          model,
            "source":         source,
            "input_tokens":   input_tokens,
            "output_tokens":  output_tokens,
            "cost_usd":       round(cost, 6),
        }
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            logger.warning(f"[JARVIS] UsageTracker write failed: {exc}")

        self._session_input  += input_tokens
        self._session_output += output_tokens
        self._session_calls  += 1
        self._session_cost   += cost
        return cost

    def session_summary(self) -> str:
        elapsed = datetime.now() - self._session_start
        mins = int(elapsed.total_seconds() / 60)
        cost = self._session_cost
        if cost < 0.01:
            cost_str = f"${cost*100:.2f}¢"
        else:
            cost_str = f"${cost:.3f}"
        return (
            f"Esta sesión: {mins} minutos, {self._session_calls} llamadas, "
            f"{self._session_input+self._session_output:,} tokens, {cost_str}."
        )

    def today_summary(self) -> str:
        today = date.today().isoformat()
        total_in = total_out = total_cost = calls = 0
        try:
            with self._path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                        if e.get("ts", "")[:10] == today:
                            total_in   += e.get("input_tokens", 0)
                            total_out  += e.get("output_tokens", 0)
                            total_cost += e.get("cost_usd", 0)
                            calls      += 1
                    except Exception:
                        pass
        except FileNotFoundError:
            pass

        if not calls:
            return "Sin actividad registrada hoy."
        cost_str = f"${total_cost:.3f}" if total_cost >= 0.01 else f"${total_cost*100:.2f}¢"
        return (
            f"Hoy: {calls} llamadas, {total_in+total_out:,} tokens, {cost_str}."
        )

    def all_time_summary(self) -> str:
        total_in = total_out = total_cost = calls = 0
        try:
            with self._path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                        total_in   += e.get("input_tokens", 0)
                        total_out  += e.get("output_tokens", 0)
                        total_cost += e.get("cost_usd", 0)
                        calls      += 1
                    except Exception:
                        pass
        except FileNotFoundError:
            pass
        if not calls:
            return "Sin historial registrado."
        return (
            f"Total: {calls} llamadas, {total_in+total_out:,} tokens, "
            f"${total_cost:.3f}."
        )
