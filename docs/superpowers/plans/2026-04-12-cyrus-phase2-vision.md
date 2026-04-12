# C.Y.R.U.S Phase 2 — Vision & Cameras Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real-time vision to C.Y.R.U.S — USB webcam capture, Frigate RTSP integration, YOLOv8n object detection, DeepFace face recognition, and vision context injected into LLM responses.

**Architecture:** A `VisionManager` orchestrates two camera sources (local USB + Frigate RTSP). Each frame is optionally processed by YOLOv8 (objects) and DeepFace (faces). Detected entities are serialised into a `VisionContext` dataclass that `LLMManager` injects as a system message prefix. The React frontend gains a `CameraStream` component showing the live feed with overlay annotations.

**Tech Stack:** OpenCV, ultralytics (YOLOv8n), deepface, httpx (Frigate API), websockets (frame push to frontend), Pillow, numpy.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `backend/modules/vision/__init__.py` | Module init |
| Create | `backend/modules/vision/camera_local.py` | USB webcam capture loop |
| Create | `backend/modules/vision/frigate_client.py` | Frigate RTSP + REST snapshot |
| Create | `backend/modules/vision/yolo_detector.py` | YOLOv8n object detection |
| Create | `backend/modules/vision/face_detector.py` | DeepFace face recognition |
| Create | `backend/modules/vision/vision_manager.py` | Orchestrates sources + detectors |
| Create | `backend/modules/vision/models.py` | `VisionContext` dataclass |
| Modify | `backend/core/cyrus_engine.py` | Wire VisionManager into pipeline |
| Modify | `backend/modules/llm/llm_manager.py` | Inject vision context into prompt |
| Modify | `config/config.yaml` | Add `vision:` section |
| Create | `frontend/src/components/CameraStream.tsx` | Live camera + detection overlay |
| Modify | `frontend/src/App.tsx` | Add CameraStream tab |
| Modify | `frontend/src/store/useCYRUSStore.ts` | Add vision state |
| Create | `tests/test_vision.py` | Vision module tests |
| Modify | `requirements.txt` | Add opencv, ultralytics, deepface |

---

## Task 1: Models & data structures

**Files:**
- Create: `backend/modules/vision/models.py`
- Create: `backend/modules/vision/__init__.py`

- [ ] **Step 1: Create `models.py`**

```python
"""C.Y.R.U.S — Vision data models."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class DetectedObject:
    label: str          # e.g. "person", "chair"
    confidence: float   # 0.0–1.0
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2


@dataclass
class DetectedFace:
    identity: str        # name or "unknown"
    confidence: float
    emotion: Optional[str] = None  # "happy", "neutral", …
    bbox: Optional[Tuple[int, int, int, int]] = None


@dataclass
class VisionContext:
    """Snapshot of what C.Y.R.U.S currently sees."""
    source: str                              # "local" | "frigate"
    objects: List[DetectedObject] = field(default_factory=list)
    faces: List[DetectedFace] = field(default_factory=list)
    frame_b64: Optional[str] = None         # base64 JPEG for frontend

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
```

- [ ] **Step 2: Create `__init__.py`**

```python
from backend.modules.vision.models import VisionContext, DetectedObject, DetectedFace
from backend.modules.vision.vision_manager import VisionManager

__all__ = ["VisionContext", "DetectedObject", "DetectedFace", "VisionManager"]
```

- [ ] **Step 3: Write test**

```python
# tests/test_vision.py
from backend.modules.vision.models import VisionContext, DetectedObject, DetectedFace

def test_empty_context_prompt():
    ctx = VisionContext(source="local")
    text = ctx.to_prompt_text()
    assert "[VISION" in text
    assert "No objects" in text

def test_objects_in_prompt():
    ctx = VisionContext(
        source="local",
        objects=[DetectedObject("person", 0.95, (0,0,100,200)),
                 DetectedObject("chair", 0.80, (200,0,300,200))]
    )
    text = ctx.to_prompt_text()
    assert "person" in text
    assert "chair" in text

def test_faces_in_prompt():
    ctx = VisionContext(
        source="local",
        faces=[DetectedFace("Ricardo", 0.92, emotion="neutral")]
    )
    text = ctx.to_prompt_text()
    assert "Ricardo" in text
    assert "neutral" in text
```

