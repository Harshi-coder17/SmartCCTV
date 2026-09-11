"""
SmartCCTV SIH26187 — Loitering Detection State Machine.

Tracks per-(track_id, zone_id) dwell time and fires a LoiteringEvent
exactly once per session when the configured threshold is exceeded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from backend.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class LoiteringEvent:
    """Event fired when a person loiters in a zone beyond the threshold."""

    track_id: int
    zone_id: str
    zone_name: str
    dwell_seconds: float
    trajectory_snapshot: List[Tuple[float, float]]   # list of (cx, cy) points
    camera_id: str
    timestamp: datetime


# ---------------------------------------------------------------------------
# Internal State
# ---------------------------------------------------------------------------


@dataclass
class _DwellState:
    """Per-(track, zone) dwell tracking state."""

    entry_time: datetime
    last_seen_time: datetime
    dwell_seconds: float = 0.0
    event_fired: bool = False
    trajectory: List[Tuple[float, float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loitering Monitor
# ---------------------------------------------------------------------------


class LoiteringMonitor:
    """Stateful loitering detector with per-zone threshold configuration.

    Call update() once per frame for each (track_id, zone_id) pair where
    the track is inside the zone.  Call on_track_left_zone() when a track
    exits a zone to reset its dwell state.
    """

    def __init__(self) -> None:
        """Initialise internal dwell state dictionary."""
        # Key: (track_id, zone_id)
        self._dwell: Dict[Tuple[int, str], _DwellState] = {}
        # Zone thresholds cache: {zone_id -> seconds}
        self._zone_thresholds: Dict[str, int] = {}

    def configure_zone(self, zone_id: str, threshold_secs: int) -> None:
        """Set the loitering threshold for a specific zone.

        Args:
            zone_id:        Zone identifier.
            threshold_secs: Seconds before loitering is declared.
        """
        self._zone_thresholds[zone_id] = threshold_secs

    def update(
        self,
        track_id: int,
        zone_id: str,
        zone_name: str,
        camera_id: str,
        centroid: Tuple[float, float],
        timestamp: datetime,
    ) -> Optional[LoiteringEvent]:
        """Update dwell state for a track inside a zone.

        Args:
            track_id:   Local ByteTrack track ID.
            zone_id:    Zone the track is currently inside.
            zone_name:  Human-readable zone name.
            camera_id:  Camera identifier.
            centroid:   Current (cx, cy) centroid.
            timestamp:  Current UTC timestamp.

        Returns:
            LoiteringEvent if threshold just exceeded, else None.
        """
        key = (track_id, zone_id)
        threshold = self._zone_thresholds.get(zone_id, settings.LOITERING_THRESHOLD_SECS)

        if key not in self._dwell:
            self._dwell[key] = _DwellState(
                entry_time=timestamp,
                last_seen_time=timestamp,
                trajectory=[centroid],
            )
            return None

        state = self._dwell[key]

        # Guard against non-monotonic timestamps
        delta = (timestamp - state.last_seen_time).total_seconds()
        if delta < 0:
            delta = 0.0

        state.dwell_seconds += delta
        state.last_seen_time = timestamp
        state.trajectory.append(centroid)

        # Trim trajectory to last 100 points for storage efficiency
        if len(state.trajectory) > 100:
            state.trajectory = state.trajectory[-100:]

        if state.event_fired:
            return None

        if state.dwell_seconds >= threshold:
            state.event_fired = True
            logger.info(
                "Loitering detected: track=%d zone=%s dwell=%.1fs",
                track_id,
                zone_id,
                state.dwell_seconds,
            )
            return LoiteringEvent(
                track_id=track_id,
                zone_id=zone_id,
                zone_name=zone_name,
                dwell_seconds=state.dwell_seconds,
                trajectory_snapshot=list(state.trajectory),
                camera_id=camera_id,
                timestamp=timestamp,
            )

        return None

    def on_track_left_zone(self, track_id: int, zone_id: str) -> None:
        """Reset dwell state when a track exits a zone.

        Args:
            track_id: Local track ID.
            zone_id:  Zone the track has exited.
        """
        key = (track_id, zone_id)
        if key in self._dwell:
            del self._dwell[key]
            logger.debug("Track %d left zone %s; dwell state cleared.", track_id, zone_id)

    def on_track_lost(self, track_id: int) -> None:
        """Remove all dwell states for a track (track became inactive).

        Args:
            track_id: The track that was lost.
        """
        keys_to_remove = [k for k in self._dwell if k[0] == track_id]
        for k in keys_to_remove:
            del self._dwell[k]

    def get_dwell_seconds(self, track_id: int, zone_id: str) -> float:
        """Return the current dwell time for a (track, zone) pair.

        Args:
            track_id: Local track ID.
            zone_id:  Zone identifier.

        Returns:
            Dwell time in seconds, or 0.0 if not tracked.
        """
        state = self._dwell.get((track_id, zone_id))
        return state.dwell_seconds if state else 0.0


# Singleton
loitering_monitor = LoiteringMonitor()
