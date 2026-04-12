"""C.Y.R.U.S — Vision data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class DetectedObject:
    label: str                           # e.g. "person", "chair"
    confidence: float                    # 0.0–1.0
    bbox: Tuple[int, int, int, int]      # x1, y1, x2, y2


@dataclass
class DetectedFace:
    identity: str                        # name or "unknown"
    confidence: float
    emotion: Optional[str] = None        # "happy", "neutral", …
    bbox: Optional[Tuple[int, int, int, int]] = None


@dataclass
class VisionContext:
    """Snapshot of what C.Y.R.U.S currently sees."""

    source: str                                          # "local" | "frigate"
    objects: List[DetectedObject] = field(default_factory=list)
    faces: List[DetectedFace] = field(default_factory=list)
    frame_b64: Optional[str] = None                     # base64 JPEG for frontend

    def to_prompt_text(self) -> str:
        """Serialise vision context for LLM injection."""
        parts = [f"[VISION — source: {self.source}]"]

        if self.objects:
            obj_str = ", ".join(
                f"{o.label} ({o.confidence:.0%})" for o in self.objects[:10]
            )
            parts.append(f"Objects detected: {obj_str}.")

        if self.faces:
            face_str = ", ".join(
                f"{f.identity}" + (f" ({f.emotion})" if f.emotion else "")
                for f in self.faces[:5]
            )
            parts.append(f"People detected: {face_str}.")

        if not self.objects and not self.faces:
            parts.append("No objects or people detected.")

        return " ".join(parts)