- [ ] **Step 4: Run tests**

```bat
venv\Scripts\activate
pytest tests/test_vision.py::test_empty_context_prompt tests/test_vision.py::test_objects_in_prompt tests/test_vision.py::test_faces_in_prompt -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**
```bat
git add backend/modules/vision/ tests/test_vision.py
git commit -m "feat(vision): add VisionContext data models"
```

---

## Task 2: USB Camera capture

**Files:**
- Create: `backend/modules/vision/camera_local.py`

- [ ] **Step 1: Create `camera_local.py`**

```python
"""C.Y.R.U.S — Local USB webcam capture."""
from __future__ import annotations
import asyncio
from typing import Optional
import numpy as np
from backend.utils.logger import get_logger
from backend.utils.exceptions import CYRUSError

logger = get_logger("cyrus.vision.local")


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
        self._running = False

    def open(self) -> None:
        """Open the camera device."""
        import cv2
        self._cap = cv2.VideoCapture(self._idx)
        if not self._cap.isOpened():
            raise CYRUSError(f"[C.Y.R.U.S] Cannot open camera {self._idx}")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        self._cap.set(cv2.CAP_PROP_FPS, self._fps)
        logger.info(f"[C.Y.R.U.S] Camera {self._idx} opened ({self._width}x{self._height})")

    def close(self) -> None:
        """Release the camera device."""
        if self._cap:
            self._cap.release()
            self._cap = None
        logger.info(f"[C.Y.R.U.S] Camera {self._idx} closed")

    def read_frame(self) -> Optional[np.ndarray]:
        """Read a single BGR frame. Returns None on failure."""
        if not self._cap:
            return None
        ret, frame = self._cap.read()
        if not ret:
            logger.warning(f"[C.Y.R.U.S] Camera {self._idx} frame read failed")
            return None
        return frame

    async def read_frame_async(self) -> Optional[np.ndarray]:
        """Read a frame without blocking the event loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.read_frame)

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()
```

- [ ] **Step 2: Add mock-based test**

```python
# in tests/test_vision.py
from unittest.mock import MagicMock, patch

def test_local_camera_open_fail():
    from backend.modules.vision.camera_local import LocalCamera
    from backend.utils.exceptions import CYRUSError
    with patch("cv2.VideoCapture") as mock_cap:
        mock_cap.return_value.isOpened.return_value = False
        cam = LocalCamera(device_index=99)
        try:
            cam.open()
            assert False, "Should raise"
        except CYRUSError:
            pass

def test_local_camera_read_none_when_closed():
    from backend.modules.vision.camera_local import LocalCamera
    cam = LocalCamera()
    assert cam.read_frame() is None
```

- [ ] **Step 3: Run tests**
```bat
pytest tests/test_vision.py -v -k "camera"
```
Expected: 2 passed

- [ ] **Step 4: Commit**
```bat
git add backend/modules/vision/camera_local.py tests/test_vision.py
git commit -m "feat(vision): add LocalCamera USB webcam capture"
```

---

## Task 3: Frigate RTSP client

**Files:**
- Create: `backend/modules/vision/frigate_client.py`

- [ ] **Step 1: Create `frigate_client.py`**

```python
"""C.Y.R.U.S — Frigate NVR integration.

Frigate exposes:
  GET /api/<camera>/latest.jpg   — latest JPEG snapshot
  GET /api/events                — recent detection events
