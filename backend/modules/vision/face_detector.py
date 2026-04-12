"""C.Y.R.U.S — DeepFace face recognition and emotion detection."""
from __future__ import annotations

from pathlib import Path
from typing import List

import numpy as np

from backend.modules.vision.models import DetectedFace
from backend.utils.logger import get_logger

logger = get_logger("cyrus.vision.face")

# Known-faces DB — directory of  <name>/<photo.jpg>  pairs
_DEFAULT_DB = Path("data/faces")


class FaceDetector:
    """DeepFace-based face recognition + emotion analysis.

    Args:
        db_path: Directory containing labelled face images for recognition.
        model_name: DeepFace recognition model (e.g. ``"Facenet512"``).
        detector_backend: Face detector backend (e.g. ``"retinaface"``).
        enforce_detection: Raise if no face found; ``False`` returns empty list.
    """

    def __init__(
        self,
        db_path: Path = _DEFAULT_DB,
        model_name: str = "Facenet512",
        detector_backend: str = "retinaface",
        enforce_detection: bool = False,
    ) -> None:
        self._db = Path(db_path)
        self._model = model_name
        self._backend = detector_backend
        self._enforce = enforce_detection

    def recognise(self, frame: np.ndarray) -> List[DetectedFace]:
        """Recognise faces and detect emotions in *frame*.

        Args:
            frame: OpenCV BGR image array.

        Returns:
            List of :class:`DetectedFace` results (empty if none found or
            deepface is not installed).
        """
        try:
            from deepface import DeepFace  # noqa: F401
        except ImportError:
            logger.warning("[C.Y.R.U.S] deepface not installed; face detection skipped")
            return []

        faces: List[DetectedFace] = []

        # ── Emotion analysis (works without DB) ───────────────────────────
        try:
            from deepface import DeepFace
            emotion_results = DeepFace.analyze(
                frame,
                actions=["emotion"],
                enforce_detection=self._enforce,
                silent=True,
                detector_backend=self._backend,
            )
            for res in emotion_results:
                region = res.get("region", {})
                bbox = (
                    region.get("x", 0),
                    region.get("y", 0),
                    region.get("x", 0) + region.get("w", 0),
                    region.get("y", 0) + region.get("h", 0),
                )
                emotion = res.get("dominant_emotion", "neutral")
                faces.append(
                    DetectedFace("unknown", 0.0, emotion=emotion, bbox=bbox)
                )
        except Exception as exc:
            logger.debug(f"[C.Y.R.U.S] Emotion analysis skipped: {exc}")

        # ── Identity recognition (requires face DB) ───────────────────────
        if self._db.exists() and any(self._db.iterdir()):
            try:
                from deepface import DeepFace
                id_results = DeepFace.find(
                    frame,
                    db_path=str(self._db),
                    model_name=self._model,
                    enforce_detection=self._enforce,
                    silent=True,
                    detector_backend=self._backend,
                )
                for i, df in enumerate(id_results):
                    if not df.empty:
                        best = df.iloc[0]
                        identity = Path(best["identity"]).parent.name
                        dist = float(best.get("distance", 1.0))
                        confidence = max(0.0, 1.0 - dist)
                        if i < len(faces):
                            faces[i].identity = identity
                            faces[i].confidence = confidence
            except Exception as exc:
                logger.debug(f"[C.Y.R.U.S] Face recognition skipped: {exc}")

        return faces
