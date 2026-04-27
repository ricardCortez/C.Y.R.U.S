"""
JARVIS — Automatic fact extraction from conversation turns.

After each exchange (user → JARVIS), sends the pair to the LLM with a
compact prompt to extract concrete, reusable facts about Ricardo.
Runs async so it never blocks the voice pipeline.

Inspired by the post-turn memory extraction in JARVIS (ethanplusai).
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from backend.utils.logger import get_logger

if TYPE_CHECKING:
    from backend.modules.memory.fact_memory import FactMemory
    from backend.modules.llm.ollama_client import OllamaClient

logger = get_logger("jarvis.memory.extractor")

_EXTRACT_PROMPT = """Eres un extractor de hechos. Analiza este intercambio entre el usuario (Ricardo) y JARVIS.

Extrae SOLO hechos concretos y reutilizables sobre Ricardo: preferencias, proyectos, personas, decisiones o datos personales.

REGLAS:
- Máximo 3 hechos. Si no hay nada útil, devuelve lista vacía.
- Solo hechos explícitos, no inferencias.
- Ignora saludos, preguntas de estado, respuestas genéricas.
- Cada hecho debe ser autónomo (entendible sin contexto).

Responde SOLO con JSON válido, sin texto adicional:
[
  {{"type": "fact|preference|project|person|decision", "content": "...", "importance": 1-10}},
  ...
]

TIPOS:
- fact: dato biográfico o técnico ("usa Windows 11 Pro")
- preference: preferencia personal ("prefiere respuestas cortas")
- project: contexto de proyecto ("trabaja en JARVIS, asistente IA local en Python")
- person: persona mencionada ("Carlos = compañero de trabajo")
- decision: decisión tomada ("decidió usar qwen3:8b como LLM local")

INTERCAMBIO:
Usuario: {user_msg}
JARVIS: {jarvis_msg}

JSON:"""


async def extract_and_store(
    user_msg: str,
    jarvis_msg: str,
    fact_memory: "FactMemory",
    ollama: "OllamaClient",
    source: str = "",
) -> int:
    """Extract facts from one exchange and store them.

    Returns the number of facts stored (0 if nothing extracted or on error).
    Runs in background — never raises.
    """
    # Skip trivial exchanges
    if len(user_msg.strip()) < 8 or len(jarvis_msg.strip()) < 8:
        return 0
    # Skip pure status/greeting exchanges
    trivial = ("hola", "ok", "gracias", "sí", "no", "bueno", "bien",
               "vale", "entendido", "perfecto")
    if user_msg.strip().lower() in trivial:
        return 0

    prompt = _EXTRACT_PROMPT.format(
        user_msg=user_msg[:300],
        jarvis_msg=jarvis_msg[:300],
    )

    try:
        raw = await ollama.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=(
                "Eres un extractor de hechos. Responde SOLO con JSON válido."
            ),
            temperature=0.1,
            max_tokens=300,
        )
    except Exception as exc:
        logger.debug(f"[JARVIS] FactExtractor: LLM call failed — {exc}")
        return 0

    # Parse JSON — strip any markdown fences the model might add
    raw = raw.strip()
    raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    raw = raw.strip()

    try:
        facts = json.loads(raw)
        if not isinstance(facts, list):
            return 0
    except json.JSONDecodeError:
        logger.debug(f"[JARVIS] FactExtractor: JSON parse failed — raw={raw[:80]}")
        return 0

    stored = 0
    for item in facts:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        if not content or len(content) < 5:
            continue
        fact_type  = str(item.get("type", "fact"))
        importance = int(item.get("importance", 5))
        fact_memory.add(content, fact_type, source or user_msg[:60], importance)
        stored += 1

    if stored:
        logger.info(f"[JARVIS] FactExtractor: stored {stored} facts from exchange")
    return stored
