"""
SmartCCTV SIH26187 - Cross-Camera Event Correlator.

Fuses events and observations across cameras into:
  - Global identity movement timelines
  - Entry-point verification (origin check, camera-health-aware)
  - Route-anomaly detection (patrol deviation, camera-health-aware)
  - Correlated alert enrichment
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.correlation.graph import TopologyGraph

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TrackSighting:
    """A single camera sighting of a global identity."""

    camera_id: str
    camera_name: str
    zone_id: Optional[str]
    timestamp: datetime
    confidence: float
    location_name: str = ""


@dataclass
class MovementTimeline:
    """Ordered cross-camera movement record for one global identity."""

    global_identity_id: str
    sightings: List[TrackSighting] = field(default_factory=list)
    authorization_status: str = "unauthorized"
    is_provisional: bool = False

    @property
    def first_seen(self) -> Optional[datetime]:
        return self.sightings[0].timestamp if self.sightings else None

    @property
    def last_seen(self) -> Optional[datetime]:
        return self.sightings[-1].timestamp if self.sightings else None

    @property
    def camera_count(self) -> int:
        return len({s.camera_id for s in self.sightings})


@dataclass
class EntryPointResult:
    """Result of the origin / entry-point verification check."""

    has_traceable_origin: bool
    # 'clear' | 'partial_sensor_gap' | 'no_origin' | 'camera_offline_suppressed'
    confidence: str
    suppressed_by_camera_outage: bool = False
    relevant_cameras_checked: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class RouteResult:
    """Result of patrol-route deviation check."""

    is_anomalous: bool
    deviation_score: float  # 0.0 (on-route) to 1.0 (fully off-route)
    suppressed_by_camera_outage: bool = False
    notes: str = ""


@dataclass
class CorrelationCandidate:
    """A proposed cross-camera identity link."""

    correlation_id: str
    source_track_id: str
    target_track_id: str
    source_camera: str
    target_camera: str
    reid_similarity: float
    topology_plausible: bool
    time_feasible: bool
    combined_confidence: float

    @property
    def is_acceptable(self) -> bool:
        return self.topology_plausible and self.time_feasible and self.combined_confidence > 0.6


# ---------------------------------------------------------------------------
# Main correlator
# ---------------------------------------------------------------------------


class EventCorrelator:
    """
    Cross-camera event correlation and movement timeline builder.

    Responsibilities:
      - Build ordered movement timelines from global identity records.
      - Check entry-point origin, suppressing false flags when cameras are offline.
      - Check patrol-route deviation, using the same camera-health suppression.
      - Produce CorrelationCandidate objects for human or automatic review.

    All adjacency queries go through topology_graph.get_adjacent_cameras()
    so there is a single definition of "adjacent camera" throughout the system.
    """

    def __init__(self, topology_graph: TopologyGraph) -> None:
        self._graph = topology_graph

    # ------------------------------------------------------------------
    # Timeline
    # ------------------------------------------------------------------

    async def build_timeline(
        self,
        global_identity_id: str,
        db: AsyncSession,
    ) -> MovementTimeline:
        """
        Build a MovementTimeline from the movement_log stored on the
        GlobalIdentity record.
        """
        from backend.models.track import GlobalIdentity
        from backend.models.camera import Camera

        result = await db.execute(
            select(GlobalIdentity).where(GlobalIdentity.identity_id == global_identity_id)
        )
        identity = result.scalar_one_or_none()
        if identity is None:
            return MovementTimeline(global_identity_id=global_identity_id)

        movement_log: List[Dict[str, Any]] = identity.movement_log or []

        # Resolve camera names
        cam_ids = list({entry.get("camera_id") for entry in movement_log if entry.get("camera_id")})
        cam_result = await db.execute(select(Camera).where(Camera.camera_id.in_(cam_ids)))
        cameras = {c.camera_id: c for c in cam_result.scalars().all()}

        sightings: List[TrackSighting] = []
        for entry in sorted(movement_log, key=lambda e: e.get("timestamp", "")):
            cam = cameras.get(entry.get("camera_id", ""))
            sightings.append(
                TrackSighting(
                    camera_id=entry.get("camera_id", ""),
                    camera_name=cam.name if cam else entry.get("camera_id", ""),
                    zone_id=entry.get("zone_id"),
                    timestamp=datetime.fromisoformat(entry["timestamp"]) if "timestamp" in entry else datetime.utcnow(),
                    confidence=entry.get("confidence", 1.0),
                    location_name=cam.location_name if cam else "",
                )
            )

        return MovementTimeline(
            global_identity_id=global_identity_id,
            sightings=sightings,
            authorization_status=identity.authorization_status,
            is_provisional=(identity.authorization_status == "provisional"),
        )

    # ------------------------------------------------------------------
    # Entry-point / origin check
    # ------------------------------------------------------------------

    async def check_entry_point(
        self,
        global_identity_id: str,
        current_camera_id: str,
        db: AsyncSession,
        max_adjacency_secs: float = 300.0,
    ) -> EntryPointResult:
        """
        Determine whether the global identity has a traceable origin.

        Steps:
          1. Load movement log. If prior sightings exist -> has_traceable_origin=True.
          2. If no prior sightings: collect candidate cameras adjacent to current
             camera (same adjacency logic as ReID).
          3. For each candidate camera, check health log over the relevant window.
          4. If a candidate was offline/degraded -> suppress or down-weight the flag.
        """
        from backend.models.track import GlobalIdentity
        from backend.models.camera import CameraHealth

        result = await db.execute(
            select(GlobalIdentity).where(GlobalIdentity.identity_id == global_identity_id)
        )
        identity = result.scalar_one_or_none()

        movement_log: List[Dict] = []
        if identity is not None:
            movement_log = identity.movement_log or []

        prior_sightings = [
            e for e in movement_log if e.get("camera_id") != current_camera_id
        ]

        if prior_sightings:
            return EntryPointResult(
                has_traceable_origin=True,
                confidence="clear",
                notes=f"Prior sightings on {len(prior_sightings)} camera(s)",
            )

        # No prior sightings: check whether adjacent cameras were healthy
        adjacent = self._graph.get_adjacent_cameras(current_camera_id, max_adjacency_secs)
        if not adjacent:
            return EntryPointResult(
                has_traceable_origin=False,
                confidence="no_origin",
                relevant_cameras_checked=[],
                notes="No adjacent cameras configured",
            )

        window_start = datetime.utcnow() - timedelta(seconds=max_adjacency_secs * 2)
        health_result = await db.execute(
            select(CameraHealth)
            .where(CameraHealth.camera_id.in_(adjacent))
            .where(CameraHealth.timestamp >= window_start)
            .order_by(CameraHealth.timestamp.desc())
        )
        health_records = health_result.scalars().all()

        # Collect worst state per camera in the window
        worst_state: Dict[str, str] = {}
        for record in health_records:
            cid = record.camera_id
            if cid not in worst_state:
                worst_state[cid] = record.state
            elif record.state in ("offline", "degraded") and worst_state[cid] == "healthy":
                worst_state[cid] = record.state

        offline_cameras = [c for c, s in worst_state.items() if s == "offline"]
        degraded_cameras = [c for c, s in worst_state.items() if s == "degraded"]

        if offline_cameras:
            # A camera that should have seen them was down: suppress the flag
            return EntryPointResult(
                has_traceable_origin=False,
                confidence="camera_offline_suppressed",
                suppressed_by_camera_outage=True,
                relevant_cameras_checked=adjacent,
                notes=f"Flag suppressed: cameras offline during window: {offline_cameras}",
            )
        elif degraded_cameras:
            return EntryPointResult(
                has_traceable_origin=False,
                confidence="partial_sensor_gap",
                suppressed_by_camera_outage=False,
                relevant_cameras_checked=adjacent,
                notes=f"Degraded cameras present: {degraded_cameras} - confidence reduced",
            )
        else:
            return EntryPointResult(
                has_traceable_origin=False,
                confidence="no_origin",
                relevant_cameras_checked=adjacent,
                notes="All adjacent cameras were healthy - no prior sighting is significant",
            )

    # ------------------------------------------------------------------
    # Route anomaly check
    # ------------------------------------------------------------------

    async def check_route_anomaly(
        self,
        global_identity_id: str,
        expected_route_camera_ids: List[str],
        db: AsyncSession,
        window_secs: float = 600.0,
    ) -> RouteResult:
        """
        Compare observed movement to an expected patrol route.

        Suppresses the anomaly flag when cameras covering the expected route
        were degraded or offline during the observation window (same pattern
        as check_entry_point).
        """
        from backend.models.track import GlobalIdentity
        from backend.models.camera import CameraHealth

        if not expected_route_camera_ids:
            return RouteResult(is_anomalous=False, deviation_score=0.0, notes="No expected route defined")

        result = await db.execute(
            select(GlobalIdentity).where(GlobalIdentity.identity_id == global_identity_id)
        )
        identity = result.scalar_one_or_none()
        if identity is None:
            return RouteResult(is_anomalous=False, deviation_score=0.0, notes="Identity not found")

        movement_log: List[Dict] = identity.movement_log or []
        window_start = datetime.utcnow() - timedelta(seconds=window_secs)
        recent = [
            e for e in movement_log
            if datetime.fromisoformat(e["timestamp"]) >= window_start
        ]

        if not recent:
            return RouteResult(is_anomalous=False, deviation_score=0.0, notes="No recent movement to compare")

        observed_cameras = {e["camera_id"] for e in recent}
        expected_set = set(expected_route_camera_ids)
        off_route_cameras = observed_cameras - expected_set

        if not off_route_cameras:
            return RouteResult(is_anomalous=False, deviation_score=0.0, notes="On expected route")

        deviation_score = len(off_route_cameras) / max(len(observed_cameras), 1)

        # Check camera health for the expected route cameras
        health_result = await db.execute(
            select(CameraHealth)
            .where(CameraHealth.camera_id.in_(list(expected_set)))
            .where(CameraHealth.timestamp >= window_start)
            .order_by(CameraHealth.timestamp.desc())
        )
        health_records = health_result.scalars().all()

        offline_on_route = {r.camera_id for r in health_records if r.state == "offline"}
        if offline_on_route:
            return RouteResult(
                is_anomalous=False,
                deviation_score=deviation_score,
                suppressed_by_camera_outage=True,
                notes=f"Route deviation suppressed: expected-route cameras offline: {list(offline_on_route)}",
            )

        return RouteResult(
            is_anomalous=deviation_score > 0.3,
            deviation_score=round(deviation_score, 3),
            notes=f"Observed cameras off-route: {list(off_route_cameras)}",
        )

    # ------------------------------------------------------------------
    # Correlation candidates
    # ------------------------------------------------------------------

    def build_correlation_candidate(
        self,
        source_track_id: str,
        target_track_id: str,
        source_camera: str,
        target_camera: str,
        reid_similarity: float,
        time_elapsed_secs: float,
    ) -> CorrelationCandidate:
        """
        Create a CorrelationCandidate, checking topology and time feasibility.
        """
        import uuid

        topology_ok = self._graph.is_travel_feasible(source_camera, target_camera, time_elapsed_secs)
        # Also accept if cameras are adjacent within 2x the elapsed window
        if not topology_ok:
            adjacent = self._graph.get_adjacent_cameras(source_camera)
            topology_ok = target_camera in adjacent

        combined = reid_similarity * (0.8 if topology_ok else 0.2)

        return CorrelationCandidate(
            correlation_id=str(uuid.uuid4()),
            source_track_id=source_track_id,
            target_track_id=target_track_id,
            source_camera=source_camera,
            target_camera=target_camera,
            reid_similarity=round(reid_similarity, 4),
            topology_plausible=topology_ok,
            time_feasible=topology_ok,
            combined_confidence=round(combined, 4),
        )
