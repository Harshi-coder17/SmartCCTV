"""
SmartCCTV SIH26187 — Camera, Zone, Tripwire, CameraHealth ORM Models.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from backend.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# Zone
# ---------------------------------------------------------------------------


class Zone(Base):
    """Defines a geographic zone within a camera's field of view.

    Zones carry sensitivity levels and access rules used by the risk engine.
    """

    __tablename__ = "zones"

    zone_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    sensitivity_level: Mapped[int] = mapped_column(Integer, default=3)  # 1–5
    polygon_points: Mapped[List[Any]] = mapped_column(JSON, default=list)
    camera_ids: Mapped[List[str]] = mapped_column(JSON, default=list)
    allowed_time_start: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    allowed_time_end: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    min_authorization_level: Mapped[int] = mapped_column(Integer, default=1)
    crowd_threshold: Mapped[int] = mapped_column(Integer, default=10)
    loitering_threshold_secs: Mapped[int] = mapped_column(Integer, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    # Relationships
    tripwires: Mapped[List["Tripwire"]] = relationship(
        "Tripwire", back_populates="zone", foreign_keys="Tripwire.zone_id"
    )
    events: Mapped[List["Event"]] = relationship(  # type: ignore[name-defined]
        "Event", back_populates="zone", foreign_keys="Event.zone_id"
    )


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------


class Camera(Base):
    """Represents a physical surveillance camera registered in the system."""

    __tablename__ = "cameras"

    camera_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    location_name: Mapped[str] = mapped_column(String(256), nullable=False)
    gps_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gps_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rtsp_url: Mapped[str] = mapped_column(String(512), nullable=False)
    camera_type: Mapped[str] = mapped_column(String(16), default="visible")  # visible/thermal/ir
    capability_profile: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    zone_ids: Mapped[List[str]] = mapped_column(JSON, default=list)
    orientation_degrees: Mapped[float] = mapped_column(Float, default=0.0)
    expected_fps: Mapped[int] = mapped_column(Integer, default=30)
    calibration_version: Mapped[str] = mapped_column(String(64), default="v1.0")
    health_state: Mapped[str] = mapped_column(String(16), default="healthy")  # healthy/degraded/offline
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    # Relationships
    health_records: Mapped[List["CameraHealth"]] = relationship(
        "CameraHealth", back_populates="camera"
    )
    tripwires: Mapped[List["Tripwire"]] = relationship(
        "Tripwire", back_populates="camera", foreign_keys="Tripwire.camera_id"
    )
    observations: Mapped[List["Observation"]] = relationship(  # type: ignore[name-defined]
        "Observation", back_populates="camera"
    )
    tracks: Mapped[List["Track"]] = relationship(  # type: ignore[name-defined]
        "Track", back_populates="camera"
    )
    events: Mapped[List["Event"]] = relationship(  # type: ignore[name-defined]
        "Event", back_populates="camera", foreign_keys="Event.camera_id"
    )


# ---------------------------------------------------------------------------
# Tripwire
# ---------------------------------------------------------------------------


class Tripwire(Base):
    """A virtual line across which directional crossings are monitored."""

    __tablename__ = "tripwires"

    tripwire_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    camera_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cameras.camera_id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    point_a: Mapped[List[float]] = mapped_column(JSON, nullable=False)  # [x, y]
    point_b: Mapped[List[float]] = mapped_column(JSON, nullable=False)  # [x, y]
    permitted_direction: Mapped[str] = mapped_column(
        String(16), default="any"
    )  # any/inbound/outbound
    zone_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("zones.zone_id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    camera: Mapped["Camera"] = relationship(
        "Camera", back_populates="tripwires", foreign_keys=[camera_id]
    )
    zone: Mapped[Optional["Zone"]] = relationship(
        "Zone", back_populates="tripwires", foreign_keys=[zone_id]
    )


# ---------------------------------------------------------------------------
# CameraHealth
# ---------------------------------------------------------------------------


class CameraHealth(Base):
    """Periodic health snapshot for a camera (tamper, blur, FPS checks)."""

    __tablename__ = "camera_health"

    health_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    camera_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cameras.camera_id"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)  # healthy/degraded/offline
    fps_actual: Mapped[float] = mapped_column(Float, default=0.0)
    fps_expected: Mapped[float] = mapped_column(Float, default=30.0)
    blank_frame_score: Mapped[float] = mapped_column(Float, default=0.0)
    sharpness_score: Mapped[float] = mapped_column(Float, default=0.0)
    scene_change_score: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    camera: Mapped["Camera"] = relationship("Camera", back_populates="health_records")
