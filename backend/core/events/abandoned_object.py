"""
SmartCCTV SIH26187 — Abandoned Object Detection.

Tracks person-object co-location, detects when associated persons move
away and objects remain stationary beyond the configured threshold.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from backend.config import settings

logger = logging.getLogger(__name__)

# Minimum overlap ratio to consider a person-object association
_MIN_OVERLAP_RATIO = 0.05
# Stationary check: object centroid moves less than this many pixels
_STATIONARY_THRESHOLD_PX = 5.0
# Frames of co-location before creating an association
_CO_LOCATION_FRAMES = 2


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class AbandonedObjectEvent:
    """Fired when an associated object is left stationary after person departs."""

    object_track_id: int
    associated_person_track_id: int
    separation_time: datetime
    dwell_time: float         # seconds since separation
    camera_id: str
    object_centroid: Tuple[float, float]
    timestamp: datetime


# ---------------------------------------------------------------------------
# Internal State
# ---------------------------------------------------------------------------


@dataclass
class _ObjectState:
    """Per-object tracking state."""

    object_track_id: int
    centroid: Tuple[float, float]
    last_centroid: Tuple[float, float]
    associated_person_id: Optional[int] = None
    co_location_count: int = 0
    separation_time: Optional[datetime] = None
    stationary_since: Optional[datetime] = None
    event_fired: bool = False
    camera_id: str = ""


# ---------------------------------------------------------------------------
# Detection dataclass (simplified for this module)
# ---------------------------------------------------------------------------


@dataclass
class SimpleDetection:
    """Minimal detection info needed by AbandonedObjectMonitor."""

    track_id: int
    object_class: str
    bbox: Tuple[float, float, float, float]
    centroid: Tuple[float, float]
    camera_id: str


# ---------------------------------------------------------------------------
# Abandoned Object Monitor
# ---------------------------------------------------------------------------


class AbandonedObjectMonitor:
    """Monitors unattended objects by tracking person-object co-location.

    Algorithm:
    1. On each frame, compute which person-object bbox pairs overlap.
    2. After _CO_LOCATION_FRAMES of overlap, create an association.
    3. Once the associated person moves > threshold from the object:
       - Record separation time and begin stationary countdown.
    4. If the object remains stationary for ABANDONED_OBJECT_THRESHOLD_SECS
       after separation, fire an AbandonedObjectEvent.
    5. Fire only once per object session.
    """

    # Non-person object classes to monitor
    _OBJECT_CLASSES = {"backpack", "suitcase", "handbag", "laptop", "cell phone",
                       "bottle", "bag", "briefcase"}

    def __init__(self) -> None:
        """Initialise internal state dictionaries."""
        self._objects: Dict[int, _ObjectState] = {}  # object_track_id -> state

    def update(
        self,
        detections: List[SimpleDetection],
        timestamp: datetime,
    ) -> List[AbandonedObjectEvent]:
        """Process one frame of detections and return any abandoned object events.

        Args:
            detections: All detections in the current frame.
            timestamp:  Current UTC timestamp.

        Returns:
            List of AbandonedObjectEvent (typically empty or one item).
        """
        persons = [d for d in detections if d.object_class == "person"]
        objects = [d for d in detections if d.object_class in self._OBJECT_CLASSES]

        # Index persons by track_id for fast centroid lookup
        person_centroids: Dict[int, Tuple[float, float]] = {
            p.track_id: p.centroid for p in persons
        }
        current_object_ids = {o.track_id for o in objects}

        # Remove stale object states (object gone from frame)
        stale = [oid for oid in self._objects if oid not in current_object_ids]
        for oid in stale:
            del self._objects[oid]

        events: List[AbandonedObjectEvent] = []

        for obj in objects:
            state = self._objects.get(obj.track_id)
            if state is None:
                state = _ObjectState(
                    object_track_id=obj.track_id,
                    centroid=obj.centroid,
                    last_centroid=obj.centroid,
                    camera_id=obj.camera_id,
                )
                self._objects[obj.track_id] = state
            else:
                state.last_centroid = state.centroid
                state.centroid = obj.centroid

            if state.event_fired:
                continue

            if state.associated_person_id is None:
                # Look for co-located person
                for person in persons:
                    if self._bbox_overlap(obj.bbox, _get_bbox(person)):
                        state.co_location_count += 1
                        if state.co_location_count >= _CO_LOCATION_FRAMES:
                            state.associated_person_id = person.track_id
                            logger.debug(
                                "Object %d associated with person %d.",
                                obj.track_id,
                                person.track_id,
                            )
                        break
            else:
                # Check if associated person has departed
                person_centroid = person_centroids.get(state.associated_person_id)
                if person_centroid is None:
                    # Person not in this frame; start separation timer
                    if state.separation_time is None:
                        state.separation_time = timestamp
                        logger.debug(
                            "Object %d: person %d departed; separation timer started.",
                            obj.track_id,
                            state.associated_person_id,
                        )
                else:
                    # Check distance from object
                    dist = _distance(person_centroid, state.centroid)
                    if dist > 150:  # pixels
                        if state.separation_time is None:
                            state.separation_time = timestamp

                # Check stationary condition
                if state.separation_time is not None:
                    obj_moved = _distance(state.centroid, state.last_centroid)
                    if obj_moved < _STATIONARY_THRESHOLD_PX:
                        if state.stationary_since is None:
                            state.stationary_since = timestamp
                    else:
                        # Object moved — reset stationary timer
                        state.stationary_since = None

                    if state.stationary_since is not None:
                        dwell = (timestamp - state.stationary_since).total_seconds()
                        if dwell >= settings.ABANDONED_OBJECT_THRESHOLD_SECS:
                            state.event_fired = True
                            events.append(
                                AbandonedObjectEvent(
                                    object_track_id=obj.track_id,
                                    associated_person_track_id=state.associated_person_id,
                                    separation_time=state.separation_time,
                                    dwell_time=dwell,
                                    camera_id=state.camera_id,
                                    object_centroid=state.centroid,
                                    timestamp=timestamp,
                                )
                            )
                            logger.warning(
                                "Abandoned object detected: track=%d dwell=%.1fs",
                                obj.track_id,
                                dwell,
                            )

        return events

    @staticmethod
    def _bbox_overlap(
        bbox_a: Tuple[float, float, float, float],
        bbox_b: Tuple[float, float, float, float],
    ) -> bool:
        """Return True if two bounding boxes overlap.

        Args:
            bbox_a: (x1, y1, x2, y2) first box.
            bbox_b: (x1, y1, x2, y2) second box.
        """
        ax1, ay1, ax2, ay2 = bbox_a
        bx1, by1, bx2, by2 = bbox_b
        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)
        if ix2 <= ix1 or iy2 <= iy1:
            return False
        intersection = (ix2 - ix1) * (iy2 - iy1)
        area_a = (ax2 - ax1) * (ay2 - ay1)
        if area_a == 0:
            return False
        return (intersection / area_a) >= _MIN_OVERLAP_RATIO


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Euclidean distance between two 2D points."""
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _get_bbox(det: SimpleDetection) -> Tuple[float, float, float, float]:
    """Extract bbox from a SimpleDetection."""
    return det.bbox


# Singleton
abandoned_object_monitor = AbandonedObjectMonitor()
