"""
SmartCCTV SIH26187 — YOLOv8 + ByteTrack Perception Worker.

Wraps Ultralytics YOLOv8 with ByteTrack multi-object tracking.
Detects and tracks persons, vehicles with per-class filtering.
Maintains centroid and bounding-box height history for downstream
pose and behavioural analysis.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch

from backend.config import settings

logger = logging.getLogger(__name__)

# COCO class indices we care about:  person, car, motorcycle, bus, truck
TRACKED_CLASSES: Dict[int, str] = {
    0: "person",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

# History buffer depth (frames)
_HISTORY_DEPTH = 150

# Colour palette for track ID annotation
_PALETTE = [
    (0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0),
    (0, 255, 255), (255, 0, 255), (128, 255, 0), (0, 128, 255),
]


# ---------------------------------------------------------------------------
# Device Selection
# ---------------------------------------------------------------------------


def auto_select_device() -> str:
    """Select CUDA if available and enabled in config, otherwise CPU.

    Returns:
        Device string: 'cuda:0' or 'cpu'.
    """
    if settings.USE_GPU and torch.cuda.is_available():
        device = "cuda:0"
        gpu_name = torch.cuda.get_device_name(0)
        logger.info("Perception engine using GPU: %s", gpu_name)
    else:
        device = "cpu"
        logger.info("Perception engine using CPU.")
    return device


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class PerceptionConfig:
    """Configuration for the YOLO detector."""

    model_path: str = settings.YOLO_MODEL
    device: str = field(default_factory=auto_select_device)
    analytics_fps: int = settings.ANALYTICS_FPS
    confidence_threshold: float = 0.45
    iou_threshold: float = 0.45


@dataclass
class Detection:
    """A single tracked object detection."""

    track_id: int
    object_class: str
    confidence: float
    bbox: Tuple[float, float, float, float]   # x1, y1, x2, y2
    centroid: Tuple[float, float]
    camera_id: str
    timestamp: datetime
    model_version: str
    frame_number: int


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class Detector:
    """YOLOv8 detector with ByteTrack multi-object tracking.

    Maintains per-track centroid and bbox-height history buffers to
    provide trajectory and pose baseline data to downstream engines.
    """

    def __init__(self, config: Optional[PerceptionConfig] = None) -> None:
        """Load the YOLO model and initialise ByteTrack.

        Args:
            config: PerceptionConfig; uses defaults from settings if None.
        """
        self.config = config or PerceptionConfig()
        self._model: Optional[object] = None
        self._model_version = "yolov8-unknown"

        # Per-track history deques: {track_id -> deque[(x, y)]}
        self._centroid_history: Dict[int, Deque[Tuple[float, float]]] = defaultdict(
            lambda: deque(maxlen=_HISTORY_DEPTH)
        )
        # Per-track bbox height history: {track_id -> deque[height]}
        self._height_history: Dict[int, Deque[float]] = defaultdict(
            lambda: deque(maxlen=_HISTORY_DEPTH)
        )

        self._load_model()

    def _load_model(self) -> None:
        """Load YOLOv8 model with graceful fallback from configured path."""
        try:
            from ultralytics import YOLO

            model_path = self.config.model_path

            # Try configured path, then yolov8n fallback.
            if not Path(model_path).exists():
                logger.warning(
                    "Model not found at %s; trying ultralytics default.", model_path
                )
                model_path = "yolov8n.pt"

            self._model = YOLO(model_path)
            self._model.to(self.config.device)  # type: ignore[union-attr]

            # Extract version from filename.
            self._model_version = Path(model_path).stem
            logger.info(
                "YOLOv8 model loaded: %s on %s", model_path, self.config.device
            )
        except Exception as exc:
            logger.error("Failed to load YOLOv8 model: %s", exc)
            self._model = None

    def detect_and_track(
        self,
        frame: np.ndarray,
        camera_id: str,
        frame_number: int,
        timestamp: datetime,
    ) -> List[Detection]:
        """Run inference + ByteTrack on a single frame.

        Args:
            frame:        BGR NumPy array.
            camera_id:    Source camera identifier.
            frame_number: Sequential frame counter.
            timestamp:    UTC timestamp of frame capture.

        Returns:
            List of Detection objects for tracked objects.
        """
        if self._model is None:
            return []

        try:
            results = self._model.track(  # type: ignore[union-attr]
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                conf=self.config.confidence_threshold,
                iou=self.config.iou_threshold,
                device=self.config.device,
                classes=list(TRACKED_CLASSES.keys()),
                verbose=False,
            )
        except Exception as exc:
            logger.error("YOLO inference failed on frame %d: %s", frame_number, exc)
            return []

        detections: List[Detection] = []

        if not results or results[0].boxes is None:
            return detections

        boxes = results[0].boxes
        for box in boxes:
            if box.id is None:
                continue

            track_id = int(box.id.item())
            cls_id = int(box.cls.item())
            conf = float(box.conf.item())
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])

            if cls_id not in TRACKED_CLASSES:
                continue

            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            height = y2 - y1

            self._centroid_history[track_id].append((cx, cy))
            self._height_history[track_id].append(height)

            detections.append(
                Detection(
                    track_id=track_id,
                    object_class=TRACKED_CLASSES[cls_id],
                    confidence=conf,
                    bbox=(x1, y1, x2, y2),
                    centroid=(cx, cy),
                    camera_id=camera_id,
                    timestamp=timestamp,
                    model_version=self._model_version,
                    frame_number=frame_number,
                )
            )

        return detections

    def get_centroid_history(self, track_id: int) -> List[Tuple[float, float]]:
        """Return the stored centroid history for a track.

        Args:
            track_id: The ByteTrack track ID.

        Returns:
            List of (cx, cy) tuples, oldest first.
        """
        return list(self._centroid_history.get(track_id, deque()))

    def get_height_history(self, track_id: int) -> List[float]:
        """Return the stored bounding-box height history for a track.

        Args:
            track_id: The ByteTrack track ID.

        Returns:
            List of height values in pixels, oldest first.
        """
        return list(self._height_history.get(track_id, deque()))

    def annotate_frame(
        self, frame: np.ndarray, detections: List[Detection]
    ) -> np.ndarray:
        """Draw bounding boxes, track IDs, and class labels on a frame copy.

        Args:
            frame:      Original BGR frame.
            detections: List of detections to annotate.

        Returns:
            Annotated BGR frame (copy of input).
        """
        annotated = frame.copy()
        for det in detections:
            x1, y1, x2, y2 = (int(v) for v in det.bbox)
            colour = _PALETTE[det.track_id % len(_PALETTE)]
            cv2.rectangle(annotated, (x1, y1), (x2, y2), colour, 2)
            label = f"{det.object_class} #{det.track_id} {det.confidence:.2f}"
            cv2.putText(
                annotated,
                label,
                (x1, y1 - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                colour,
                1,
                cv2.LINE_AA,
            )
        return annotated

    @property
    def model_version(self) -> str:
        """Return the loaded model version string."""
        return self._model_version