"""
from __future__ import annotations
from typing import Optional
import httpx
from backend.utils.logger import get_logger
from backend.utils.exceptions import CYRUSError

logger = get_logger("cyrus.vision.frigate")


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
        """Return True if Frigate responds."""
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{self._host}/api/version")
                return r.status_code == 200
        except Exception:
            return False

    async def get_snapshot_bytes(self) -> Optional[bytes]:
        """Fetch the latest JPEG snapshot from Frigate.

        Returns:
            Raw JPEG bytes, or ``None`` if unavailable.
        """
        url = f"{self._host}/api/{self._camera}/latest.jpg"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    return r.content
                logger.warning(f"[C.Y.R.U.S] Frigate snapshot HTTP {r.status_code}")
                return None
        except Exception as exc:
            logger.warning(f"[C.Y.R.U.S] Frigate unreachable: {exc}")
            return None

    async def get_snapshot_array(self):
        """Return snapshot as numpy BGR array, or None."""
        import numpy as np
        import cv2
        raw = await self.get_snapshot_bytes()
        if raw is None:
            return None
        arr = np.frombuffer(raw, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return frame
```

- [ ] **Step 2: Add test**

```python
# in tests/test_vision.py
import pytest

@pytest.mark.asyncio
async def test_frigate_unavailable():
    from backend.modules.vision.frigate_client import FrigateClient
    client = FrigateClient(host="http://127.0.0.1:19999")  # nothing there
    available = await client.is_available()
    assert available is False

@pytest.mark.asyncio
async def test_frigate_snapshot_none_on_fail():
    from backend.modules.vision.frigate_client import FrigateClient
    client = FrigateClient(host="http://127.0.0.1:19999")
    result = await client.get_snapshot_bytes()
    assert result is None
```

- [ ] **Step 3: Run tests**
```bat
pytest tests/test_vision.py -v -k "frigate"
```
Expected: 2 passed

- [ ] **Step 4: Commit**
```bat
git add backend/modules/vision/frigate_client.py tests/test_vision.py
git commit -m "feat(vision): add FrigateClient RTSP/snapshot integration"
```

---

## Task 4: YOLOv8n object detector

**Files:**
- Create: `backend/modules/vision/yolo_detector.py`

- [ ] **Step 1: Create `yolo_detector.py`**

```python
"""C.Y.R.U.S — YOLOv8n real-time object detection."""
from __future__ import annotations
from pathlib import Path
from typing import List, Optional
import numpy as np
from backend.modules.vision.models import DetectedObject
from backend.utils.logger import get_logger

logger = get_logger("cyrus.vision.yolo")

_MODEL_NAME = "yolov8n.pt"  # auto-downloaded by ultralytics on first use


class YOLODetector:
    """YOLOv8-nano object detector.

    Args:
        model_name: YOLO model filename (auto-downloaded if absent).
        confidence: Minimum confidence threshold (0.0–1.0).
        device: ``"cuda"`` or ``"cpu"``.
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
        """Load the YOLO model (downloads if not cached)."""
        from ultralytics import YOLO
        self._model = YOLO(self._model_name)
        logger.info(f"[C.Y.R.U.S] YOLOv8 model loaded: {self._model_name}")

    def detect(self, frame: np.ndarray) -> List[DetectedObject]:
        """Run inference on a BGR numpy frame.

        Args:
            frame: OpenCV BGR image array.

        Returns:
            List of detected objects sorted by confidence descending.
        """
        if self._model is None:
            logger.warning("[C.Y.R.U.S] YOLO model not loaded — call load() first")
            return []

        try:
            results = self._model(frame, conf=self._confidence,
                                  device=self._device, verbose=False)
            objects: List[DetectedObject] = []
            for r in results:
                for box in r.boxes:
                    label = r.names[int(box.cls)]
                    conf = float(box.conf)
                    x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
                    objects.append(DetectedObject(label, conf, (x1, y1, x2, y2)))
            objects.sort(key=lambda o: o.confidence, reverse=True)
            return objects
        except Exception as exc:
            logger.error(f"[C.Y.R.U.S] YOLO inference failed: {exc}")
            return []

    @property
    def is_loaded(self) -> bool:
        return self._model is not None
```

- [ ] **Step 2: Add test (mocked — no GPU required)**

```python
# in tests/test_vision.py
from unittest.mock import MagicMock, patch
import numpy as np

def test_yolo_not_loaded_returns_empty():
    from backend.modules.vision.yolo_detector import YOLODetector
    det = YOLODetector()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = det.detect(frame)
    assert result == []

