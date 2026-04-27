"""JARVIS — VisionManager: orchestrates camera + YOLO + face pipeline."""
from __future__ import annotations

import asyncio
import base64
from typing import Optional

import numpy as np

from backend.modules.vision.camera_local import LocalCamera
from backend.modules.vision.face_detector import FaceDetector
from backend.modules.vision.frigate_client import FrigateClient
from backend.modules.vision.models import VisionContext
from backend.modules.vision.yolo_detector import YOLODetector
from backend.utils.logger import get_logger

logger = get_logger("jarvis.vision.manager")


class VisionManager:
    """Async vision pipeline that keeps a rolling :class:`VisionContext`.

    Supports two camera sources (mutually exclusive):
    - ``local``: USB webcam via :class:`LocalCamera`
    - ``frigate``: RTSP/snapshot via :class:`FrigateClient`

    Args:
        source: ``"local"`` or ``"frigate"``.
        local_camera: Pre-configured :class:`LocalCamera` (used when source="local").
        frigate_client: Pre-configured :class:`FrigateClient` (used when source="frigate").
        yolo: Pre-configured :class:`YOLODetector`.
        face: Pre-configured :class:`FaceDetector`.
        interval: Seconds between frame captures in the background loop.
        encode_frame: If ``True``, encode frame as base64 JPEG in the context.
    """

    def __init__(
        self,
        source: str = "local",
        local_camera: Optional[LocalCamera] = None,
        frigate_client: Optional[FrigateClient] = None,
        yolo: Optional[YOLODetector] = None,
        face: Optional[FaceDetector] = None,
        interval: float = 1.0,
        encode_frame: bool = False,
    ) -> None:
        if source not in ("local", "frigate"):
            raise ValueError(f"source must be 'local' or 'frigate', got {source!r}")

        self._source = source
        self._local = local_camera or LocalCamera()
        self._frigate = frigate_client or FrigateClient()
        self._yolo = yolo or YOLODetector()
        self._face = face or FaceDetector()
        self._interval = interval
        self._encode_frame = encode_frame

        self._context: VisionContext = VisionContext(source=source)
        self._task: Optional[asyncio.Task] = None
        self._running = False

    # ── Public API ────────────────────────────────────────────────────────────

    def get_context(self) -> VisionContext:
        """Return the most recently computed :class:`VisionContext`."""
        return self._context

    async def start(self) -> None:
        """Start the background capture-and-analyse loop."""
        if self._running:
            return

        if self._source == "local":
            self._local.open()
            if not self._yolo.is_loaded:
                await asyncio.get_event_loop().run_in_executor(None, self._yolo.load)

        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"[JARVIS] VisionManager started (source={self._source})")

    async def stop(self) -> None:
        """Stop the background loop and release resources."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._source == "local":
            self._local.close()

        logger.info("[JARVIS] VisionManager stopped")

    # ── Internal loop ─────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while self._running:
            try:
                frame = await self._capture_frame()
                if frame is not None:
                    self._context = await self._analyse(frame)
            except Exception as exc:
                logger.error(f"[JARVIS] VisionManager loop error: {exc}")
            await asyncio.sleep(self._interval)

    async def _capture_frame(self) -> Optional[np.ndarray]:
        if self._source == "local":
            return await self._local.read_frame_async()
        # frigate
        return await self._frigate.get_snapshot_array()

    async def _analyse(self, frame: np.ndarray) -> VisionContext:
        loop = asyncio.get_event_loop()

        # Run CPU-bound inference in thread pool
        objects = await loop.run_in_executor(None, self._yolo.detect, frame)
        faces = await loop.run_in_executor(None, self._face.recognise, frame)

        frame_b64: Optional[str] = None
        if self._encode_frame:
            frame_b64 = await loop.run_in_executor(None, _encode_jpeg, frame)

        return VisionContext(
            source=self._source,
            objects=objects,
            faces=faces,
            frame_b64=frame_b64,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _encode_jpeg(frame: np.ndarray) -> str:
    """Encode BGR frame to base64 JPEG string."""
    import cv2

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
    return base64.b64encode(buf.tobytes()).decode()
