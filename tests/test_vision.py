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


# ─────────────────────────────────────────────────────────────────────────────
# Task 2 — LocalCamera
# ─────────────────────────────────────────────────────────────────────────────

def test_local_camera_open_fail():
    from backend.modules.vision.camera_local import LocalCamera
    from backend.utils.exceptions import CYRUSError

    with patch("cv2.VideoCapture") as MockCap:
        MockCap.return_value.isOpened.return_value = False
        cam = LocalCamera(device_index=99)
        with pytest.raises(CYRUSError):
            cam.open()


def test_local_camera_read_none_when_closed():
    from backend.modules.vision.camera_local import LocalCamera

    cam = LocalCamera()
    assert cam.read_frame() is None
    assert not cam.is_open


def test_local_camera_read_frame_ok():
    from backend.modules.vision.camera_local import LocalCamera

    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    with patch("cv2.VideoCapture") as MockCap:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, fake_frame)
        MockCap.return_value = mock_cap

        cam = LocalCamera()
        cam.open()
        frame = cam.read_frame()
        assert frame is not None
        assert frame.shape == (480, 640, 3)


# ─────────────────────────────────────────────────────────────────────────────
# Task 3 — FrigateClient
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_frigate_unavailable():
    from backend.modules.vision.frigate_client import FrigateClient
    client = FrigateClient(host="http://127.0.0.1:19999")
    available = await client.is_available()
    assert available is False


@pytest.mark.asyncio
async def test_frigate_snapshot_none_on_fail():
    from backend.modules.vision.frigate_client import FrigateClient
    client = FrigateClient(host="http://127.0.0.1:19999")
    result = await client.get_snapshot_bytes()
    assert result is None