def test_yolo_detect_mocked():
    from backend.modules.vision.yolo_detector import YOLODetector
    from backend.modules.vision.models import DetectedObject
    det = YOLODetector()

    # Mock the YOLO model results
    mock_box = MagicMock()
    mock_box.cls = [0]
    mock_box.conf = [0.92]
    mock_box.xyxy = [MagicMock()]
    mock_box.xyxy[0].__iter__ = lambda s: iter([10, 20, 100, 200])

    mock_result = MagicMock()
    mock_result.names = {0: "person"}
    mock_result.boxes = [mock_box]

    det._model = MagicMock(return_value=[mock_result])
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    objects = det.detect(frame)
    assert len(objects) == 1
    assert objects[0].label == "person"
```

- [ ] **Step 3: Run tests**
```bat
pytest tests/test_vision.py -v -k "yolo"
```
Expected: 2 passed

- [ ] **Step 4: Commit**
```bat
git add backend/modules/vision/yolo_detector.py tests/test_vision.py
git commit -m "feat(vision): add YOLOv8n object detector"
```

---

## Task 5: DeepFace face recogniser

**Files:**
- Create: `backend/modules/vision/face_detector.py`

- [ ] **Step 1: Create `face_detector.py`**

```python
"""C.Y.R.U.S — DeepFace face recognition and emotion detection."""
from __future__ import annotations
from pathlib import Path
from typing import List
import numpy as np
from backend.modules.vision.models import DetectedFace
from backend.utils.logger import get_logger

logger = get_logger("cyrus.vision.face")

# Known faces DB — directory of <name>/<photo.jpg> pairs
_DEFAULT_DB = Path("data/faces")


class FaceDetector:
    """DeepFace-based face recognition + emotion analysis.

    Args:
        db_path: Path to the face database directory.
        model_name: DeepFace recognition model.
        detector_backend: Face detector backend.
        enforce_detection: Raise if no face found (False = return empty).
    """

    def __init__(
        self,
        db_path: Path = _DEFAULT_DB,
        model_name: str = "Facenet512",
        detector_backend: str = "retinaface",
        enforce_detection: bool = False,
    ) -> None:
        self._db = db_path
        self._model = model_name
        self._backend = detector_backend
        self._enforce = enforce_detection

    def recognise(self, frame: np.ndarray) -> List[DetectedFace]:
        """Recognise faces and detect emotions in *frame*.

        Args:
            frame: OpenCV BGR frame.

        Returns:
            List of DetectedFace results (empty if none found).
        """
        try:
            from deepface import DeepFace
        except ImportError:
            logger.warning("[C.Y.R.U.S] deepface not installed; face detection skipped")
            return []

        faces: List[DetectedFace] = []

        # Emotion analysis (runs on every face found)
        try:
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
                    region.get("x", 0), region.get("y", 0),
                    region.get("x", 0) + region.get("w", 0),
                    region.get("y", 0) + region.get("h", 0),
                )
                emotion = res.get("dominant_emotion", "neutral")
                faces.append(DetectedFace("unknown", 0.0, emotion=emotion, bbox=bbox))
        except Exception as exc:
            logger.debug(f"[C.Y.R.U.S] Emotion analysis skipped: {exc}")

        # Identity recognition (requires face DB)
        if self._db.exists() and list(self._db.iterdir()):
            try:
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
```

- [ ] **Step 2: Add test**

```python
# in tests/test_vision.py
def test_face_detector_no_deepface():
    """Should return empty list gracefully if deepface not installed."""
    from backend.modules.vision.face_detector import FaceDetector
    import sys
    import numpy as np
    # Temporarily hide deepface
    deepface_mod = sys.modules.pop("deepface", None)
    try:
        det = FaceDetector()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = det.recognise(frame)
        assert result == []
    finally:
        if deepface_mod:
            sys.modules["deepface"] = deepface_mod
