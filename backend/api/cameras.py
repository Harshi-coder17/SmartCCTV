"""
SmartCCTV SIH26187 - Camera Management API.

CRUD for camera registry, health history, and MJPEG stream endpoint.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.camera import Camera, CameraHealth, Zone, Tripwire
from backend.models.user import User
from backend.security.rbac import get_current_user, require_role
from backend.utils.logger import audit_log

router = APIRouter(prefix="/cameras", tags=["Cameras"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CameraCreate(BaseModel):
    camera_id: str
    name: str
    location_name: str
    gps_lat: float
    gps_lon: float
    rtsp_url: str
    camera_type: str = "visible"
    expected_fps: int = 30
    orientation_degrees: float = 0.0
    zone_ids: List[str] = []
    capability_profile: Dict[str, Any] = {}


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    location_name: Optional[str] = None
    rtsp_url: Optional[str] = None
    expected_fps: Optional[int] = None
    orientation_degrees: Optional[float] = None
    is_active: Optional[bool] = None
    zone_ids: Optional[List[str]] = None
    capability_profile: Optional[Dict[str, Any]] = None


class CameraResponse(BaseModel):
    camera_id: str
    name: str
    location_name: str
    gps_lat: float
    gps_lon: float
    camera_type: str
    health_state: str
    expected_fps: int
    is_active: bool
    capability_profile: Dict[str, Any]
    zone_ids: List[str]
    last_heartbeat: Optional[datetime]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/", response_model=List[CameraResponse])
async def list_cameras(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[CameraResponse]:
    """List all cameras with current health status."""
    result = await db.execute(select(Camera).order_by(Camera.name))
    cameras = result.scalars().all()
    return [
        CameraResponse(
            camera_id=c.camera_id,
            name=c.name,
            location_name=c.location_name,
            gps_lat=c.gps_lat,
            gps_lon=c.gps_lon,
            camera_type=c.camera_type,
            health_state=c.health_state,
            expected_fps=c.expected_fps,
            is_active=c.is_active,
            capability_profile=c.capability_profile or {},
            zone_ids=c.zone_ids or [],
            last_heartbeat=c.last_heartbeat,
        )
        for c in cameras
    ]


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CameraResponse:
    """Get a single camera with current health state."""
    result = await db.execute(select(Camera).where(Camera.camera_id == camera_id))
    camera = result.scalar_one_or_none()
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return CameraResponse(
        camera_id=camera.camera_id,
        name=camera.name,
        location_name=camera.location_name,
        gps_lat=camera.gps_lat,
        gps_lon=camera.gps_lon,
        camera_type=camera.camera_type,
        health_state=camera.health_state,
        expected_fps=camera.expected_fps,
        is_active=camera.is_active,
        capability_profile=camera.capability_profile or {},
        zone_ids=camera.zone_ids or [],
        last_heartbeat=camera.last_heartbeat,
    )


@router.get("/{camera_id}/health")
async def get_camera_health_history(
    camera_id: str,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """Paginated health history for a camera."""
    result = await db.execute(
        select(CameraHealth)
        .where(CameraHealth.camera_id == camera_id)
        .order_by(CameraHealth.timestamp.desc())
        .limit(limit)
    )
    records = result.scalars().all()
    return [
        {
            "timestamp": r.timestamp.isoformat(),
            "state": r.state,
            "fps_actual": r.fps_actual,
            "fps_expected": r.fps_expected,
            "blank_frame_score": r.blank_frame_score,
            "sharpness_score": r.sharpness_score,
            "scene_change_score": r.scene_change_score,
            "notes": r.notes,
        }
        for r in records
    ]


@router.post("/", response_model=CameraResponse, status_code=201)
async def create_camera(
    body: CameraCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> CameraResponse:
    """Register a new camera (admin only)."""
    existing = await db.execute(select(Camera).where(Camera.camera_id == body.camera_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Camera ID already exists")

    camera = Camera(
        camera_id=body.camera_id,
        name=body.name,
        location_name=body.location_name,
        gps_lat=body.gps_lat,
        gps_lon=body.gps_lon,
        rtsp_url=body.rtsp_url,
        camera_type=body.camera_type,
        expected_fps=body.expected_fps,
        orientation_degrees=body.orientation_degrees,
        zone_ids=body.zone_ids,
        capability_profile=body.capability_profile,
    )
    db.add(camera)
    await db.commit()
    await db.refresh(camera)

    await audit_log(
        "camera.created", "camera", camera.camera_id,
        actor_id=current_user.user_id, actor_role=current_user.role,
        after_state=body.model_dump(),
        ip_address=request.client.host if request.client else None,
        db=db,
    )

    return CameraResponse(
        camera_id=camera.camera_id, name=camera.name, location_name=camera.location_name,
        gps_lat=camera.gps_lat, gps_lon=camera.gps_lon, camera_type=camera.camera_type,
        health_state=camera.health_state, expected_fps=camera.expected_fps,
        is_active=camera.is_active, capability_profile=camera.capability_profile or {},
        zone_ids=camera.zone_ids or [], last_heartbeat=camera.last_heartbeat,
    )


@router.patch("/{camera_id}")
async def update_camera(
    camera_id: str,
    body: CameraUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> dict:
    """Update camera configuration (admin only)."""
    result = await db.execute(select(Camera).where(Camera.camera_id == camera_id))
    camera = result.scalar_one_or_none()
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    before = {"name": camera.name, "rtsp_url": camera.rtsp_url, "is_active": camera.is_active}
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(camera, field, value)

    await db.commit()
    await audit_log(
        "camera.updated", "camera", camera_id,
        actor_id=current_user.user_id, actor_role=current_user.role,
        before_state=before, after_state=body.model_dump(exclude_none=True),
        db=db,
    )
    return {"message": "Camera updated"}


@router.delete("/{camera_id}")
async def deactivate_camera(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> dict:
    """Deactivate a camera (admin only). Does not delete historical data."""
    result = await db.execute(select(Camera).where(Camera.camera_id == camera_id))
    camera = result.scalar_one_or_none()
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    camera.is_active = False
    await db.commit()
    return {"message": f"Camera {camera_id} deactivated"}


@router.get("/{camera_id}/stream")
async def mjpeg_stream(
    camera_id: str,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    MJPEG stream endpoint - serves the latest annotated frame for the camera.
    Falls back to a placeholder when the stream worker is not running.
    """
    from backend.core.stream_manager import get_stream_manager

    manager = get_stream_manager()

    async def frame_generator():
        while True:
            frame_bytes = manager.get_latest_frame(camera_id)
            if frame_bytes:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )
            await asyncio.sleep(1.0 / 15)  # 15 fps display rate

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
