"""
C.Y.R.U.S — Remote Vision backend.

HTTP client for the C.Y.R.U.S Vision microservice (services/vision_server).
Sends base64-encoded JPEG frames and receives detected objects + faces.

Usage
-----
Configure in config.yaml:
    services:
      vision:
        enabled: true
        host: http://localhost:8001
"""

from __future__ import annotations

import base64
from typing import Optional

from backend.modules.vision.models import DetectedFace, DetectedObject, VisionContext
from backend.utils.logger import get_logger

logger = get_logger("cyrus.vision.remote")

try:
    import httpx
    _HTTPX_OK = True
except ImportError:
    _HTTPX_OK = False


class RemoteVision:
    """HTTP client for the C.Y.R.U.S Vision microservice.

    Replaces the in-process VisionManager when ``services.vision.enabled: true``.
    Provides the same interface: ``get_context()`` returns a :class:`VisionContext`.

    Args:
        host:    Base URL (e.g. ``http://localhost:8001``).
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        host: str = "http://localhost:8001",
        timeout: float = 10.0,
    ) -> None:
        self._host = host.rstrip("/")
        self._timeout = timeout
        self._available: Optional[bool] = None
        self._context: VisionContext = VisionContext(source="remote")

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def check_health(self) -> bool:
        if not _HTTPX_OK:
            self._available = False
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self._host}/health")
                self._available = r.status_code == 200
                if self._available:
                    data = r.json()
                    logger.info(
                        f"[C.Y.R.U.S] RemoteVision: server ready — "
                        f"yolo={data.get('yolo')}, face={data.get('face')}"
                    )
                return self._available
        except Exception as exc:
            logger.warning(f"[C.Y.R.U.S] RemoteVision: server not reachable at {self._host} ({exc})")
            self._available = False
            return False

    @property
    def available(self) -> bool:
        return bool(self._available)

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    async def analyze_frame(self, frame_b64: str) -> VisionContext:
        """Send a base64-encoded JPEG frame for remote analysis.

        Args:
            frame_b64: Base64-encoded JPEG image.

        Returns:
            Populated :class:`VisionContext`.
        """
        if not _HTTPX_OK:
            return VisionContext(source="remote")

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(
                    f"{self._host}/analyze",
                    json={"frame_b64": frame_b64},
                )
                if r.status_code != 200:
                    logger.warning(f"[C.Y.R.U.S] RemoteVision: server returned {r.status_code}")
                    return VisionContext(source="remote")

                data = r.json()
                self._available = True

                objects = [
                    DetectedObject(
                        label=o["label"],
                        confidence=o["confidence"],
                        bbox=tuple(o["bbox"]),
                    )
                    for o in data.get("objects", [])
                ]
                faces = [
                    DetectedFace(
                        identity=f["identity"],
                        confidence=f["confidence"],
                    )
                    for f in data.get("faces", [])
                ]
                ctx = VisionContext(source="remote", objects=objects, faces=faces)
                self._context = ctx
                return ctx

        except Exception as exc:
            logger.warning(f"[C.Y.R.U.S] RemoteVision: analysis failed ({exc})")
            self._available = False
            return VisionContext(source="remote")

    def get_context(self) -> VisionContext:
        """Return the most recently analyzed context (cached)."""
        return self._context

    # ------------------------------------------------------------------
    # VisionManager-compatible lifecycle stubs
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Probe server health (replaces VisionManager.start)."""
        await self.check_health()

    async def stop(self) -> None:
        pass