```

- [ ] **Step 3: Run test**
```bat
pytest tests/test_vision.py::test_face_detector_no_deepface -v
```
Expected: 1 passed

- [ ] **Step 4: Commit**
```bat
git add backend/modules/vision/face_detector.py tests/test_vision.py
git commit -m "feat(vision): add DeepFace face recognition module"
```

---

## Task 6: VisionManager orchestrator

**Files:**
- Create: `backend/modules/vision/vision_manager.py`

- [ ] **Step 1: Create `vision_manager.py`**

```python
"""C.Y.R.U.S — Vision pipeline orchestrator."""
from __future__ import annotations
import asyncio
import base64
from typing import Optional
import cv2
import numpy as np
from backend.modules.vision.camera_local import LocalCamera
from backend.modules.vision.frigate_client import FrigateClient
from backend.modules.vision.yolo_detector import YOLODetector
from backend.modules.vision.face_detector import FaceDetector
from backend.modules.vision.models import VisionContext
from backend.utils.logger import get_logger

logger = get_logger("cyrus.vision")


class VisionManager:
    """Orchestrates camera sources and vision detectors.

    Args:
        local_camera: LocalCamera instance (or None to disable).
        frigate: FrigateClient instance (or None to disable).
        yolo: YOLODetector instance (or None to disable).
        face_detector: FaceDetector instance (or None to disable).
        prefer_frigate: If True, try Frigate before local camera.
    """

    def __init__(
        self,
        local_camera: Optional[LocalCamera] = None,
        frigate: Optional[FrigateClient] = None,
        yolo: Optional[YOLODetector] = None,
        face_detector: Optional[FaceDetector] = None,
        prefer_frigate: bool = False,
    ) -> None:
        self._local = local_camera
        self._frigate = frigate
        self._yolo = yolo
        self._face = face_detector
        self._prefer_frigate = prefer_frigate
        self._last_context: Optional[VisionContext] = None

    async def capture_and_analyse(self) -> Optional[VisionContext]:
        """Capture a frame and run detection pipeline.

        Returns:
            VisionContext with detections, or None if no source available.
        """
        frame, source = await self._capture_frame()
        if frame is None:
            return None

        objects = self._yolo.detect(frame) if self._yolo and self._yolo.is_loaded else []
        faces = self._face.recognise(frame) if self._face else []

        # Encode frame as base64 JPEG for frontend
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        frame_b64 = base64.b64encode(buf.tobytes()).decode()

        ctx = VisionContext(
            source=source,
            objects=objects,
            faces=faces,
            frame_b64=frame_b64,
        )
        self._last_context = ctx
        logger.debug(
            f"[C.Y.R.U.S] Vision: {len(objects)} objects, {len(faces)} faces [{source}]"
        )
        return ctx

    @property
    def last_context(self) -> Optional[VisionContext]:
        return self._last_context

    async def _capture_frame(self):
        """Try sources in priority order. Returns (frame, source_name)."""
        sources = []
        if self._prefer_frigate:
            sources = [("frigate", self._get_frigate_frame),
                       ("local", self._get_local_frame)]
        else:
            sources = [("local", self._get_local_frame),
                       ("frigate", self._get_frigate_frame)]

        for name, getter in sources:
            frame = await getter()
            if frame is not None:
                return frame, name
        return None, "none"

    async def _get_local_frame(self):
        if self._local and self._local.is_open:
            return await self._local.read_frame_async()
        return None

    async def _get_frigate_frame(self):
        if self._frigate:
            return await self._frigate.get_snapshot_array()
        return None
```

- [ ] **Step 2: Add test**

```python
# in tests/test_vision.py
@pytest.mark.asyncio
async def test_vision_manager_no_sources():
    from backend.modules.vision.vision_manager import VisionManager
    vm = VisionManager()
    ctx = await vm.capture_and_analyse()
    assert ctx is None

