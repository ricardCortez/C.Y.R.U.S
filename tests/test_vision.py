"""C.Y.R.U.S — Tests for the Vision pipeline (Phase 2).

All tests are hardware-free — cameras and ML models are mocked.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Task 1 — VisionContext models
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_context_prompt():
    from backend.modules.vision.models import VisionContext
    ctx = VisionContext(source="local")
    text = ctx.to_prompt_text()
    assert "[VISION" in text
    assert "No objects" in text


def test_objects_in_prompt():
    from backend.modules.vision.models import VisionContext, DetectedObject
    ctx = VisionContext(
        source="local",
        objects=[
            DetectedObject("person", 0.95, (0, 0, 100, 200)),
            DetectedObject("chair",  0.80, (200, 0, 300, 200)),
        ],
    )
    text = ctx.to_prompt_text()
    assert "person" in text
    assert "chair" in text


def test_faces_in_prompt():
    from backend.modules.vision.models import VisionContext, DetectedFace
    ctx = VisionContext(
        source="local",
        faces=[DetectedFace("Ricardo", 0.92, emotion="neutral")],
    )
    text = ctx.to_prompt_text()
    assert "Ricardo" in text
    assert "neutral" in text
