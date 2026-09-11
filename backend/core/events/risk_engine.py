"""
SmartCCTV SIH26187 — Weighted Risk Scoring Engine (Step 29).

Computes an explainable, calibration-free risk score from identity flags,
behavioural signals, zone sensitivity, and temporal context.
All weights are loaded from data/risk_weights.json — no redeploy needed
for recalibration.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from backend.config import settings

logger = logging.getLogger(__name__)

# Default weight configuration (overridden by risk_weights.json)
_DEFAULT_WEIGHTS: Dict = {
    "identity": {
        "zone_violation": 30,
        "no_traceable_origin": 25,
        "route_anomaly": 15,
        "off_hours": 10,
    },
    "behavior": {
        "trajectory_jagged": 3,
        "stutter_gait": 3,
        "boundary_hesitation": 3,
        "sudden_level_change": 4,
        "compressed_silhouette": 2,
        "crawling_detected": 2,
        "crouching_sustained": 2,
        "group_huddling": 2,
        "sustained_upward_gaze": 2,
        "jittery_head": 2,
        "arm_tucked": 2,
    },
    "zone_sensitivity_factors": {
        "1": 0.6,
        "2": 0.6,
        "3": 1.0,
        "4": 1.4,
        "5": 1.4,
    },
    "time_factors": {
        "daytime_start": 6,
        "daytime_end": 20,
        "day_factor": 0.7,
        "night_factor": 1.3,
    },
    "severity_bands": {
        "low_max": 20,
        "medium_max": 40,
        "high_max": 60,
    },
    "no_identity_behavior_cap": 5,
}


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class TrajectoryFeatures:
    """Aggregated trajectory characteristics."""

    is_jagged: bool = False
    speed_variance: float = 0.0
    boundary_hesitation: bool = False
    sudden_level_change: bool = False
    stutter_gait: bool = False


@dataclass
class RiskContext:
    """All inputs to the risk scorer.

    Boolean flags map directly to weight keys in risk_weights.json.
    """

    # Identity flags
    zone_violation: bool = False
    no_traceable_origin: bool = False
    route_anomaly: bool = False

    # Temporal
    hour: int = 12   # 0–23 UTC hour of observation

    # Zone
    zone_sensitivity: int = 3   # 1–5
    camera_id: str = ""
    global_identity_id: Optional[str] = None

    # Zone time window (for off-hours check)
    zone_allowed_start: Optional[str] = None   # "HH:MM"
    zone_allowed_end: Optional[str] = None     # "HH:MM"

    # Behavioural flags (from PoseEngine / Detector)
    trajectory_jagged: bool = False
    stutter_gait: bool = False
    boundary_hesitation: bool = False
    sudden_level_change: bool = False
    compressed_silhouette: bool = False
    crawling_detected: bool = False
    crouching_sustained: bool = False
    group_huddling: bool = False
    sustained_upward_gaze: bool = False
    jittery_head: bool = False
    arm_tucked: bool = False


@dataclass
class RiskScore:
    """Fully explainable risk assessment output."""

    total_score: float
    severity: str                              # low / medium / high / critical
    identity_score: float
    behavior_score: float
    context_multiplier: float
    factor_breakdown: Dict[str, float] = field(default_factory=dict)
    thresholds_used: Dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Risk Engine
# ---------------------------------------------------------------------------


class RiskEngine:
    """Computes weighted risk scores per the SIH26187 Step 29 formula.

    Loads weights from risk_weights.json; falls back to embedded defaults
    if the file is absent so the system never fails to score.
    """

    def __init__(self) -> None:
        """Load weight configuration."""
        self._weights = self._load_weights()

    def _load_weights(self) -> Dict:
        """Load risk weights from JSON, falling back to embedded defaults."""
        path = Path(settings.RISK_WEIGHTS_JSON_PATH)
        if path.exists():
            try:
                with open(path) as f:
                    loaded = json.load(f)
                logger.info("Risk weights loaded from %s.", path)
                return loaded
            except Exception as exc:
                logger.warning("Failed to load risk_weights.json (%s); using defaults.", exc)
        return _DEFAULT_WEIGHTS

    def reload_weights(self) -> None:
        """Reload weights from disk without restarting the process."""
        self._weights = self._load_weights()
        logger.info("Risk weights reloaded.")

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def score(self, context: RiskContext) -> RiskScore:
        """Compute the risk score for a detection context.

        Args:
            context: All input flags and zone/time metadata.

        Returns:
            RiskScore with total, severity, and per-factor breakdown.
        """
        weights = self._weights
        id_weights = weights.get("identity", {})
        beh_weights = weights.get("behavior", {})
        zone_factors = weights.get("zone_sensitivity_factors", {})
        time_cfg = weights.get("time_factors", {})
        bands = weights.get("severity_bands", {})
        no_id_cap = weights.get("no_identity_behavior_cap", 5)

        factor_breakdown: Dict[str, float] = {}

        # ------------------------------------------------------------------
        # Off-hours check
        # ------------------------------------------------------------------
        off_hours = self._check_off_hours(
            context.hour,
            context.zone_allowed_start,
            context.zone_allowed_end,
            time_cfg,
        )

        # ------------------------------------------------------------------
        # Identity score
        # ------------------------------------------------------------------
        identity_score = 0.0
        for flag, key in [
            (context.zone_violation, "zone_violation"),
            (context.no_traceable_origin, "no_traceable_origin"),
            (context.route_anomaly, "route_anomaly"),
            (off_hours, "off_hours"),
        ]:
            w = id_weights.get(key, 0)
            contribution = w if flag else 0.0
            factor_breakdown[key] = contribution
            identity_score += contribution

        # ------------------------------------------------------------------
        # Context multiplier
        # ------------------------------------------------------------------
        sens_key = str(min(max(context.zone_sensitivity, 1), 5))
        zone_sensitivity_factor = float(zone_factors.get(sens_key, 1.0))

        day_start = int(time_cfg.get("daytime_start", 6))
        day_end = int(time_cfg.get("daytime_end", 20))
        if day_start <= context.hour < day_end:
            time_factor = float(time_cfg.get("day_factor", 0.7))
        else:
            time_factor = float(time_cfg.get("night_factor", 1.3))

        context_multiplier = zone_sensitivity_factor * time_factor
        factor_breakdown["zone_sensitivity_factor"] = zone_sensitivity_factor
        factor_breakdown["time_factor"] = time_factor
        factor_breakdown["context_multiplier"] = context_multiplier

        # ------------------------------------------------------------------
        # Behaviour score
        # ------------------------------------------------------------------
        behavior_flags = {
            "trajectory_jagged": context.trajectory_jagged,
            "stutter_gait": context.stutter_gait,
            "boundary_hesitation": context.boundary_hesitation,
            "sudden_level_change": context.sudden_level_change,
            "compressed_silhouette": context.compressed_silhouette,
            "crawling_detected": context.crawling_detected,
            "crouching_sustained": context.crouching_sustained,
            "group_huddling": context.group_huddling,
            "sustained_upward_gaze": context.sustained_upward_gaze,
            "jittery_head": context.jittery_head,
            "arm_tucked": context.arm_tucked,
        }

        behavior_score_raw = 0.0
        for key, active in behavior_flags.items():
            w = beh_weights.get(key, 0)
            contribution = w if active else 0.0
            factor_breakdown[f"beh_{key}"] = contribution
            behavior_score_raw += contribution

        behavior_score = behavior_score_raw * context_multiplier

        # Identity-gated behaviour contribution
        if identity_score == 0:
            behavior_contribution = min(behavior_score, float(no_id_cap))
        else:
            behavior_contribution = behavior_score

        factor_breakdown["behavior_score_raw"] = behavior_score_raw
        factor_breakdown["behavior_score_effective"] = behavior_contribution

        # ------------------------------------------------------------------
        # Total score
        # ------------------------------------------------------------------
        total_score = identity_score + behavior_contribution

        # ------------------------------------------------------------------
        # Severity band
        # ------------------------------------------------------------------
        low_max = int(bands.get("low_max", settings.RISK_LOW_MAX))
        medium_max = int(bands.get("medium_max", settings.RISK_MEDIUM_MAX))
        high_max = int(bands.get("high_max", settings.RISK_HIGH_MAX))

        if total_score < low_max:
            severity = "low"
        elif total_score < medium_max:
            severity = "medium"
        elif total_score < high_max:
            severity = "high"
        else:
            severity = "critical"

        return RiskScore(
            total_score=total_score,
            severity=severity,
            identity_score=identity_score,
            behavior_score=behavior_contribution,
            context_multiplier=context_multiplier,
            factor_breakdown=factor_breakdown,
            thresholds_used={
                "low_max": low_max,
                "medium_max": medium_max,
                "high_max": high_max,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_off_hours(
        hour: int,
        zone_start: Optional[str],
        zone_end: Optional[str],
        time_cfg: Dict,
    ) -> bool:
        """Determine if the hour falls outside the zone's allowed window.

        Args:
            hour:       UTC hour (0–23).
            zone_start: Allowed start time string "HH:MM" or None.
            zone_end:   Allowed end time string "HH:MM" or None.
            time_cfg:   Time factor configuration dict.

        Returns:
            True if outside allowed window.
        """
        if zone_start and zone_end:
            try:
                start_h = int(zone_start.split(":")[0])
                end_h = int(zone_end.split(":")[0])
                if start_h <= end_h:
                    return not (start_h <= hour < end_h)
                else:
                    # Wraps midnight
                    return not (hour >= start_h or hour < end_h)
            except (ValueError, IndexError):
                pass

        # Fallback to global daytime definition
        day_start = int(time_cfg.get("daytime_start", 6))
        day_end = int(time_cfg.get("daytime_end", 20))
        return not (day_start <= hour < day_end)

    @staticmethod
    def _compute_trajectory_features(
        track_history: list,
    ) -> TrajectoryFeatures:
        """Derive trajectory flags from a list of (cx, cy) centroid points.

        Args:
            track_history: Ordered list of (cx, cy) tuples.

        Returns:
            TrajectoryFeatures with computed flags.
        """
        import numpy as np

        features = TrajectoryFeatures()

        if len(track_history) < 5:
            return features

        pts = np.array(track_history, dtype=np.float32)
        # Speed: frame-to-frame displacement
        displacements = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        speed_variance = float(np.var(displacements))
        features.speed_variance = speed_variance
        features.stutter_gait = speed_variance > 200.0  # pixels²

        # Jagged path: sum of direction changes
        if len(pts) >= 3:
            dirs = np.diff(pts, axis=0)
            angles = []
            for i in range(len(dirs) - 1):
                a, b = dirs[i], dirs[i + 1]
                cos_val = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-6)
                angles.append(float(np.arccos(np.clip(cos_val, -1.0, 1.0))))
            mean_angle_change = float(np.mean(angles)) if angles else 0.0
            features.is_jagged = mean_angle_change > 1.0  # radians ~57°

        return features


# Singleton
risk_engine = RiskEngine()
