"""
SmartCCTV SIH26187 — Event and Alert ORM Models.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from backend.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------


class Event(Base):
    """Security event raised by the detection and rule engines.

    An event captures everything needed for forensic review:
    evidence manifest, risk breakdown, model versions, calibration snapshot.
    """

    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # zone_intrusion / tripwire_crossing / loitering / wrong_direction /
    # abandoned_object / camera_tamper / crowd_anomaly
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # low / medium / high / critical
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_factors: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    camera_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("cameras.camera_id"), nullable=True, index=True
    )
    zone_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("zones.zone_id"), nullable=True
    )
    track_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tracks.track_id"), nullable=True
    )
    global_identity_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("global_identities.identity_id"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    # open / acknowledged / verified / false_alarm / escalated / closed

    evidence_manifest: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    model_versions: Mapped[Dict[str, str]] = mapped_column(JSON, default=dict)
    rule_version: Mapped[str] = mapped_column(String(32), default="v1.0")
    calibration_version: Mapped[str] = mapped_column(String(32), default="v1.0")

    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    # Relationships
    camera: Mapped[Optional["Camera"]] = relationship(  # type: ignore[name-defined]
        "Camera", back_populates="events", foreign_keys=[camera_id]
    )
    zone: Mapped[Optional["Zone"]] = relationship(  # type: ignore[name-defined]
        "Zone", back_populates="events", foreign_keys=[zone_id]
    )
    track: Mapped[Optional["Track"]] = relationship(  # type: ignore[name-defined]
        "Track", back_populates="events", foreign_keys=[track_id]
    )
    global_identity: Mapped[Optional["GlobalIdentity"]] = relationship(  # type: ignore[name-defined]
        "GlobalIdentity", back_populates="events", foreign_keys=[global_identity_id]
    )
    alert: Mapped[Optional["Alert"]] = relationship(
        "Alert", back_populates="event", uselist=False
    )


# ---------------------------------------------------------------------------
# Alert
# ---------------------------------------------------------------------------


class Alert(Base):
    """Operator-facing alert derived from an event, with disposition tracking."""

    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.event_id"), nullable=False, unique=True, index=True
    )
    operator_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.user_id"), nullable=True
    )

    disposition: Mapped[str] = mapped_column(String(24), default="pending")
    # pending / confirmed / false_positive / inconclusive
    disposition_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    disposition_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)

    # Relationships
    event: Mapped["Event"] = relationship("Event", back_populates="alert")
    operator: Mapped[Optional["User"]] = relationship(  # type: ignore[name-defined]
        "User", back_populates="alerts_handled", foreign_keys=[operator_id]
    )
