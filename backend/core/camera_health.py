"""
SmartCCTV SIH26187 — Camera Health Monitor.

Assesses tamper conditions (lens cover, defocus, scene replacement) by
analysing incoming frames and comparing against stored background anchors.
Raises camera_tamper events when anomalies persist.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

import cv2
import numpy as np

from backend.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class HealthState(str, Enum):
    """Enumerated camera health states."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


@dataclass
class HealthSnapshot:
    """A single health assessment result."""

    camera_id: str
    state: HealthState
    fps_actual: float
    fps_expected: float
    blank_frame_score: float
    sharpness_score: float
    scene_change_score: float
    notes: str
    timestamp: datetime


# ---------------------------------------------------------------------------
# Camera Health Monitor
# ---------------------------------------------------------------------------


class CameraHealthMonitor:
    """Analyses per-camera frames for tamper, blur, and scene change.

    State held in-process:
    - Background anchor frames (one per camera, updated every 5 minutes)
    - Previous SSIM scores for trend analysis
    - Tamper persistence counters (N consecutive bad frames -> event)
    """

    _ANCHOR_UPDATE_INTERVAL_SECS = 300   # 5 minutes
    _TAMPER_PERSIST_THRESHOLD = 5        # consecutive bad health snapshots

    def __init__(self) -> None:
        """Initialise internal state dicts."""
        self._anchors: Dict[str, np.ndarray] = {}
        self._anchor_timestamps: Dict[str, float] = {}
        self._bad_streak: Dict[str, int] = {}
        self._tamper_reported: Dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def update(
        self,
        camera_id: str,
        frame: np.ndarray,
        fps_actual: float,
        fps_expected: float,
        db: "AsyncSession",  # type: ignore[name-defined]
    ) -> HealthSnapshot:
        """Run all health checks on one frame and persist the result.

        Args:
            camera_id:    Identifier of the camera.
            frame:        Current BGR frame.
            fps_actual:   Measured FPS over the last window.
            fps_expected: Configured expected FPS.
            db:           Async DB session.

        Returns:
            HealthSnapshot with all scores and assessed state.
        """
        blank_score = self._check_blank_frame(frame)
        sharpness_score = self._check_sharpness(frame)
        scene_change_score = self._check_scene_change(camera_id, frame)

        state = self.assess_state(blank_score, sharpness_score, fps_actual, fps_expected)
        notes = self._build_notes(blank_score, sharpness_score, scene_change_score, fps_actual, fps_expected)

        snapshot = HealthSnapshot(
            camera_id=camera_id,
            state=state,
            fps_actual=fps_actual,
            fps_expected=fps_expected,
            blank_frame_score=float(blank_score),
            sharpness_score=float(sharpness_score),
            scene_change_score=float(scene_change_score),
            notes=notes,
            timestamp=datetime.utcnow(),
        )

        await self._persist(snapshot, db)
        await self._update_camera_state(camera_id, state, db)
        await self._check_tamper_event(camera_id, state, snapshot, db)

        # Periodically refresh the background anchor.
        if state == HealthState.HEALTHY:
            self._maybe_update_anchor(camera_id, frame)

        return snapshot

    # ------------------------------------------------------------------
    # Blank Frame Detection
    # ------------------------------------------------------------------

    def _check_blank_frame(self, frame: np.ndarray) -> float:
        """Compute variance of the grayscale frame.

        A very low variance (< threshold) indicates a covered or solid-colour
        image, suggesting a lens cover or tampering.

        Args:
            frame: BGR image array.

        Returns:
            Grayscale variance. Lower = more likely covered.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return float(gray.var())

    # ------------------------------------------------------------------
    # Sharpness / Defocus Detection
    # ------------------------------------------------------------------

    def _check_sharpness(self, frame: np.ndarray) -> float:
        """Compute Laplacian variance as a focus measure.

        A low Laplacian variance (< threshold) indicates defocus, which can
        indicate intentional tampering or physical damage.

        Args:
            frame: BGR image array.

        Returns:
            Laplacian variance. Lower = blurrier.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        return float(laplacian.var())

    # ------------------------------------------------------------------
    # Scene Change Detection (SSIM-based)
    # ------------------------------------------------------------------

    def _check_scene_change(self, camera_id: str, frame: np.ndarray) -> float:
        """Compare frame to stored background anchor using mean absolute difference.

        Args:
            camera_id: Used to look up the anchor frame.
            frame:     Current BGR frame.

        Returns:
            Normalised MAD score [0.0, 1.0]. Higher = more scene change.
        """
        anchor = self._anchors.get(camera_id)
        if anchor is None:
            self._anchors[camera_id] = frame.copy()
            self._anchor_timestamps[camera_id] = time.monotonic()
            return 0.0

        # Resize both to a small thumbnail for speed.
        size = (160, 90)
        curr_small = cv2.resize(frame, size).astype(np.float32)
        anch_small = cv2.resize(anchor, size).astype(np.float32)
        mad = float(np.mean(np.abs(curr_small - anch_small))) / 255.0
        return mad

    # ------------------------------------------------------------------
    # Background Anchor Management
    # ------------------------------------------------------------------

    def _maybe_update_anchor(self, camera_id: str, frame: np.ndarray) -> None:
        """Update the background anchor if the update interval has elapsed.

        Args:
            camera_id: Camera identifier.
            frame:     Current healthy frame to use as new anchor.
        """
        last_update = self._anchor_timestamps.get(camera_id, 0.0)
        if time.monotonic() - last_update >= self._ANCHOR_UPDATE_INTERVAL_SECS:
            self._update_background_anchor(camera_id, frame)

    def _update_background_anchor(self, camera_id: str, frame: np.ndarray) -> None:
        """Store a new background reference frame for a camera.

        Args:
            camera_id: Camera identifier.
            frame:     Frame to store as the new anchor.
        """
        self._anchors[camera_id] = frame.copy()
        self._anchor_timestamps[camera_id] = time.monotonic()
        logger.debug("Background anchor updated for camera %s.", camera_id)

    # ------------------------------------------------------------------
    # State Assessment
    # ------------------------------------------------------------------

    def assess_state(
        self,
        blank_score: float,
        sharpness_score: float,
        fps_actual: float,
        fps_expected: float,
    ) -> HealthState:
        """Determine HealthState from individual metric scores.

        Args:
            blank_score:     Grayscale variance (low = covered).
            sharpness_score: Laplacian variance (low = blurry).
            fps_actual:      Measured FPS.
            fps_expected:    Configured expected FPS.

        Returns:
            HealthState enum value.
        """
        if blank_score < settings.BLANK_FRAME_VARIANCE_THRESHOLD:
            return HealthState.OFFLINE

        if sharpness_score < settings.SHARPNESS_LAPLACIAN_THRESHOLD:
            return HealthState.DEGRADED

        fps_ratio = fps_actual / max(fps_expected, 1.0)
        if fps_ratio < settings.FPS_DEGRADED_RATIO:
            return HealthState.DEGRADED

        return HealthState.HEALTHY

    # ------------------------------------------------------------------
    # Topology Query
    # ------------------------------------------------------------------

    def get_candidate_cameras_in_area(
        self, camera_id: str, topology_graph: "TopologyGraph"  # type: ignore[name-defined]
    ) -> List[str]:
        """Return camera IDs adjacent to the given camera via the topology graph.

        Args:
            camera_id:      Source camera.
            topology_graph: The loaded topology graph.

        Returns:
            List of adjacent camera IDs.
        """
        return topology_graph.get_adjacent_cameras(camera_id, max_travel_time_secs=300)

    # ------------------------------------------------------------------
    # Tamper Event Trigger
    # ------------------------------------------------------------------

    async def _check_tamper_event(
        self,
        camera_id: str,
        state: HealthState,
        snapshot: HealthSnapshot,
        db: "AsyncSession",  # type: ignore[name-defined]
    ) -> None:
        """Fire a camera_tamper event after N consecutive bad health checks.

        Args:
            camera_id: Camera being assessed.
            state:     Current health state.
            snapshot:  Full snapshot for evidence.
            db:        Async DB session.
        """
        if state in (HealthState.OFFLINE, HealthState.DEGRADED):
            self._bad_streak[camera_id] = self._bad_streak.get(camera_id, 0) + 1
        else:
            self._bad_streak[camera_id] = 0
            self._tamper_reported[camera_id] = False
            return

        if (
            self._bad_streak[camera_id] >= self._TAMPER_PERSIST_THRESHOLD
            and not self._tamper_reported.get(camera_id, False)
        ):
            self._tamper_reported[camera_id] = True
            await self._create_tamper_event(camera_id, snapshot, db)

    async def _create_tamper_event(
        self,
        camera_id: str,
        snapshot: HealthSnapshot,
        db: "AsyncSession",  # type: ignore[name-defined]
    ) -> None:
        """Persist a camera_tamper Event in the database.

        Args:
            camera_id: Affected camera.
            snapshot:  Health data to embed in risk factors.
            db:        Async DB session.
        """
        from backend.models.event import Alert, Event

        event = Event(
            event_type="camera_tamper",
            severity="high",
            risk_score=60.0,
            risk_factors={
                "blank_frame_score": snapshot.blank_frame_score,
                "sharpness_score": snapshot.sharpness_score,
                "scene_change_score": snapshot.scene_change_score,
                "fps_actual": snapshot.fps_actual,
                "consecutive_bad_checks": self._bad_streak.get(camera_id, 0),
            },
            camera_id=camera_id,
            status="open",
            evidence_manifest={},
            model_versions={},
            rule_version="v1.0",
            calibration_version="v1.0",
        )
        db.add(event)
        await db.flush()
        alert = Alert(event_id=event.event_id, disposition="pending")
        db.add(alert)
        await db.flush()
        logger.warning(
            "camera_tamper event created for camera %s (health=%s).",
            camera_id,
            snapshot.state,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _persist(
        self, snapshot: HealthSnapshot, db: "AsyncSession"  # type: ignore[name-defined]
    ) -> None:
        """Write a CameraHealth row to the database.

        Args:
            snapshot: The health assessment to persist.
            db:       Async DB session.
        """
        from backend.models.camera import CameraHealth

        record = CameraHealth(
            camera_id=snapshot.camera_id,
            timestamp=snapshot.timestamp,
            state=snapshot.state.value,
            fps_actual=snapshot.fps_actual,
            fps_expected=snapshot.fps_expected,
            blank_frame_score=snapshot.blank_frame_score,
            sharpness_score=snapshot.sharpness_score,
            scene_change_score=snapshot.scene_change_score,
            notes=snapshot.notes,
        )
        db.add(record)
        await db.flush()

    async def _update_camera_state(
        self,
        camera_id: str,
        state: HealthState,
        db: "AsyncSession",  # type: ignore[name-defined]
    ) -> None:
        """Update the Camera.health_state column and last_heartbeat.

        Args:
            camera_id: Camera to update.
            state:     New health state.
            db:        Async DB session.
        """
        from sqlalchemy import update
        from backend.models.camera import Camera

        await db.execute(
            update(Camera)
            .where(Camera.camera_id == camera_id)
            .values(health_state=state.value, last_heartbeat=datetime.utcnow())
        )
        await db.flush()

    # ------------------------------------------------------------------
    # Notes Builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_notes(
        blank: float,
        sharp: float,
        scene: float,
        fps_actual: float,
        fps_expected: float,
    ) -> str:
        """Build a human-readable notes string from metric values."""
        issues = []
        if blank < settings.BLANK_FRAME_VARIANCE_THRESHOLD:
            issues.append(f"Possible lens cover (blank={blank:.1f})")
        if sharp < settings.SHARPNESS_LAPLACIAN_THRESHOLD:
            issues.append(f"Defocus detected (sharpness={sharp:.1f})")
        if fps_actual < fps_expected * settings.FPS_DEGRADED_RATIO:
            issues.append(f"Low FPS ({fps_actual:.1f}/{fps_expected})")
        if scene > 0.4:
            issues.append(f"Scene change anomaly (score={scene:.2f})")
        return "; ".join(issues) if issues else "Normal"


# Singleton instance
camera_health_monitor = CameraHealthMonitor()
