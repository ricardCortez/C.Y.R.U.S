"""
JARVIS — Home Assistant REST API client (Phase 4).

Wraps the HA Long-Lived Access Token REST API.
All calls are async (httpx).

Docs: https://developers.home-assistant.io/docs/api/rest/
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import httpx

from backend.utils.logger import get_logger

logger = get_logger("cyrus.ha.client")


class HomeAssistantClient:
    """Async client for the Home Assistant REST API.

    Args:
        base_url: HA base URL, e.g. ``http://homeassistant.local:8123``.
        token:    Long-Lived Access Token from HA profile page.
        timeout:  HTTP request timeout in seconds.
        verify_ssl: Verify TLS certificate (set False for self-signed certs).
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 10.0,
        verify_ssl: bool = True,
    ) -> None:
        self._base  = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        }
        self._timeout    = timeout
        self._verify_ssl = verify_ssl
        self._available  = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def check_connection(self) -> bool:
        """Ping HA API. Returns True if reachable and token is valid."""
        try:
            async with httpx.AsyncClient(verify=self._verify_ssl, timeout=self._timeout) as c:
                r = await c.get(f"{self._base}/api/", headers=self._headers)
                self._available = r.status_code == 200
                if self._available:
                    logger.info("[HA] Connected to Home Assistant")
                else:
                    logger.warning(f"[HA] API ping returned {r.status_code}")
        except Exception as exc:
            logger.warning(f"[HA] Connection failed: {exc}")
            self._available = False
        return self._available

    @property
    def available(self) -> bool:
        return self._available

    # ── States ────────────────────────────────────────────────────────────────

    async def get_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Return the state dict for an entity or None on error."""
        try:
            async with httpx.AsyncClient(verify=self._verify_ssl, timeout=self._timeout) as c:
                r = await c.get(f"{self._base}/api/states/{entity_id}", headers=self._headers)
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            logger.error(f"[HA] get_state({entity_id}) failed: {exc}")
            return None

    async def get_all_states(self) -> List[Dict[str, Any]]:
        """Return all entity states."""
        try:
            async with httpx.AsyncClient(verify=self._verify_ssl, timeout=self._timeout) as c:
                r = await c.get(f"{self._base}/api/states", headers=self._headers)
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            logger.error(f"[HA] get_all_states failed: {exc}")
            return []

    # ── Services ──────────────────────────────────────────────────────────────

    async def call_service(
        self,
        domain: str,
        service: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Call a HA service. Returns True on success."""
        url = f"{self._base}/api/services/{domain}/{service}"
        try:
            async with httpx.AsyncClient(verify=self._verify_ssl, timeout=self._timeout) as c:
                r = await c.post(url, headers=self._headers, json=data or {})
                r.raise_for_status()
                logger.info(f"[HA] Service {domain}.{service} called → {r.status_code}")
                return True
        except Exception as exc:
            logger.error(f"[HA] call_service({domain}.{service}) failed: {exc}")
            return False

    # ── Convenience helpers ───────────────────────────────────────────────────

    async def turn_on(self, entity_id: str, **kwargs) -> bool:
        domain = entity_id.split(".")[0]
        return await self.call_service(domain, "turn_on", {"entity_id": entity_id, **kwargs})

    async def turn_off(self, entity_id: str) -> bool:
        domain = entity_id.split(".")[0]
        return await self.call_service(domain, "turn_off", {"entity_id": entity_id})

    async def toggle(self, entity_id: str) -> bool:
        domain = entity_id.split(".")[0]
        return await self.call_service(domain, "toggle", {"entity_id": entity_id})

    async def set_light_brightness(self, entity_id: str, brightness_pct: int) -> bool:
        """Set light brightness 0–100 %."""
        brightness = int(brightness_pct / 100 * 255)
        return await self.call_service(
            "light", "turn_on",
            {"entity_id": entity_id, "brightness": brightness},
        )

    async def set_light_color_temp(self, entity_id: str, kelvin: int) -> bool:
        return await self.call_service(
            "light", "turn_on",
            {"entity_id": entity_id, "color_temp_kelvin": kelvin},
        )
