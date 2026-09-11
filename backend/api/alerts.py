"""
SmartCCTV SIH26187 - Alerts API + WebSocket Feed.

Provides:
  - REST: active alert queue, paginated history, operator disposition
  - WebSocket /ws/alerts: real-time push to all connected operators,
    re-validated every 5 minutes for long-lived connections
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.event import Event, Alert
from backend.models.user import User
from backend.security.auth import verify_access_token
from backend.security.rbac import get_current_user
from backend.utils.logger import audit_log

router = APIRouter(tags=["Alerts"])


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------


class AlertConnectionManager:
    """Manages all active WebSocket connections for the alert feed."""

    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        """Send alert payload to all connected clients. Drop stale connections."""
        dead: List[WebSocket] = []
        message = json.dumps(payload, default=str)
        for ws in list(self._connections):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


# Module-level singleton — shared with the event pipeline
_manager = AlertConnectionManager()


def get_alert_manager() -> AlertConnectionManager:
    return _manager


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DispositionUpdate(BaseModel):
    disposition: str  # confirmed | false_positive | inconclusive
    reason: Optional[str] = None


class AlertResponse(BaseModel):
    alert_id: str
    event_id: str
    event_type: str
    severity: str
    risk_score: float
    camera_id: Optional[str]
    zone_id: Optional[str]
    timestamp: datetime
    disposition: str
    disposition_reason: Optional[str]
    factor_breakdown: Dict[str, Any]
    evidence_manifest: Dict[str, Any]
    model_versions: Dict[str, str]


# ---------------------------------------------------------------------------
# REST routes
# ---------------------------------------------------------------------------


@router.get("/alerts/", response_model=List[AlertResponse])
async def list_alerts(
    severity: Optional[str] = None,
    disposition: Optional[str] = None,
    camera_id: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[AlertResponse]:
    """
    Return active alert queue sorted by risk score descending.
    Supports filtering by severity, disposition, and camera.
    """
    query = (
        select(Alert, Event)
        .join(Event, Alert.event_id == Event.event_id)
        .order_by(desc(Event.risk_score), desc(Alert.created_at))
        .limit(limit)
        .offset(offset)
    )
    if severity:
        query = query.where(Event.severity == severity)
    if disposition:
        query = query.where(Alert.disposition == disposition)
    if camera_id:
        query = query.where(Event.camera_id == camera_id)

    result = await db.execute(query)
    rows = result.all()

    return [
        AlertResponse(
            alert_id=alert.alert_id,
            event_id=event.event_id,
            event_type=event.event_type,
            severity=event.severity,
            risk_score=event.risk_score,
            camera_id=event.camera_id,
            zone_id=event.zone_id,
            timestamp=event.timestamp,
            disposition=alert.disposition,
            disposition_reason=alert.disposition_reason,
            factor_breakdown=event.risk_factors or {},
            evidence_manifest=event.evidence_manifest or {},
            model_versions=event.model_versions or {},
        )
        for alert, event in rows
    ]


@router.patch("/alerts/{alert_id}/disposition")
async def set_disposition(
    alert_id: str,
    body: DispositionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Record operator disposition for an alert."""
    valid_dispositions = {"confirmed", "false_positive", "inconclusive"}
    if body.disposition not in valid_dispositions:
        raise HTTPException(
            status_code=400,
            detail=f"disposition must be one of: {valid_dispositions}",
        )

    result = await db.execute(select(Alert).where(Alert.alert_id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    before = {"disposition": alert.disposition, "reason": alert.disposition_reason}
    alert.disposition = body.disposition
    alert.disposition_reason = body.reason
    alert.disposition_timestamp = datetime.utcnow()
    alert.operator_id = current_user.user_id

    # Update parent event status
    evt_result = await db.execute(select(Event).where(Event.event_id == alert.event_id))
    event = evt_result.scalar_one_or_none()
    if event:
        if body.disposition == "confirmed":
            event.status = "verified"
        elif body.disposition == "false_positive":
            event.status = "false_alarm"
        else:
            event.status = "acknowledged"

    await db.commit()

    await audit_log(
        "alert.disposition",
        "alert",
        alert_id,
        actor_id=current_user.user_id,
        actor_role=current_user.role,
        before_state=before,
        after_state={"disposition": body.disposition, "reason": body.reason},
        db=db,
    )

    # Broadcast disposition update to all WebSocket clients
    await _manager.broadcast({
        "type": "alert_disposition",
        "alert_id": alert_id,
        "disposition": body.disposition,
        "operator": current_user.username,
        "timestamp": datetime.utcnow().isoformat(),
    })

    return {"message": "Disposition recorded"}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


@router.websocket("/ws/alerts")
async def websocket_alert_feed(websocket: WebSocket, token: Optional[str] = None) -> None:
    """
    Real-time alert feed over secure WebSocket.

    Authentication: JWT token passed as query param ?token=<access_token>
    Re-validation: every 5 minutes for long-lived connections.
    """
    # Initial authentication
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    try:
        payload = verify_access_token(token)
        user_id = payload.get("sub")
        user_role = payload.get("role")
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await _manager.connect(websocket)
    REVALIDATE_INTERVAL = 300  # 5 minutes

    try:
        last_validated = asyncio.get_event_loop().time()
        await websocket.send_text(json.dumps({
            "type": "connected",
            "message": f"Alert feed connected. Role: {user_role}",
            "connections": _manager.connection_count,
        }))

        while True:
            # Re-validate token periodically
            now = asyncio.get_event_loop().time()
            if now - last_validated > REVALIDATE_INTERVAL:
                try:
                    verify_access_token(token)
                    last_validated = now
                except Exception:
                    await websocket.close(code=4001, reason="Token expired")
                    return

            # Keep connection alive - wait for any client message or timeout
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Handle ping/pong keepalive from client
                if msg == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send keepalive to detect dead connections
                try:
                    await websocket.send_text(json.dumps({"type": "keepalive"}))
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    finally:
        _manager.disconnect(websocket)
