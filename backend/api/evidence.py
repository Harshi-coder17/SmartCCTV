"""
SmartCCTV SIH26187 - Evidence API.

Serves AES-256-GCM encrypted evidence files (decrypted on demand),
SHA-256 hash verification against the ledger, and evidence manifests.
All access is logged to the audit trail.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database import get_db
from backend.models.event import Event
from backend.models.user import User
from backend.security.crypto import decrypt_file_to_bytes
from backend.security.rbac import get_current_user
from backend.utils.evidence import EvidenceBuilder
from backend.utils.logger import audit_log

router = APIRouter(prefix="/evidence", tags=["Evidence"])
settings = get_settings()
_builder = EvidenceBuilder()


@router.get("/{event_id}/package")
async def get_evidence_manifest(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return the evidence manifest for an event (no binary data, just metadata)."""
    result = await db.execute(select(Event).where(Event.event_id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    await audit_log(
        "evidence.manifest_accessed", "event", event_id,
        actor_id=current_user.user_id, actor_role=current_user.role, db=db,
    )

    return {
        "event_id": event_id,
        "evidence": event.evidence_manifest or {},
        "model_versions": event.model_versions or {},
        "rule_version": event.rule_version,
        "calibration_version": event.calibration_version,
        "timestamp": event.timestamp.isoformat(),
    }


@router.get("/{event_id}/clip/{clip_type}")
async def get_evidence_clip(
    event_id: str,
    clip_type: str,  # 'pre' | 'post'
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Stream decrypted evidence clip (pre_event or post_event).
    Access is logged to the audit trail.
    """
    if clip_type not in ("pre", "post"):
        raise HTTPException(status_code=400, detail="clip_type must be 'pre' or 'post'")

    result = await db.execute(select(Event).where(Event.event_id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    manifest = event.evidence_manifest or {}
    clip_key = "pre_clip" if clip_type == "pre" else "post_clip"
    clip_path = manifest.get(clip_key)

    if not clip_path or not Path(clip_path).exists():
        raise HTTPException(status_code=404, detail="Clip not available")

    await audit_log(
        f"evidence.clip_accessed.{clip_type}", "event", event_id,
        actor_id=current_user.user_id, actor_role=current_user.role, db=db,
    )

    # Decrypt and stream
    decrypted = decrypt_file_to_bytes(Path(clip_path))

    return StreamingResponse(
        io.BytesIO(decrypted),
        media_type="video/mp4",
        headers={"Content-Disposition": f"inline; filename={event_id}_{clip_type}.mp4"},
    )


@router.get("/{event_id}/snapshot")
async def get_evidence_snapshot(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Serve decrypted snapshot image for quick review."""
    result = await db.execute(select(Event).where(Event.event_id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    manifest = event.evidence_manifest or {}
    snap_path = manifest.get("snapshot")

    if not snap_path or not Path(snap_path).exists():
        raise HTTPException(status_code=404, detail="Snapshot not available")

    await audit_log(
        "evidence.snapshot_accessed", "event", event_id,
        actor_id=current_user.user_id, actor_role=current_user.role, db=db,
    )

    decrypted = decrypt_file_to_bytes(Path(snap_path))
    return Response(content=decrypted, media_type="image/jpeg")


@router.get("/{event_id}/verify")
async def verify_evidence_integrity(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Recompute SHA-256 hashes and verify against the ledger.
    Returns a detailed verification report per evidence file.
    """
    await audit_log(
        "evidence.integrity_verified", "event", event_id,
        actor_id=current_user.user_id, actor_role=current_user.role, db=db,
    )
    return await _builder.verify_package(event_id)
