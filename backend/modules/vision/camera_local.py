"""JARVIS — Local USB webcam capture."""
from __future__ import annotations

import asyncio
from typing import Optional

import numpy as np

from backend.utils.exceptions import JARVISError
from backend.utils.logger import get_logger

logger = get_logger("jarvis.vision.local")


class LocalCamera:
    """Async wrapper around OpenCV VideoCapture.

    Args:
        device_index: Camera device index (0 = default webcam).
        width: Capture width in pixels.
        height: Capture height in pixels.
        fps: Target capture FPS (approximate).
    """

    def __init__(
        self,
        device_index: int = 0,
        width: int = 640,
        height: int = 480,
        fps: int = 15,
    ) -> None:
        self._idx = device_index
        self._width = width
        self._height = height
        self._fps = fps
        self._cap = None

    def open(self) -> None:
        """Open the camera device.

        Raises:
            JARVISError: If the device cannot be opened.
        """
        import cv2

        self._cap = cv2.VideoCapture(self._idx)
        if not self._cap.isOpened():
            self._cap = None
            raise JARVISError(f"[JARVIS] Cannot open camera device {self._idx}")

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        self._cap.set(cv2.CAP_PROP_FPS, self._fps)
        logger.info(f"[JARVIS] Camera {self._idx} opened ({self._width}x{self._height}@{self._fps}fps)")

    def close(self) -> None:
        """Release the camera device."""
        if self._cap:
            self._cap.release()
            self._cap = None
        logger.info(f"[JARVIS] Camera {self._idx} closed")

    def read_frame(self) -> Optional[np.ndarray]:
        """Read a single BGR frame synchronously.

        Returns:
            BGR numpy array, or ``None`` if read failed.
        """
        if not self._cap:
            return None
        ret, frame = self._cap.read()
        if not ret:
            logger.warning(f"[JARVIS] Camera {self._idx} frame read failed")
            return None
        return frame

    async def read_frame_async(self) -> Optional[np.ndarray]:
        """Read a frame without blocking the asyncio event loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.read_frame)

    @property
    def is_open(self) -> bool:
        """True if the camera is currently open."""
        return self._cap is not None and self._cap.isOpened()

    @staticmethod
    def list_devices(max_index: int = 5) -> list[int]:
        """Return indices of available camera devices.

        Args:
            max_index: Highest device index to probe.

        Returns:
            List of working device indices.
        """
        import cv2

        available = []
        for i in range(max_index):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                available.append(i)
                cap.release()
        return available
