"""
SmartCCTV SIH26187 — Asyncio Multi-Camera Stream Manager.

Manages one CameraWorker coroutine per camera.  Each worker reads frames
from RTSP/file sources, maintains a rolling evidence ring buffer, and
forwards analytics frames to the AI perception pipeline queue.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque, Dict, Optional, Tuple

import cv2
import numpy as np

from backend.config import settings

logger = logging.getLogger(__name__)

# Type alias for ring buffer entries
_RingEntry = Tuple[datetime, np.ndarray]

# Exponential backoff limits in seconds
_BACKOFF_MIN = 1.0
_BACKOFF_MAX = 60.0


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class CameraConfig:
    """Minimal configuration needed to open a camera stream."""

    camera_id: str
    rtsp_url: str
    expected_fps: int = 30
    camera_type: str = "visible"


@dataclass
class FramePacket:
    """Frame packet dispatched from a CameraWorker to the analytics queue."""

    camera_id: str
    frame_number: int
    timestamp: datetime
    frame: np.ndarray
    is_analytics_frame: bool


# ---------------------------------------------------------------------------
# Camera Worker
# ---------------------------------------------------------------------------


class CameraWorker:
    """Asyncio worker that reads frames from one camera.

    Responsibilities:
    - Capture frames at native FPS.
    - Maintain a rolling ring buffer of (timestamp, frame) tuples for
      evidence clip extraction.
    - Forward every Nth frame (analytics_fps) to the shared analytics queue.
    - Emit health heartbeats on a configurable interval.
    - Reconnect with exponential backoff on failure.
    """

    def __init__(
        self,
        config: CameraConfig,
        analytics_queue: asyncio.Queue,
        health_queue: asyncio.Queue,
    ) -> None:
        """Initialise the worker.

        Args:
            config:          Camera connection and capability parameters.
            analytics_queue: Queue consumed by the perception pipeline.
            health_queue:    Queue for health heartbeat events.
        """
        self.config = config
        self.analytics_queue = analytics_queue
        self.health_queue = health_queue

        # Rolling buffer: enough frames to cover pre + post event window.
        ring_size = (
            settings.EVIDENCE_PRE_EVENT_SECS + settings.EVIDENCE_POST_EVENT_SECS
        ) * config.expected_fps
        self.ring_buffer: Deque[_RingEntry] = deque(maxlen=max(ring_size, 60))

        self._stop_event = asyncio.Event()
        self._frame_number = 0
        self._fps_actual: float = 0.0
        self._last_health_time: float = 0.0
        self._task: Optional[asyncio.Task] = None

    def get_ring_buffer_snapshot(self) -> list[_RingEntry]:
        """Return a copy of the current ring buffer contents."""
        return list(self.ring_buffer)

    async def start(self) -> None:
        """Launch the worker coroutine as a background asyncio task."""
        self._task = asyncio.create_task(
            self._run(), name=f"cam-worker-{self.config.camera_id}"
        )

    async def stop(self) -> None:
        """Signal graceful shutdown and wait for the task to finish."""
        self._stop_event.set()
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        logger.info("CameraWorker stopped: %s", self.config.camera_id)

    async def _run(self) -> None:
        """Main capture loop with reconnection and backoff."""
        backoff = _BACKOFF_MIN

        while not self._stop_event.is_set():
            cap = await asyncio.to_thread(
                cv2.VideoCapture, self.config.rtsp_url
            )
            if not cap.isOpened():
                logger.warning(
                    "Camera %s: cannot open source '%s'. Retrying in %.1fs.",
                    self.config.camera_id,
                    self.config.rtsp_url,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_MAX)
                continue

            logger.info("Camera %s: stream opened.", self.config.camera_id)
            backoff = _BACKOFF_MIN
            await self._capture_loop(cap)
            cap.release()

            if not self._stop_event.is_set():
                logger.warning(
                    "Camera %s: stream lost. Reconnecting in %.1fs.",
                    self.config.camera_id,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _BACKOFF_MAX)

    async def _capture_loop(self, cap: cv2.VideoCapture) -> None:
        """Read frames from an open VideoCapture and dispatch them."""
        frame_count_window = 0
        window_start = time.monotonic()
        analytics_skip = 0

        while not self._stop_event.is_set():
            ok, frame = await asyncio.to_thread(cap.read)
            if not ok or frame is None:
                break

            now = datetime.utcnow()
            mono_now = time.monotonic()
            self.ring_buffer.append((now, frame))
            self._frame_number += 1
            frame_count_window += 1

            # Compute rolling FPS every second.
            elapsed = mono_now - window_start
            if elapsed >= 1.0:
                self._fps_actual = frame_count_window / elapsed
                frame_count_window = 0
                window_start = mono_now

            # Forward analytics frames.
            analytics_skip += 1
            is_analytics = analytics_skip >= settings.ANALYTICS_FPS
            if is_analytics:
                analytics_skip = 0

            packet = FramePacket(
                camera_id=self.config.camera_id,
                frame_number=self._frame_number,
                timestamp=now,
                frame=frame,
                is_analytics_frame=is_analytics,
            )
            try:
                self.analytics_queue.put_nowait(packet)
            except asyncio.QueueFull:
                pass  # Drop frame rather than block; analytics pipeline is behind.

            # Health heartbeat.
            if mono_now - self._last_health_time >= settings.CAMERA_HEALTH_INTERVAL_SECS:
                self._last_health_time = mono_now
                try:
                    self.health_queue.put_nowait(
                        {
                            "camera_id": self.config.camera_id,
                            "fps_actual": self._fps_actual,
                            "fps_expected": self.config.expected_fps,
                            "frame": frame,
                            "timestamp": now,
                        }
                    )
                except asyncio.QueueFull:
                    pass

            # Yield to the event loop to avoid blocking.
            await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# Stream Manager
# ---------------------------------------------------------------------------


class StreamManager:
    """Manages the lifecycle of all CameraWorker instances.

    Used as a singleton started during FastAPI lifespan.
    """

    def __init__(self) -> None:
        """Initialise with empty worker registry."""
        self._workers: Dict[str, CameraWorker] = {}
        self.analytics_queue: asyncio.Queue = asyncio.Queue(maxsize=512)
        self.health_queue: asyncio.Queue = asyncio.Queue(maxsize=128)

    async def load_cameras_from_db(self, db: "AsyncSession") -> list[CameraConfig]:  # type: ignore[name-defined]
        """Load active cameras from the database.

        Args:
            db: AsyncSession provided by FastAPI dependency injection.

        Returns:
            List of CameraConfig objects for all active cameras.
        """
        from sqlalchemy import select
        from backend.models.camera import Camera

        result = await db.execute(select(Camera).where(Camera.is_active == True))  # noqa: E712
        cameras = result.scalars().all()
        return [
            CameraConfig(
                camera_id=c.camera_id,
                rtsp_url=c.rtsp_url,
                expected_fps=c.expected_fps,
                camera_type=c.camera_type,
            )
            for c in cameras
        ]

    async def start(self, configs: Optional[list[CameraConfig]] = None) -> None:
        """Start workers for all provided camera configurations, or load from DB if omitted.

        Args:
            configs: Optional list of camera configs. If None, loaded from database.
        """
        if configs is None:
            from backend.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                configs = await self.load_cameras_from_db(db)

        for config in configs:
            await self.add_camera(config)
        logger.info(
            "StreamManager started with %d camera workers.", len(self._workers)
        )

    async def stop(self) -> None:
        """Gracefully stop all camera workers."""
        for camera_id, worker in list(self._workers.items()):
            logger.info("Stopping worker for camera %s…", camera_id)
            await worker.stop()
        self._workers.clear()
        logger.info("StreamManager: all workers stopped.")

    async def add_camera(self, config: CameraConfig) -> None:
        """Hot-add a new camera worker.

        Args:
            config: Configuration for the new camera.
        """
        if config.camera_id in self._workers:
            logger.warning(
                "Camera %s already registered; skipping.", config.camera_id
            )
            return
        worker = CameraWorker(config, self.analytics_queue, self.health_queue)
        self._workers[config.camera_id] = worker
        await worker.start()
        logger.info("Camera worker added: %s -> %s", config.camera_id, config.rtsp_url)

    async def remove_camera(self, camera_id: str) -> None:
        """Gracefully stop and remove a camera worker.

        Args:
            camera_id: The camera to remove.
        """
        worker = self._workers.pop(camera_id, None)
        if worker:
            await worker.stop()
        else:
            logger.warning("remove_camera: unknown camera_id %s", camera_id)

    def get_ring_buffer(self, camera_id: str) -> list[_RingEntry]:
        """Return the ring buffer snapshot for a given camera.

        Args:
            camera_id: Camera to query.

        Returns:
            List of (timestamp, frame) tuples, oldest first.
        """
        worker = self._workers.get(camera_id)
        if worker is None:
            return []
        return worker.get_ring_buffer_snapshot()

    def get_latest_frame(self, camera_id: str) -> Optional[np.ndarray]:
        """Return the most recent frame from a camera's ring buffer.

        Args:
            camera_id: Camera to query.

        Returns:
            NumPy frame array or None if no frames available.
        """
        buf = self.get_ring_buffer(camera_id)
        if not buf:
            return None
        return buf[-1][1]

    def list_camera_ids(self) -> list[str]:
        """Return the list of currently registered camera IDs."""
        return list(self._workers.keys())

    def get_camera_statuses(self) -> dict[str, str]:
        """Return a dict of {camera_id: 'running'|'stopped'} for all workers."""
        return {
            cid: ("running" if w._task is not None and not w._task.done() else "stopped")
            for cid, w in self._workers.items()
        }

    @property
    def is_running(self) -> bool:
        return any(
            w._task is not None and not w._task.done()
            for w in self._workers.values()
        )

    def get_latest_frame(self, camera_id: str) -> Optional[bytes]:
        """Return the latest frame encoded as JPEG bytes for MJPEG streaming."""
        buf = self.get_ring_buffer(camera_id)
        if not buf:
            return None
        frame = buf[-1][1]
        if frame is None:
            return None
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ok:
            return None
        return bytes(encoded)


# Singleton instance
stream_manager = StreamManager()


def get_stream_manager() -> StreamManager:
    """Return the module-level StreamManager singleton."""
    return stream_manager