@pytest.mark.asyncio
async def test_vision_manager_with_mock_camera():
    from backend.modules.vision.vision_manager import VisionManager
    from backend.modules.vision.camera_local import LocalCamera
    import numpy as np

    mock_cam = MagicMock(spec=LocalCamera)
    mock_cam.is_open = True
    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    mock_cam.read_frame_async = asyncio.coroutine(lambda: fake_frame)

    vm = VisionManager(local_camera=mock_cam)
    ctx = await vm.capture_and_analyse()
    assert ctx is not None
    assert ctx.source == "local"
    assert ctx.frame_b64 is not None
```

- [ ] **Step 3: Run tests**
```bat
pytest tests/test_vision.py -v -k "vision_manager"
```
Expected: 2 passed

- [ ] **Step 4: Commit**
```bat
git add backend/modules/vision/vision_manager.py tests/test_vision.py
git commit -m "feat(vision): add VisionManager pipeline orchestrator"
```

---

## Task 7: Wire vision into CYRUSEngine + LLMManager

**Files:**
- Modify: `backend/core/cyrus_engine.py`
- Modify: `backend/modules/llm/llm_manager.py`
- Modify: `config/config.yaml`

- [ ] **Step 1: Add `vision:` block to `config/config.yaml`**

```yaml
# ── Vision (Phase 2) ──────────────────────────────────────────────────────────
vision:
  enabled: false                # set true to activate
  source: "local"               # "local" | "frigate" | "both"
  prefer_frigate: false

  local_camera:
    device_index: 0
    width: 640
    height: 480
    fps: 15

  frigate:
    host: "http://192.168.1.50:5000"
    camera: "default"
    timeout: 5

  yolo:
    enabled: true
    model: "yolov8n.pt"
    confidence: 0.45
    device: "cuda"

  face:
    enabled: true
    db_path: "data/faces"
    model: "Facenet512"
```

- [ ] **Step 2: Add vision context injection to `LLMManager.generate()`**

In `backend/modules/llm/llm_manager.py`, add `vision_context` parameter:

```python
async def generate(
    self,
    user_input: str,
    history: list[dict] | None = None,
    language: str = "es",
    turn_count: int = 0,
    vision_context=None,        # NEW: Optional[VisionContext]
) -> str:
    system = self._build_system_prompt(language, turn_count, vision_context)
    # … rest unchanged
```

Update `_build_system_prompt`:

```python
def _build_system_prompt(self, language, turn_count, vision_context=None) -> str:
    parts = [self._soul_text]
    parts.append(self._prompts.get("context_template", "").format(
        current_time=current_time_str(),
        language=language,
        turn_count=turn_count,
    ))
    if vision_context is not None:
        parts.append(vision_context.to_prompt_text())   # NEW
    return "\n\n".join(p for p in parts if p.strip())
```

- [ ] **Step 3: Wire VisionManager in `CYRUSEngine.__init__()`**

```python
# After TTS init, before WebSocket init:
from backend.modules.vision.vision_manager import VisionManager
from backend.modules.vision.camera_local import LocalCamera
from backend.modules.vision.frigate_client import FrigateClient
from backend.modules.vision.yolo_detector import YOLODetector
from backend.modules.vision.face_detector import FaceDetector

vis_cfg = self._cfg.get("vision", {})
self._vision: Optional[VisionManager] = None
if vis_cfg.get("enabled", False):
    local_cam = LocalCamera(**vis_cfg.get("local_camera", {})) if vis_cfg.get("source") in ("local","both") else None
    if local_cam:
        local_cam.open()
    frigate = FrigateClient(**vis_cfg.get("frigate", {})) if vis_cfg.get("source") in ("frigate","both") else None
    yolo = YOLODetector(**vis_cfg.get("yolo", {})) if vis_cfg.get("yolo", {}).get("enabled") else None
    if yolo:
        await loop.run_in_executor(None, yolo.load)
    face_det = FaceDetector(**vis_cfg.get("face", {})) if vis_cfg.get("face", {}).get("enabled") else None
    self._vision = VisionManager(
        local_camera=local_cam,
        frigate=frigate,
        yolo=yolo,
        face_detector=face_det,
        prefer_frigate=vis_cfg.get("prefer_frigate", False),
    )
    logger.info("[C.Y.R.U.S] Vision pipeline enabled")
