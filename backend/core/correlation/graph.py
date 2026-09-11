"""
SmartCCTV SIH26187 - Camera Topology Graph.

Maintains the adjacency graph of cameras: which cameras are physically
adjacent, the estimated travel time between them, and the feasibility
check used by ReID, entry-point verification, and route-anomaly checks.

All three callers (reid_engine, correlation/matcher, and the risk engine's
no_traceable_origin check) call get_adjacent_cameras() from this single
source so there is never more than one definition of "nearby camera".
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import structlog

log = structlog.get_logger(__name__)

# Assumed walking speed for travel-time estimation (m/s)
_WALKING_SPEED_MS = 1.4  # ~5 km/h
# Default max travel time when no explicit edge defined (seconds)
_DEFAULT_MAX_TRAVEL_SECS = 300  # 5 minutes


@dataclass
class CameraNode:
    """Represents a single camera in the topology graph."""

    camera_id: str
    gps_lat: float
    gps_lon: float
    location_name: str = ""


@dataclass
class TopologyEdge:
    """Directed edge between two cameras with travel-time bounds."""

    from_camera: str
    to_camera: str
    # metres (computed from GPS or provided explicitly)
    distance_m: float = 0.0
    # estimated max seconds for a person to travel between them
    max_travel_secs: float = _DEFAULT_MAX_TRAVEL_SECS
    # explicitly configured? (False = derived from GPS distance)
    explicit: bool = False


class TopologyGraph:
    """
    Camera adjacency graph used by ReID, entry-point checks, and
    route-anomaly checks.

    Loading priority:
        1. Explicit adjacency JSON (data/topology.json) - highest fidelity.
        2. GPS-distance auto-derivation from cameras.json - fallback.

    The graph is undirected for adjacency queries but edges are stored
    directionally so asymmetric travel times can be modelled if needed.
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, CameraNode] = {}
        # adjacency: camera_id -> list of edges FROM that camera
        self._edges: Dict[str, List[TopologyEdge]] = {}

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_from_cameras_json(self, cameras_json_path: Path) -> None:
        """
        Build the topology graph from a cameras.json file.

        If a sibling topology.json file exists, explicit adjacency edges
        from it override the GPS-derived ones.
        """
        if not cameras_json_path.exists():
            log.warning("cameras_json_not_found", path=str(cameras_json_path))
            return

        with open(cameras_json_path) as fh:
            cameras = json.load(fh)

        for cam in cameras:
            node = CameraNode(
                camera_id=cam["camera_id"],
                gps_lat=cam.get("gps_lat", 0.0),
                gps_lon=cam.get("gps_lon", 0.0),
                location_name=cam.get("location_name", ""),
            )
            self._nodes[node.camera_id] = node
            self._edges.setdefault(node.camera_id, [])

        # Build fully-connected graph with GPS-derived travel times
        camera_ids = list(self._nodes.keys())
        for i, cid_a in enumerate(camera_ids):
            for cid_b in camera_ids[i + 1 :]:
                dist = self._haversine(
                    self._nodes[cid_a].gps_lat,
                    self._nodes[cid_a].gps_lon,
                    self._nodes[cid_b].gps_lat,
                    self._nodes[cid_b].gps_lon,
                )
                travel = dist / _WALKING_SPEED_MS
                edge_ab = TopologyEdge(cid_a, cid_b, dist, travel)
                edge_ba = TopologyEdge(cid_b, cid_a, dist, travel)
                self._edges[cid_a].append(edge_ab)
                self._edges[cid_b].append(edge_ba)

        log.info(
            "topology_loaded_from_gps",
            cameras=len(self._nodes),
            edges=sum(len(v) for v in self._edges.values()),
        )

        # Try to overlay explicit adjacency
        topology_json = cameras_json_path.parent / "topology.json"
        if topology_json.exists():
            self._load_explicit_topology(topology_json)

    def _load_explicit_topology(self, topology_json_path: Path) -> None:
        """Override GPS-derived edges with explicit adjacency config."""
        with open(topology_json_path) as fh:
            data = json.load(fh)

        for entry in data.get("edges", []):
            cid_a = entry["from"]
            cid_b = entry["to"]
            dist = entry.get("distance_m", 0.0)
            travel = entry.get("max_travel_secs", dist / _WALKING_SPEED_MS if dist else _DEFAULT_MAX_TRAVEL_SECS)
            bidirectional = entry.get("bidirectional", True)

            # Replace any existing edges between these cameras
            self._edges.setdefault(cid_a, [])
            self._edges[cid_a] = [e for e in self._edges[cid_a] if e.to_camera != cid_b]
            self._edges[cid_a].append(TopologyEdge(cid_a, cid_b, dist, travel, explicit=True))

            if bidirectional:
                self._edges.setdefault(cid_b, [])
                self._edges[cid_b] = [e for e in self._edges[cid_b] if e.to_camera != cid_a]
                self._edges[cid_b].append(TopologyEdge(cid_b, cid_a, dist, travel, explicit=True))

        log.info("topology_explicit_overlay_applied", path=str(topology_json_path))

    # ------------------------------------------------------------------
    # Public Query API
    # ------------------------------------------------------------------

    def get_adjacent_cameras(
        self,
        camera_id: str,
        max_travel_time_secs: float = _DEFAULT_MAX_TRAVEL_SECS,
    ) -> List[str]:
        """
        Return camera IDs reachable from camera_id within max_travel_time_secs.

        This is THE single definition of "adjacent camera" used by:
          - reid_engine.py (FAISS candidate set)
          - matcher.py (entry-point and route-anomaly checks)
          - risk_engine.py (no_traceable_origin health-camera selection)
        """
        adjacent: List[str] = []
        for edge in self._edges.get(camera_id, []):
            if edge.max_travel_secs <= max_travel_time_secs:
                adjacent.append(edge.to_camera)
        return adjacent

    def is_travel_feasible(
        self,
        from_camera_id: str,
        to_camera_id: str,
        elapsed_secs: float,
    ) -> bool:
        """
        Return True if a person could physically travel from one camera's
        field of view to another in the observed elapsed time.
        """
        for edge in self._edges.get(from_camera_id, []):
            if edge.to_camera == to_camera_id:
                return elapsed_secs <= edge.max_travel_secs
        # No edge defined: assume not feasible (conservative)
        return False

    def get_distance_m(self, camera_id_a: str, camera_id_b: str) -> Optional[float]:
        """Return estimated distance in metres between two cameras, or None."""
        for edge in self._edges.get(camera_id_a, []):
            if edge.to_camera == camera_id_b:
                return edge.distance_m
        return None

    def all_camera_ids(self) -> List[str]:
        """Return all registered camera IDs."""
        return list(self._nodes.keys())

    def get_node(self, camera_id: str) -> Optional[CameraNode]:
        return self._nodes.get(camera_id)

    def to_dict(self) -> dict:
        """Serialise the graph for API responses."""
        return {
            "nodes": [
                {
                    "camera_id": n.camera_id,
                    "location_name": n.location_name,
                    "gps_lat": n.gps_lat,
                    "gps_lon": n.gps_lon,
                }
                for n in self._nodes.values()
            ],
            "edges": [
                {
                    "from": e.from_camera,
                    "to": e.to_camera,
                    "distance_m": round(e.distance_m, 1),
                    "max_travel_secs": round(e.max_travel_secs, 1),
                    "explicit": e.explicit,
                }
                for edges in self._edges.values()
                for e in edges
            ],
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Haversine great-circle distance in metres."""
        R = 6_371_000  # Earth radius in metres
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return 2 * R * math.asin(math.sqrt(a))


# Module-level singleton — shared across the process
_graph: Optional[TopologyGraph] = None


def get_topology_graph() -> TopologyGraph:
    """Return the module-level topology graph singleton."""
    global _graph
    if _graph is None:
        _graph = TopologyGraph()
    return _graph


def init_topology(cameras_json_path: Path) -> TopologyGraph:
    """Initialise the singleton from a cameras.json file."""
    global _graph
    _graph = TopologyGraph()
    _graph.load_from_cameras_json(cameras_json_path)
    return _graph
