"""JARVIS — Frigate NVR integration.

Frigate exposes:
  GET /api/<camera>/latest.jpg   — latest JPEG snapshot
  GET /api/version               — version probe / health check
  GET /api/events                — recent detection events
"""
from __future__ import annotations

from typing import Optional

import httpx

from backend.utils.logger import get_logger

logger = get_logger("jarvis.vision.frigate")


class FrigateClient:
    """HTTP client for Frigate NVR snapshots and events.

    Args:
        host: Frigate base URL, e.g. ``"http://192.168.1.50:5000"``.
        camera: Camera name as configured in Frigate, e.g. ``"front_door"``.
        timeout: HTTP timeout in seconds.
    """

    def __init__(
        self,
        host: str = "http://192.168.1.50:5000",
        camera: str = "default",
        timeout: int = 5,
    ) -> None:
        self._host = host.rstrip("/")
        self._camera = camera
        self._timeout = timeout

    async def is_available(self) -> bool:
        """Return ``True`` if the Frigate service responds to a version ping."""
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{self._host}/api/version")
                return r.status_code == 200
        except Exception:
            return False

    async def get_snapshot_bytes(self) -> Optional[bytes]:
        """Fetch the latest JPEG snapshot from Frigate.

        Returns:
            Raw JPEG bytes, or ``None`` if the service is unavailable.
        """
        url = f"{self._host}/api/{self._camera}/latest.jpg"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    return r.content
                logger.warning(
                    f"[JARVIS] Frigate snapshot returned HTTP {r.status_code}"
                )
                return None
        except Exception as exc:
            logger.warning(f"[JARVIS] Frigate unreachable: {exc}")
            return None

    async def get_snapshot_array(self):
        """Return the latest snapshot as a numpy BGR array, or ``None``."""
        import cv2
        import numpy as np

        raw = await self.get_snapshot_bytes()
        if raw is None:
            return None
        arr = np.frombuffer(raw, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return frame
