"""
SmartCCTV SIH26187 - Admin API.

Admin-only configuration endpoints:
  - Zone CRUD
  - Tripwire CRUD
  - Authorized personnel (with face enrollment)
  - Watchlist management
  - Audit log viewer (auditor+ only)
  - Model registry management
  - Camera topology
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.camera import Zone, Tripwire
from backend.models.audit import AuditAction
from backend.models.user import Personnel, Watchlist
from backend.security.rbac import get_current_user, require_role
from backend.models.user import User
from backend.utils.logger import audit_log
from backend.utils.model_registry import get_registry

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ZoneCreate(BaseModel):
    name: str
    sensitivity_level: int  # 1-5
    polygon_points: List[List[float]]
    camera_ids: List[str] = []
    allowed_time_start: str = "00:00"
    allowed_time_end: str = "23:59"
    min_authorization_level: int = 1
    loitering_threshold_secs: int = 30


class TripwireCreate(BaseModel):
    camera_id: str
    name: str
    point_a: List[float]
    point_b: List[float]
    permitted_direction: str = "any"
    zone_id: Optional[str] = None


class PersonnelCreate(BaseModel):
    name: str
    designation: str
    authorization_level: int  # 1-5


class WatchlistCreate(BaseModel):
    label: str
    notes: str = ""


class ModelDeprecateRequest(BaseModel):
    model_name: str
    version: str
    reason: str


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------


@router.get("/zones/")
async def list_zones(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "supervisor", "operator")),
) -> List[dict]:
    result = await db.execute(select(Zone).order_by(Zone.name))
    return [
        {
            "zone_id": z.zone_id,
            "name": z.name,
            "sensitivity_level": z.sensitivity_level,
            "polygon_points": z.polygon_points,
            "camera_ids": z.camera_ids or [],
            "min_authorization_level": z.min_authorization_level,
            "is_active": z.is_active,
        }
        for z in result.scalars().all()
    ]


@router.post("/zones/", status_code=201)
async def create_zone(
    body: ZoneCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> dict:
    import uuid
    zone = Zone(
        zone_id=str(uuid.uuid4()),
        name=body.name,
        sensitivity_level=body.sensitivity_level,
        polygon_points=body.polygon_points,
        camera_ids=body.camera_ids,
        allowed_time_start=body.allowed_time_start,
        allowed_time_end=body.allowed_time_end,
        min_authorization_level=body.min_authorization_level,
        loitering_threshold_secs=body.loitering_threshold_secs,
        calibration_version="v1.0",
    )
    db.add(zone)
    await db.commit()
    await audit_log("zone.created", "zone", zone.zone_id,
                    actor_id=current_user.user_id, actor_role=current_user.role, db=db)
    return {"zone_id": zone.zone_id, "message": "Zone created"}


@router.delete("/zones/{zone_id}")
async def delete_zone(
    zone_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> dict:
    result = await db.execute(select(Zone).where(Zone.zone_id == zone_id))
    zone = result.scalar_one_or_none()
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    zone.is_active = False
    await db.commit()
    await audit_log("zone.deactivated", "zone", zone_id,
                    actor_id=current_user.user_id, actor_role=current_user.role, db=db)
    return {"message": "Zone deactivated"}


# ---------------------------------------------------------------------------
# Tripwires
# ---------------------------------------------------------------------------


@router.get("/tripwires/")
async def list_tripwires(
    camera_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    query = select(Tripwire).where(Tripwire.is_active == True)
    if camera_id:
        query = query.where(Tripwire.camera_id == camera_id)
    result = await db.execute(query)
    return [
        {
            "tripwire_id": t.tripwire_id,
            "camera_id": t.camera_id,
            "name": t.name,
            "point_a": t.point_a,
            "point_b": t.point_b,
            "permitted_direction": t.permitted_direction,
        }
        for t in result.scalars().all()
    ]


@router.post("/tripwires/", status_code=201)
async def create_tripwire(
    body: TripwireCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> dict:
    import uuid
    tw = Tripwire(
        tripwire_id=str(uuid.uuid4()),
        camera_id=body.camera_id,
        name=body.name,
        point_a=body.point_a,
        point_b=body.point_b,
        permitted_direction=body.permitted_direction,
        zone_id=body.zone_id,
    )
    db.add(tw)
    await db.commit()
    await audit_log("tripwire.created", "tripwire", tw.tripwire_id,
                    actor_id=current_user.user_id, actor_role=current_user.role, db=db)
    return {"tripwire_id": tw.tripwire_id, "message": "Tripwire created"}


# ---------------------------------------------------------------------------
# Personnel
# ---------------------------------------------------------------------------


@router.get("/personnel/")
async def list_personnel(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "supervisor")),
) -> List[dict]:
    result = await db.execute(select(Personnel).order_by(Personnel.name))
    return [
        {
            "person_id": p.person_id,
            "name": p.name,
            "designation": p.designation,
            "authorization_level": p.authorization_level,
            "enrolled_at": p.enrolled_at.isoformat() if p.enrolled_at else None,
        }
        for p in result.scalars().all()
    ]


@router.post("/personnel/", status_code=201)
async def enroll_personnel(
    name: str,
    designation: str,
    authorization_level: int,
    face_image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> dict:
    """Enroll an authorized person with face image."""
    import uuid
    import numpy as np
    import cv2
    from backend.core.perception.face_engine import get_face_engine

    raw = await face_image.read()
    nparr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    face_engine = get_face_engine()
    detections = face_engine.detect(img)
    if not detections:
        raise HTTPException(status_code=422, detail="No face detected in uploaded image")

    embedding = face_engine.embed(img[
        detections[0].y1:detections[0].y2,
        detections[0].x1:detections[0].x2
    ])

    person = Personnel(
        person_id=str(uuid.uuid4()),
        name=name,
        designation=designation,
        authorization_level=authorization_level,
        face_embedding=embedding.tobytes() if embedding is not None else None,
        embedding_version="v1.0",
        enrolled_by=current_user.user_id,
    )
    db.add(person)
    await db.commit()

    await audit_log("personnel.enrolled", "personnel", person.person_id,
                    actor_id=current_user.user_id, actor_role=current_user.role, db=db)
    return {"person_id": person.person_id, "message": "Personnel enrolled"}


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------


@router.post("/watchlist/", status_code=201)
async def add_to_watchlist(
    label: str,
    notes: str = "",
    face_image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> dict:
    import uuid
    import numpy as np
    import cv2
    from backend.core.perception.face_engine import get_face_engine

    raw = await face_image.read()
    nparr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    face_engine = get_face_engine()
    detections = face_engine.detect(img)
    embedding = None
    if detections:
        embedding = face_engine.embed(img[
            detections[0].y1:detections[0].y2,
            detections[0].x1:detections[0].x2
        ])

    entry = Watchlist(
        watchlist_id=str(uuid.uuid4()),
        label=label,
        face_embedding=embedding.tobytes() if embedding is not None else None,
        embedding_version="v1.0",
        notes=notes,
        added_by=current_user.user_id,
    )
    db.add(entry)
    await db.commit()

    await audit_log("watchlist.entry_added", "watchlist", entry.watchlist_id,
                    actor_id=current_user.user_id, actor_role=current_user.role, db=db)
    return {"watchlist_id": entry.watchlist_id, "message": "Watchlist entry added"}


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


@router.get("/audit-log/")
async def get_audit_log(
    action_type: Optional[str] = None,
    actor_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "auditor")),
) -> List[dict]:
    """Paginated audit log - admin and auditor roles only."""
    query = select(AuditAction).order_by(desc(AuditAction.timestamp)).limit(limit).offset(offset)
    if action_type:
        query = query.where(AuditAction.action_type == action_type)
    if actor_id:
        query = query.where(AuditAction.actor_id == actor_id)

    result = await db.execute(query)
    records = result.scalars().all()

    return [
        {
            "action_id": r.action_id,
            "timestamp": r.timestamp.isoformat(),
            "action_type": r.action_type,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "actor_id": r.actor_id,
            "actor_role": r.actor_role,
            "ip_address": r.ip_address,
            "before_state": r.before_state,
            "after_state": r.after_state,
        }
        for r in records
    ]


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------


@router.get("/model-registry/")
async def list_model_versions(
    model_name: Optional[str] = None,
    current_user: User = Depends(require_role("admin")),
) -> List[dict]:
    registry = get_registry()
    return [v.to_dict() for v in registry.list_versions(model_name)]


@router.post("/model-registry/deprecate")
async def deprecate_model_version(
    body: ModelDeprecateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> dict:
    registry = get_registry()
    success = registry.deprecate_version(
        body.model_name, body.version, body.reason, deprecated_by=current_user.user_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Model version not found")
    await audit_log(
        "model.deprecated", "model_version", f"{body.model_name}:{body.version}",
        actor_id=current_user.user_id, actor_role=current_user.role,
        after_state={"reason": body.reason}, db=db,
    )
    return {"message": f"Model {body.model_name} v{body.version} deprecated"}


# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------


@router.get("/topology/")
async def get_topology(
    current_user: User = Depends(get_current_user),
) -> dict:
    from backend.core.correlation.graph import get_topology_graph
    return get_topology_graph().to_dict()
