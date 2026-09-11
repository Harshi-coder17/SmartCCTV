"""
SmartCCTV SIH26187 — Crowd Analysis Engine.

Analyses density, count, group spacing, and movement direction of
crowds within zones.  Fires CrowdEvents when thresholds are exceeded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

from backend.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class CrowdEvent:
    """Event fired when crowd density or count exceeds zone thresholds."""

    camera_id: str
    zone_id: Optional[str]
    count: int
    density: float
    movement_vector: Tuple[float, float]
    spacing_variance: float
    heatmap_data: List[List[float]]   # 2D density grid (10x10)
    timestamp: datetime


@dataclass
class SimpleDetection:
    """Minimal detection info for crowd analysis."""

    track_id: int
    object_class: str
    centroid: Tuple[float, float]
    camera_id: str


# ---------------------------------------------------------------------------
# Crowd Engine
# ---------------------------------------------------------------------------


class CrowdEngine:
    """Analyses crowd behaviour within camera views and zones.

    Maintains track history for direction computation.
    """

    def __init__(self) -> None:
        """Initialise track history buffer."""
        # track_id -> deque of (cx, cy) points
        self._track_history: Dict[int, List[Tuple[float, float]]] = {}

    def update_track_history(
        self,
        track_id: int,
        centroid: Tuple[float, float],
        max_len: int = 30,
    ) -> None:
        """Append a centroid to a track's history.

        Args:
            track_id: Track ID.
            centroid: (cx, cy).
            max_len:  Maximum history length.
        """
        if track_id not in self._track_history:
            self._track_history[track_id] = []
        self._track_history[track_id].append(centroid)
        if len(self._track_history[track_id]) > max_len:
            self._track_history[track_id] = self._track_history[track_id][-max_len:]

    def analyze(
        self,
        detections: List[SimpleDetection],
        camera_id: str,
        zone_id: Optional[str] = None,
        zone_polygon: Optional[List[List[float]]] = None,
        zone_area_pixels: float = 100_000.0,
        crowd_count_threshold: int = 0,
        crowd_density_threshold: float = 0.0,
    ) -> Optional[CrowdEvent]:
        """Analyse crowd metrics for the given detections.

        Args:
            detections:               All person detections in the frame.
            camera_id:                Camera identifier.
            zone_id:                  Zone to restrict analysis to (optional).
            zone_polygon:             Polygon for zone filtering.
            zone_area_pixels:         Area of the zone in pixels² for density.
            crowd_count_threshold:    Override default count threshold.
            crowd_density_threshold:  Override default density threshold.

        Returns:
            CrowdEvent if thresholds exceeded, else None.
        """
        count_thresh = crowd_count_threshold or settings.CROWD_COUNT_THRESHOLD
        density_thresh = crowd_density_threshold or settings.CROWD_DENSITY_THRESHOLD

        # Filter to persons only
        persons = [d for d in detections if d.object_class == "person"]

        # Optionally filter to zone
        if zone_polygon:
            from backend.core.events.zone_engine import ZoneEngine
            persons = [
                p for p in persons
                if ZoneEngine.point_in_polygon(p.centroid, zone_polygon)
            ]

        count = self.count_in_zone(persons, zone_polygon)
        density = self.compute_density(count, zone_area_pixels)

        # Update track histories
        for p in persons:
            self.update_track_history(p.track_id, p.centroid)

        if count < count_thresh and density < density_thresh:
            return None

        spacing_var = self.compute_group_spacing_variance(persons)
        movement_vec = self.compute_movement_vector(
            {p.track_id: self._track_history.get(p.track_id, []) for p in persons}
        )
        heatmap = self._build_heatmap(persons)

        logger.info(
            "Crowd anomaly: camera=%s zone=%s count=%d density=%.4f",
            camera_id, zone_id, count, density,
        )

        return CrowdEvent(
            camera_id=camera_id,
            zone_id=zone_id,
            count=count,
            density=density,
            movement_vector=movement_vec,
            spacing_variance=spacing_var,
            heatmap_data=heatmap,
            timestamp=datetime.utcnow(),
        )

    @staticmethod
    def count_in_zone(
        detections: List[SimpleDetection],
        zone_polygon: Optional[List[List[float]]],
    ) -> int:
        """Count persons inside a zone polygon.

        Args:
            detections:   Person detections to count.
            zone_polygon: Zone polygon or None (count all).

        Returns:
            Integer person count.
        """
        if zone_polygon is None:
            return len(detections)

        from backend.core.events.zone_engine import ZoneEngine
        return sum(
            1 for d in detections
            if ZoneEngine.point_in_polygon(d.centroid, zone_polygon)
        )

    @staticmethod
    def compute_density(count: int, zone_area_pixels: float) -> float:
        """Compute crowd density as persons per 10,000 pixels².

        Args:
            count:            Number of persons.
            zone_area_pixels: Zone area in pixels².

        Returns:
            Density float.
        """
        if zone_area_pixels <= 0:
            return 0.0
        return count / (zone_area_pixels / 10_000.0)

    @staticmethod
    def compute_group_spacing_variance(detections: List[SimpleDetection]) -> float:
        """Compute variance of pairwise centroid distances.

        High variance = spread out group; low variance = tight cluster.

        Args:
            detections: Person detections.

        Returns:
            Variance of pairwise L2 distances, or 0.0 if fewer than 2 persons.
        """
        if len(detections) < 2:
            return 0.0

        centroids = np.array([d.centroid for d in detections], dtype=np.float32)
        n = len(centroids)
        dists = []
        for i in range(n):
            for j in range(i + 1, n):
                d = float(np.linalg.norm(centroids[i] - centroids[j]))
                dists.append(d)
        return float(np.var(dists)) if dists else 0.0

    @staticmethod
    def compute_movement_vector(
        track_histories: Dict[int, List[Tuple[float, float]]],
    ) -> Tuple[float, float]:
        """Compute mean movement direction across all tracked persons.

        Args:
            track_histories: Map of track_id -> list of (cx, cy) points.

        Returns:
            Mean (dx, dy) displacement vector.
        """
        vectors = []
        for hist in track_histories.values():
            if len(hist) >= 2:
                dx = hist[-1][0] - hist[-min(len(hist), 10)][0]
                dy = hist[-1][1] - hist[-min(len(hist), 10)][1]
                vectors.append((dx, dy))

        if not vectors:
            return (0.0, 0.0)

        mean_dx = float(np.mean([v[0] for v in vectors]))
        mean_dy = float(np.mean([v[1] for v in vectors]))
        return (mean_dx, mean_dy)

    @staticmethod
    def _build_heatmap(
        detections: List[SimpleDetection],
        grid_rows: int = 10,
        grid_cols: int = 10,
        frame_width: int = 1920,
        frame_height: int = 1080,
    ) -> List[List[float]]:
        """Build a 10×10 density heatmap from person centroids.

        Args:
            detections:   Person detections with centroids.
            grid_rows:    Number of heatmap rows.
            grid_cols:    Number of heatmap columns.
            frame_width:  Assumed frame width for normalisation.
            frame_height: Assumed frame height for normalisation.

        Returns:
            2D list of floats (count per cell).
        """
        heatmap = [[0.0] * grid_cols for _ in range(grid_rows)]
        for d in detections:
            cx, cy = d.centroid
            col = min(int(cx / frame_width * grid_cols), grid_cols - 1)
            row = min(int(cy / frame_height * grid_rows), grid_rows - 1)
            heatmap[row][col] += 1.0
        return heatmap


# Singleton
crowd_engine = CrowdEngine()
