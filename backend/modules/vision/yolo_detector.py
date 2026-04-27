"""JARVIS — YOLOv8n real-time object detection."""
from __future__ import annotations

from typing import List

import numpy as np

from backend.modules.vision.models import DetectedObject
from backend.utils.logger import get_logger

logger = get_logger("jarvis.vision.yolo")

_MODEL_NAME = "yolov8n.pt"   # auto-downloaded by ultralytics on first use


class YOLODetector:
    """YOLOv8-nano object detector.

    Args:
        model_name: YOLO model file (downloaded automatically if absent).
        confidence: Minimum detection confidence threshold (0.0–1.0).
        device: ``"cuda"`` for GPU inference or ``"cpu"`` for CPU fallback.
    """

    def __init__(
        self,
        model_name: str = _MODEL_NAME,
        confidence: float = 0.45,
        device: str = "cuda",
    ) -> None:
        self._model_name = model_name
        self._confidence = confidence
        self._device = device
        self._model = None

    def load(self) -> None:
        """Load the YOLO model (downloads weights if not cached)."""
        from ultralytics import YOLO

        self._model = YOLO(self._model_name)
        logger.info(f"[JARVIS] YOLOv8 model loaded: {self._model_name}")

    def detect(self, frame: np.ndarray) -> List[DetectedObject]:
        """Run inference on a BGR numpy frame.

        Args:
            frame: OpenCV BGR image array.

        Returns:
            List of ``DetectedObject`` instances sorted by confidence descending.
            Returns empty list if model is not loaded or inference fails.
        """
        if self._model is None:
            logger.warning("[JARVIS] YOLO model not loaded — call load() first")
            return []

        try:
            results = self._model(
                frame,
                conf=self._confidence,
                device=self._device,
                verbose=False,
            )
            objects: List[DetectedObject] = []
            for r in results:
                for box in r.boxes:
                    label = r.names[int(box.cls[0])]
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
                    objects.append(DetectedObject(label, conf, (x1, y1, x2, y2)))

            objects.sort(key=lambda o: o.confidence, reverse=True)
            return objects

        except Exception as exc:
            logger.error(f"[JARVIS] YOLO inference failed: {exc}")
            return []

    @property
    def is_loaded(self) -> bool:
        """True if the model weights are loaded and ready."""
        return self._model is not None
