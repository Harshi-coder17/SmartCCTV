"""
SmartCCTV SIH26187 — MediaPipe Pose Behavioural Signal Extractor.

Processes person crops through MediaPipe Pose to extract binary behavioural
signals (crawling, crouching, prone, etc.) with persistence filtering to
suppress single-frame noise.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np

from backend.config import settings

logger = logging.getLogger(__name__)

# MediaPipe landmark indices (used for posture assessment)
_MP_NOSE = 0
_MP_LEFT_SHOULDER = 11
_MP_RIGHT_SHOULDER = 12
_MP_LEFT_HIP = 23
_MP_RIGHT_HIP = 24
_MP_LEFT_ELBOW = 13
_MP_RIGHT_ELBOW = 14
_MP_LEFT_WRIST = 15
_MP_RIGHT_WRIST = 16
_MP_LEFT_EAR = 7
_MP_RIGHT_EAR = 8


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class PoseSignals:
    """Behavioural signals extracted from a person's pose."""

    is_crawling: bool = False
    is_crouching: bool = False
    is_prone: bool = False
    compressed_silhouette: bool = False
    arm_tucked: bool = False
    sustained_upward_gaze: bool = False
    jittery_head: bool = False
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Pose Engine
# ---------------------------------------------------------------------------


class PoseEngine:
    """MediaPipe Pose-based behavioural signal extractor.

    Per-track signal histories are maintained so that persistence
    filtering (N frames must agree before flagging) suppresses noise.
    """

    def __init__(self) -> None:
        """Initialise MediaPipe Pose and per-track history buffers."""
        self._pose = None
        self._load()

        # Per-track buffers: {track_id -> deque[bool]} for each signal
        _buf = lambda: deque(maxlen=settings.POSE_PERSISTENCE_FRAMES)  # noqa: E731
        self._crawl_buf: Dict[int, Deque[bool]] = defaultdict(_buf)
        self._crouch_buf: Dict[int, Deque[bool]] = defaultdict(_buf)
        self._prone_buf: Dict[int, Deque[bool]] = defaultdict(_buf)
        self._arm_tuck_buf: Dict[int, Deque[bool]] = defaultdict(_buf)
        self._gaze_buf: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=settings.POSE_PERSISTENCE_FRAMES))
        self._head_yaw_buf: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=settings.POSE_PERSISTENCE_FRAMES))

    def _load(self) -> None:
        """Load MediaPipe Pose solution."""
        try:
            import mediapipe as mp

            self._pose = mp.solutions.pose.Pose(  # type: ignore[attr-defined]
                static_image_mode=False,
                model_complexity=1,
                enable_segmentation=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            logger.info("MediaPipe Pose loaded.")
        except Exception as exc:
            logger.warning("MediaPipe Pose unavailable: %s", exc)
            self._pose = None

    def _persistent(self, buf: Deque[bool], n_frames: Optional[int] = None) -> bool:
        """Return True if the majority of the last N frames signal True."""
        if not buf:
            return False
        n = n_frames or settings.POSE_PERSISTENCE_FRAMES
        window = list(buf)[-n:]
        return sum(window) > len(window) / 2

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_signals(
        self,
        frame: np.ndarray,
        track_id: int,
        bbox: Tuple[float, float, float, float],
        height_buffer: List[float],
    ) -> PoseSignals:
        """Extract behavioural signals from a person crop.

        Args:
            frame:         Full BGR frame.
            track_id:      ByteTrack track ID for history lookup.
            bbox:          (x1, y1, x2, y2) bounding box in the frame.
            height_buffer: Historical bbox heights for crouching baseline.

        Returns:
            PoseSignals dataclass with boolean flags and confidence.
        """
        if self._pose is None:
            return PoseSignals()

        x1, y1, x2, y2 = (int(v) for v in bbox)
        crop = frame[y1:y2, x1:x2]
        if crop is None or crop.size == 0:
            return PoseSignals()

        try:
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            results = self._pose.process(rgb)

            if not results.pose_landmarks:
                return PoseSignals()

            lm = results.pose_landmarks.landmark
            confidence = float(lm[_MP_NOSE].visibility)

            # Run individual checks and update persistence buffers
            crawling_raw = self._check_crawling(lm, crop)
            crouching_raw = self._check_crouching(lm, height_buffer, crop)
            prone_raw = self._check_prone(lm, crop)
            arm_tuck_raw = self._check_arm_tuck(lm, crop)
            gaze_pitch = self._get_head_pitch(lm)
            head_yaw = self._get_head_yaw(lm)

            self._crawl_buf[track_id].append(crawling_raw)
            self._crouch_buf[track_id].append(crouching_raw)
            self._prone_buf[track_id].append(prone_raw)
            self._arm_tuck_buf[track_id].append(arm_tuck_raw)
            self._gaze_buf[track_id].append(gaze_pitch)
            self._head_yaw_buf[track_id].append(head_yaw)

            # Persistent signals (majority vote over N frames)
            is_crawling = self._persistent(self._crawl_buf[track_id])
            is_crouching = self._persistent(self._crouch_buf[track_id])
            is_prone = self._persistent(self._prone_buf[track_id])
            arm_tucked = self._persistent(self._arm_tuck_buf[track_id])

            # Sustained upward gaze: mean pitch below -0.1 (head tilted up)
            gaze_vals = list(self._gaze_buf[track_id])
            sustained_upward_gaze = (
                len(gaze_vals) >= settings.POSE_PERSISTENCE_FRAMES
                and float(np.mean(gaze_vals)) < -0.10
            )

            # Jittery head: high yaw variance
            yaw_vals = list(self._head_yaw_buf[track_id])
            jittery_head = (
                len(yaw_vals) >= settings.POSE_PERSISTENCE_FRAMES
                and float(np.var(yaw_vals)) > 0.05
            )

            compressed_silhouette = is_crouching or is_prone or is_crawling

            return PoseSignals(
                is_crawling=is_crawling,
                is_crouching=is_crouching,
                is_prone=is_prone,
                compressed_silhouette=compressed_silhouette,
                arm_tucked=arm_tucked,
                sustained_upward_gaze=sustained_upward_gaze,
                jittery_head=jittery_head,
                confidence=confidence,
            )

        except Exception as exc:
            logger.debug("PoseEngine error for track %d: %s", track_id, exc)
            return PoseSignals()

    # ------------------------------------------------------------------
    # Individual Checks
    # ------------------------------------------------------------------

    def _check_crawling(self, lm: list, crop: np.ndarray) -> bool:
        """Check if person is crawling (shoulder and hip at similar height).

        Crawling: shoulder Y and hip Y are close, and both are in the upper
        portion of the crop (i.e., body is nearly horizontal).
        """
        sh_y = (lm[_MP_LEFT_SHOULDER].y + lm[_MP_RIGHT_SHOULDER].y) / 2.0
        hip_y = (lm[_MP_LEFT_HIP].y + lm[_MP_RIGHT_HIP].y) / 2.0
        # Shoulders and hips at similar Y means horizontal body
        vertical_diff = abs(sh_y - hip_y)
        return vertical_diff < 0.15

    def _check_crouching(
        self,
        lm: list,
        height_buffer: List[float],
        crop: np.ndarray,
    ) -> bool:
        """Check if person is crouching relative to their own height baseline.

        Uses the 90th percentile of the historical height buffer as the
        upright baseline and detects a sustained drop below 60%.
        """
        if len(height_buffer) < 10:
            return False
        baseline = float(np.percentile(height_buffer, 90))
        current = height_buffer[-1] if height_buffer else baseline
        return current < baseline * 0.60

    def _check_prone(self, lm: list, crop: np.ndarray) -> bool:
        """Check if person appears prone (lying down).

        Single-frame check: shoulder-to-hip Y spread is very small AND
        nose Y is close to hip Y (entire body compressed vertically).
        """
        sh_y = (lm[_MP_LEFT_SHOULDER].y + lm[_MP_RIGHT_SHOULDER].y) / 2.0
        hip_y = (lm[_MP_LEFT_HIP].y + lm[_MP_RIGHT_HIP].y) / 2.0
        nose_y = lm[_MP_NOSE].y
        spread = abs(sh_y - hip_y)
        head_body_diff = abs(nose_y - hip_y)
        return spread < 0.10 and head_body_diff < 0.15

    def _check_arm_tuck(self, lm: list, crop: np.ndarray) -> bool:
        """Check if arms are tucked close to the torso (concealment posture).

        Arm tuck: elbow-to-hip distance is small compared to shoulder width.
        """
        sh_dist = abs(lm[_MP_LEFT_SHOULDER].x - lm[_MP_RIGHT_SHOULDER].x)
        left_elbow_hip = (
            (lm[_MP_LEFT_ELBOW].x - lm[_MP_LEFT_HIP].x) ** 2
            + (lm[_MP_LEFT_ELBOW].y - lm[_MP_LEFT_HIP].y) ** 2
        ) ** 0.5
        right_elbow_hip = (
            (lm[_MP_RIGHT_ELBOW].x - lm[_MP_RIGHT_HIP].x) ** 2
            + (lm[_MP_RIGHT_ELBOW].y - lm[_MP_RIGHT_HIP].y) ** 2
        ) ** 0.5
        avg_elbow_hip = (left_elbow_hip + right_elbow_hip) / 2.0
        return avg_elbow_hip < sh_dist * 0.5

    def _get_head_pitch(self, lm: list) -> float:
        """Compute approximate head pitch angle from nose-to-ear vertical offset.

        Returns:
            Negative values = upward gaze; positive = downward.
        """
        nose_y = lm[_MP_NOSE].y
        ear_y = (lm[_MP_LEFT_EAR].y + lm[_MP_RIGHT_EAR].y) / 2.0
        return float(nose_y - ear_y)

    def _get_head_yaw(self, lm: list) -> float:
        """Compute approximate head yaw from left-to-right ear horizontal spread.

        Returns:
            Normalised horizontal asymmetry [0, 1]; higher = more side-turned.
        """
        left_x = lm[_MP_LEFT_EAR].x
        right_x = lm[_MP_RIGHT_EAR].x
        mid_x = (left_x + right_x) / 2.0
        nose_x = lm[_MP_NOSE].x
        return float(abs(nose_x - mid_x))


# Singleton
pose_engine = PoseEngine()
