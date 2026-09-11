"""
SmartCCTV SIH26187 — Track, Observation, GlobalIdentity ORM Models.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from backend.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# GlobalIdentity
# ---------------------------------------------------------------------------


class GlobalIdentity(Base):
    """Cross-camera persistent identity linking local tracks to a single entity.

    Authorization status drives risk scoring. Movement log is an append-only
    JSON list of sightings across all cameras.
    """

    __tablename__ = "global_identities"

    identity_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)

    authorization_status: Mapped[str] = mapped_column(
        String(16), default="unauthorized", index=True
    )  # unauthorized / authorized / provisional

    authorized_person_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("personnel.person_id"), nullable=True
    )
    matched_embedding_version: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )

    # JSON append-only list of {camera_id, zone_id, timestamp, confidence}
    movement_log: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)

    reid_embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)

    # Relationships
    authorized_person: Mapped[Optional["Personnel"]] = relationship(  # type: ignore[name-defined]
        "Personnel",
        back_populates="global_identities",
        foreign_keys=[authorized_person_id],
    )
    tracks: Mapped[List["Track"]] = relationship(
        "Track", back_populates="global_identity"
    )
    events: Mapped[List["Event"]] = relationship(  # type: ignore[name-defined]
        "Event",
        back_populates="global_identity",
        foreign_keys="Event.global_identity_id",
    )


# ---------------------------------------------------------------------------
# Track
# ---------------------------------------------------------------------------


class Track(Base):
    """Local track within a single camera's view, optionally linked to a GlobalIdentity."""

    __tablename__ = "tracks"

    track_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    local_track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    camera_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cameras.camera_id"), nullable=False, index=True
    )
    global_identity_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("global_identities.identity_id"),
        nullable=True,
        index=True,
    )

    start_time: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # JSON list of {x, y, t} trajectory points
    trajectory: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    direction_vector: Mapped[Optional[Dict[str, float]]] = mapped_column(JSON, nullable=True)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    camera: Mapped["Camera"] = relationship(  # type: ignore[name-defined]
        "Camera", back_populates="tracks"
    )
    global_identity: Mapped[Optional["GlobalIdentity"]] = relationship(
        "GlobalIdentity", back_populates="tracks"
    )
    observations: Mapped[List["Observation"]] = relationship(
        "Observation", back_populates="track", foreign_keys="Observation.track_id"
    )
    events: Mapped[List["Event"]] = relationship(  # type: ignore[name-defined]
        "Event", back_populates="track", foreign_keys="Event.track_id"
    )


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------


class Observation(Base):
    """Single-frame detection record produced by the perception pipeline."""

    __tablename__ = "observations"

    observation_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    camera_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cameras.camera_id"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    object_class: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    bbox_x1: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y1: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_x2: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y2: Mapped[float] = mapped_column(Float, nullable=False)

    track_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tracks.track_id"), nullable=True, index=True
    )
    model_version: Mapped[str] = mapped_column(String(64), default="v1.0")
    frame_number: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    camera: Mapped["Camera"] = relationship(  # type: ignore[name-defined]
        "Camera", back_populates="observations"
    )
    track: Mapped[Optional["Track"]] = relationship(
        "Track", back_populates="observations", foreign_keys=[track_id]
    )
