"""
SmartCCTV SIH26187 - Events API.

Paginated event history with filtering, full event detail including
explainable risk breakdown and cross-camera movement timeline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.event import Event
from backend.models.user import User
from backend.security.rbac import get_current_user

router = APIRouter(prefix="/events", tags=["Events"])


class EventSummary(BaseModel):
    event_id: str
    event_type: str
    severity: str
    risk_score: float
    camera_id: Optional[str]
    zone_id: Optional[str]
    status: str
    timestamp: datetime
    risk_factors: Dict[str, Any]


class EventDetail(EventSummary):
    evidence_manifest: Dict[str, Any]
    model_versions: Dict[str, str]
    rule_version: str
    calibration_version: str
    updated_at: datetime


@router.get("/", response_model=List[EventSummary])
async def list_events(
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    camera_id: Optional[str] = None,
    zone_id: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[EventSummary]:
    """Paginated event history with multi-field filtering."""
    filters = []
    if event_type:
        filters.append(Event.event_type == event_type)
    if severity:
        filters.append(Event.severity == severity)
    if camera_id:
        filters.append(Event.camera_id == camera_id)
    if zone_id:
        filters.append(Event.zone_id == zone_id)
    if status:
        filters.append(Event.status == status)
    if from_date:
        filters.append(Event.timestamp >= from_date)
    if to_date:
        filters.append(Event.timestamp <= to_date)

    query = (
        select(Event)
        .where(and_(*filters) if filters else True)
        .order_by(desc(Event.timestamp))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    events = result.scalars().all()

    return [
        EventSummary(
            event_id=e.event_id,
            event_type=e.event_type,
            severity=e.severity,
            risk_score=e.risk_score,
            camera_id=e.camera_id,
            zone_id=e.zone_id,
            status=e.status,
            timestamp=e.timestamp,
            risk_factors=e.risk_factors or {},
        )
        for e in events
    ]


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EventDetail:
    """Full event detail with evidence manifest and model versions."""
    result = await db.execute(select(Event).where(Event.event_id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    return EventDetail(
        event_id=event.event_id,
        event_type=event.event_type,
        severity=event.severity,
        risk_score=event.risk_score,
        camera_id=event.camera_id,
        zone_id=event.zone_id,
        status=event.status,
        timestamp=event.timestamp,
        updated_at=event.updated_at,
        risk_factors=event.risk_factors or {},
        evidence_manifest=event.evidence_manifest or {},
        model_versions=event.model_versions or {},
        rule_version=event.rule_version,
        calibration_version=event.calibration_version,
    )


@router.get("/{event_id}/timeline")
async def get_event_timeline(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Cross-camera movement timeline for the global identity involved in this event."""
    result = await db.execute(select(Event).where(Event.event_id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    if not event.global_identity_id:
        return {"global_identity_id": None, "sightings": [], "message": "No global identity linked"}

    from backend.core.correlation.graph import get_topology_graph
    from backend.core.correlation.matcher import EventCorrelator

    correlator = EventCorrelator(get_topology_graph())
    timeline = await correlator.build_timeline(event.global_identity_id, db)

    return {
        "global_identity_id": timeline.global_identity_id,
        "authorization_status": timeline.authorization_status,
        "is_provisional": timeline.is_provisional,
        "camera_count": timeline.camera_count,
        "first_seen": timeline.first_seen.isoformat() if timeline.first_seen else None,
        "last_seen": timeline.last_seen.isoformat() if timeline.last_seen else None,
        "sightings": [
            {
                "camera_id": s.camera_id,
                "camera_name": s.camera_name,
                "zone_id": s.zone_id,
                "timestamp": s.timestamp.isoformat(),
                "confidence": s.confidence,
                "location_name": s.location_name,
            }
            for s in timeline.sightings
        ],
    }


@router.get("/{event_id}/risk-breakdown")
async def get_risk_breakdown(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the explainable risk factor breakdown for an event."""
    result = await db.execute(select(Event).where(Event.event_id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    factors = event.risk_factors or {}
    return {
        "event_id": event_id,
        "total_score": event.risk_score,
        "severity": event.severity,
        "identity_tier": {
            k: v for k, v in factors.items()
            if k in ("zone_violation", "no_traceable_origin", "route_anomaly", "off_hours", "identity_score")
        },
        "behavior_tier": {
            k: v for k, v in factors.items()
            if k in (
                "trajectory_jagged", "stutter_gait", "boundary_hesitation",
                "sudden_level_change", "compressed_silhouette", "crawling_detected",
                "crouching_sustained", "group_huddling", "sustained_upward_gaze",
                "jittery_head", "arm_tucked", "behavior_score"
            )
        },
        "context": {
            k: v for k, v in factors.items()
            if k in ("context_multiplier", "zone_sensitivity_factor", "time_factor")
        },
        "model_versions": event.model_versions or {},
        "rule_version": event.rule_version,
        "calibration_version": event.calibration_version,
    }
