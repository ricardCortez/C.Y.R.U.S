"""
C.Y.R.U.S — Home Assistant Device Controller (Phase 4).

Maps natural-language intent to HA service calls.
Patterns cover common Spanish voice commands for lights, switches, and climate.
"""
from __future__ import annotations

import re
from typing import Optional

from backend.modules.home_assistant.ha_client import HomeAssistantClient
from backend.utils.logger import get_logger

logger = get_logger("cyrus.ha.controller")

# ── Intent → entity alias map (extend via HA config) ─────────────────────────
# Keys are lowercase Spanish room/device names; values are HA entity_ids.
# This is a starter map — populate via config or HA auto-discovery.
_DEFAULT_ALIASES: dict[str, str] = {
    "sala":         "light.sala",
    "living":       "light.sala",
    "cocina":       "light.cocina",
    "dormitorio":   "light.dormitorio",
    "cuarto":       "light.dormitorio",
    "habitacion":   "light.dormitorio",
    "baño":         "light.bano",
    "oficina":      "light.oficina",
    "escritorio":   "light.oficina",
    "garage":       "switch.garage",
    "ventilador":   "switch.ventilador",
    "aire":         "climate.aire_acondicionado",
    "tv":           "media_player.tv",
    "television":   "media_player.tv",
}


class DeviceController:
    """Translates voice intents to Home Assistant service calls.

    Args:
        client:  Pre-connected :class:`HomeAssistantClient`.
        aliases: Optional override map of name → entity_id.
    """

    def __init__(
        self,
        client: HomeAssistantClient,
        aliases: Optional[dict[str, str]] = None,
    ) -> None:
        self._client  = client
        self._aliases = {**_DEFAULT_ALIASES, **(aliases or {})}

    # ── Intent router ─────────────────────────────────────────────────────────

    async def handle_voice_command(self, text: str) -> Optional[str]:
        """Parse *text* for HA commands. Returns Spanish reply or None."""
        if not self._client.available:
            return None

        low = text.lower().strip()

        # ── LIGHTS: enciende / apaga / prende ─────────────────────────────────
        m = re.search(
            r"(?:enciende|prende|activa|apaga|apague|enciéndeme)\s+(?:la(?:s)?\s+)?(?:luz(?:es)?\s+(?:de(?:l)?\s+)?)?(\w+)",
            low,
        )
        if m:
            device = m.group(1)
            entity = self._resolve(device)
            if entity:
                action = "turn_off" if any(k in low for k in ["apaga", "apague"]) else "turn_on"
                domain  = entity.split(".")[0]
                ok = await self._client.call_service(domain, action, {"entity_id": entity})
                verb = "apagué" if action == "turn_off" else "encendí"
                return f"{verb.capitalize()} {device}." if ok else f"No pude controlar {device}."

        # ── BRIGHTNESS: sube/baja el brillo ───────────────────────────────────
        m = re.search(r"(?:sube|baja)\s+(?:el\s+)?brillo\s+(?:de(?:l)?\s+)?(\w+)", low)
        if m:
            device = m.group(1)
            entity = self._resolve(device)
            if entity and entity.startswith("light."):
                pct = 80 if "sube" in low else 20
                ok  = await self._client.set_light_brightness(entity, pct)
                return f"Brillo de {device} ajustado." if ok else f"No pude ajustar {device}."

        # ── TOGGLE: alterna ───────────────────────────────────────────────────
        m = re.search(r"alterna(?:r)?\s+(?:la\s+)?(\w+)", low)
        if m:
            device = m.group(1)
            entity = self._resolve(device)
            if entity:
                ok = await self._client.toggle(entity)
                return f"Alterné {device}." if ok else f"No pude alternar {device}."

        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve(self, name: str) -> Optional[str]:
        """Return entity_id for a device name, or None if unknown."""
        entity = self._aliases.get(name.lower())
        if not entity:
            logger.debug(f"[HA] Unknown device alias: {name!r}")
        return entity

    def register_alias(self, name: str, entity_id: str) -> None:
        self._aliases[name.lower()] = entity_id
        logger.info(f"[HA] Alias registered: {name!r} → {entity_id!r}")