```

In `_process_one_turn`, after trigger detection and before LLM call:

```python
# 3b. Capture vision context (if enabled)
vision_ctx = None
if self._vision:
    try:
        vision_ctx = await self._vision.capture_and_analyse()
        if vision_ctx:
            await self._bus.emit("vision", {"frame": vision_ctx.frame_b64})
    except Exception as exc:
        logger.warning(f"[C.Y.R.U.S] Vision capture failed: {exc}")

# 4. LLM inference (pass vision_ctx)
response = await self._llm.generate(
    clean_input,
    history=...,
    language=lang,
    turn_count=...,
    vision_context=vision_ctx,   # NEW
)
```

- [ ] **Step 4: Run full test suite**
```bat
pytest tests/ -v --tb=short
```
Expected: all prior tests still pass

- [ ] **Step 5: Commit**
```bat
git add backend/ config/config.yaml tests/
git commit -m "feat(vision): wire VisionManager into CYRUSEngine + LLMManager"
```

---

## Task 8: Frontend CameraStream component

**Files:**
- Create: `frontend/src/components/CameraStream.tsx`
- Modify: `frontend/src/store/useCYRUSStore.ts`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add vision state to Zustand store**

In `useCYRUSStore.ts`, add:
```typescript
// Vision state
cameraFrame: string | null        // base64 JPEG
setCameraFrame: (frame: string | null) => void
```

- [ ] **Step 2: Handle `vision` WS message in `useWebSocket.ts`**

```typescript
case "vision":
  if (data.frame) useCYRUSStore.getState().setCameraFrame(data.frame)
  break
```

- [ ] **Step 3: Create `CameraStream.tsx`**

```tsx
import { useCYRUSStore } from '../store/useCYRUSStore'

export function CameraStream() {
  const frame = useCYRUSStore((s) => s.cameraFrame)

  if (!frame) {
    return (
      <div className="flex items-center justify-center h-48 border border-cyan-900 rounded bg-black/40">
        <span className="font-mono text-xs text-cyan-700 tracking-widest">
          CAMERA OFFLINE
        </span>
      </div>
    )
  }

  return (
    <div className="relative rounded overflow-hidden border border-cyan-800">
      <img
        src={`data:image/jpeg;base64,${frame}`}
        alt="C.Y.R.U.S vision"
        className="w-full object-contain"
      />
      <div className="absolute top-2 left-2">
        <span className="font-mono text-xs text-green-400 bg-black/60 px-1 rounded">
          LIVE
        </span>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Add camera tab to `App.tsx`**

Add a "VISION" tab in the tab bar that shows `<CameraStream />` alongside the hologram.

- [ ] **Step 5: Commit**
```bat
git add frontend/src/
git commit -m "feat(vision): add CameraStream frontend component"
```

---

## Task 9: Install dependencies + update requirements.txt

- [ ] **Step 1: Install vision packages**

```bat
venv\Scripts\activate
pip install opencv-python==4.10.0.84 ultralytics==8.2.24 deepface==0.0.93 Pillow==10.4.0
```

- [ ] **Step 2: Update `requirements.txt`**

```
# ── Vision (Phase 2) ──────────────────────────────────────────────────────────
opencv-python==4.10.0.84
ultralytics==8.2.24
deepface==0.0.93
Pillow==10.4.0
```

- [ ] **Step 3: Run all tests**
```bat
pytest tests/ -v
```
Expected: all pass + 6 skipped

- [ ] **Step 4: Final commit**
```bat
git add requirements.txt
git commit -m "feat(vision): Phase 2 complete — vision pipeline fully integrated"
```

---

## Success Criteria

- [ ] `pytest tests/ -v` → all tests pass
- [ ] `vision.enabled: true` in config → camera opens, YOLO runs, faces detected
- [ ] LLM responses reference objects seen ("I can see a person and a chair")
- [ ] Frontend shows live camera frame in VISION tab
- [ ] Frigate fallback works when local camera unavailable
- [ ] All new code has `[C.Y.R.U.S]` log prefix
