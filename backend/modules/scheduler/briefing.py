"""
JARVIS — Morning Briefing Agent.

Collects data from multiple sources, asks the LLM to synthesize a concise
Spanish audio briefing, then returns the text for TTS playback.

Data sources (all offline-capable):
  - DateTime + day of week (local)
  - Pending tasks from TaskPlanner
  - System health (CPU, RAM, disk)
  - Weather for configured city (wttr.in, no key needed)

Inspired by OpenJarvis morning_digest.py.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Callable, Coroutine, List, Optional

import httpx

from backend.utils.logger import get_logger

logger = get_logger("jarvis.scheduler.briefing")

_DAYS_ES   = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
_MONTHS_ES = ["enero","febrero","marzo","abril","mayo","junio",
               "julio","agosto","septiembre","octubre","noviembre","diciembre"]


def _readable_date() -> str:
    now = datetime.now()
    return (
        f"{_DAYS_ES[now.weekday()]} {now.day} de "
        f"{_MONTHS_ES[now.month-1]} de {now.year}, "
        f"son las {now.strftime('%H:%M')}"
    )


async def _fetch_weather(city: str, timeout: float = 6.0) -> str:
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(f"https://wttr.in/{city}?format=j1")
            r.raise_for_status()
            data = r.json()
        cur  = data["current_condition"][0]
        temp = cur["temp_C"]
        feel = cur["FeelsLikeC"]
        desc = (cur.get("lang_es") or [{"value": cur["weatherDesc"][0]["value"]}])[0]["value"]
        hum  = cur["humidity"]
        wind = cur["windspeedKmph"]
        return f"{desc}, {temp}°C (sensación {feel}°C), humedad {hum}%, viento {wind} km/h"
    except Exception as exc:
        logger.warning(f"[Briefing] Weather fetch failed: {exc}")
        return "no disponible"


async def _fetch_system_info() -> str:
    try:
        import psutil
        cpu  = psutil.cpu_percent(interval=0.3)
        ram  = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return (
            f"CPU al {cpu:.0f}%, "
            f"RAM {ram.used/1e9:.1f}/{ram.total/1e9:.1f} GB ({ram.percent:.0f}%), "
            f"disco {disk.used/1e9:.0f}/{disk.total/1e9:.0f} GB ({disk.percent:.0f}%)"
        )
    except Exception:
        return "no disponible"


_BRIEFING_PROMPT = """Eres JARVIS. Genera un briefing matutino en español para Ricardo.
Sé conciso — máximo 5 oraciones. Sin markdown. Habla como si lo saludaras al comenzar el día.
Estructura: saludo con la fecha → clima → tareas pendientes → estado del sistema → cierre motivador breve.
"""


class MorningBriefingAgent:
    """Generates the morning briefing text using the LLM + external data.

    Args:
        ollama:  OllamaClient for LLM generation.
        planner: TaskPlanner for pending tasks.
        city:    City name for weather (default: Lima).
    """

    def __init__(
        self,
        ollama,
        planner=None,
        city: str = "Lima",
    ) -> None:
        self._ollama  = ollama
        self._planner = planner
        self._city    = city

    async def generate(self) -> str:
        """Collect data, ask LLM to synthesize briefing. Returns plain text."""
        date_str   = _readable_date()
        weather    = await _fetch_weather(self._city)
        sys_info   = await _fetch_system_info()
        tasks_text = self._pending_tasks_text()

        context = (
            f"Fecha y hora: {date_str}\n"
            f"Clima en {self._city}: {weather}\n"
            f"Estado del sistema: {sys_info}\n"
            f"Tareas pendientes:\n{tasks_text}"
        )

        logger.info(f"[Briefing] Generating with context:\n{context}")

        try:
            response = await self._ollama.chat(
                messages=[{"role": "user", "content": context}],
                system_prompt=_BRIEFING_PROMPT,
                temperature=0.7,
                max_tokens=250,
            )
            briefing = response.strip()
            logger.info(f"[Briefing] Generated ({len(briefing)}ch): {briefing[:120]}")
            return briefing
        except Exception as exc:
            logger.error(f"[Briefing] LLM generation failed: {exc}")
            # Fallback: plain data summary without LLM
            return (
                f"Buenos días, Ricardo. Hoy es {date_str}. "
                f"Clima en {self._city}: {weather}. "
                f"{tasks_text}. "
                f"Sistema: {sys_info}."
            )

    def _pending_tasks_text(self) -> str:
        if not self._planner:
            return "sin información de tareas"
        tasks = self._planner.get_pending()
        if not tasks:
            return "No tienes tareas pendientes."
        lines = [f"- {t.description}" + (f" ({t.due_hint})" if t.due_hint else "")
                 for t in tasks[:5]]
        extra = f" y {len(tasks)-5} más." if len(tasks) > 5 else ""
        return "\n".join(lines) + extra
