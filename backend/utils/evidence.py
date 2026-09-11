"""
SmartCCTV SIH26187 - Evidence Builder.

Extracts pre/post-event clips from the in-memory ring buffer,
encrypts them with AES-256-GCM, records SHA-256 hashes in the
append-only ledger, and returns a fully-populated EvidencePackage.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.security.crypto import encrypt_file, compute_sha256
from backend.security.hash_ledger import get_ledger, LedgerEntry

log = structlog.get_logger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BufferedFrame:
    """A single frame stored in the rolling evidence ring buffer."""

    frame_number: int
    timestamp: float  # Unix epoch seconds
    frame: np.ndarray  # BGR image array


@dataclass
class EvidencePackage:
    """Complete evidence bundle for one event."""

    event_id: str
    camera_id: str
    pre_clip_path: Optional[Path] = None
    post_clip_path: Optional[Path] = None
    snapshot_path: Optional[Path] = None
    pre_clip_hash: Optional[str] = None
    post_clip_hash: Optional[str] = None
    snapshot_hash: Optional[str] = None
    model_versions: Dict[str, str] = field(default_factory=dict)
    rule_version: str = "v1.0"
    calibration_version: str = "v1.0"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    ledger_entry_ids: List[str] = field(default_factory=list)

    def to_manifest(self) -> Dict[str, Any]:
        """Serialise to JSON-safe dict for storage in the events table."""
        return {
            "event_id": self.event_id,
            "camera_id": self.camera_id,
            "pre_clip": str(self.pre_clip_path) if self.pre_clip_path else None,
            "post_clip": str(self.post_clip_path) if self.post_clip_path else None,
            "snapshot": str(self.snapshot_path) if self.snapshot_path else None,
            "hashes": {
                "pre_clip": self.pre_clip_hash,
                "post_clip": self.post_clip_hash,
                "snapshot": self.snapshot_hash,
            },
            "model_versions": self.model_versions,
            "rule_version": self.rule_version,
            "calibration_version": self.calibration_version,
            "created_at": self.created_at,
            "ledger_entries": self.ledger_entry_ids,
        }


# ---------------------------------------------------------------------------
# Evidence ring buffer (per camera, held in StreamWorker)
# ---------------------------------------------------------------------------


class EvidenceRingBuffer:
    """
    Rolling circular buffer of raw video frames for one camera.

    Capacity: (pre_event_secs + post_event_secs) * target_fps frames.
    When full, oldest frames are dropped automatically (deque maxlen).
    """

    def __init__(self, pre_secs: int, post_secs: int, fps: int = 30) -> None:
        self.pre_secs = pre_secs
        self.post_secs = post_secs
        self.fps = fps
        capacity = (pre_secs + post_secs) * fps
        self._buf: Deque[BufferedFrame] = deque(maxlen=capacity)

    def push(self, frame_number: int, frame: np.ndarray) -> None:
        self._buf.append(BufferedFrame(frame_number, time.time(), frame.copy()))

    def get_pre_event(self, event_ts: float) -> List[BufferedFrame]:
        """Frames from (event_ts - pre_secs) to event_ts."""
        cutoff = event_ts - self.pre_secs
        return [f for f in self._buf if cutoff <= f.timestamp <= event_ts]

    def get_post_event(self, event_ts: float) -> List[BufferedFrame]:
        """Frames from event_ts to (event_ts + post_secs)."""
        cutoff = event_ts + self.post_secs
        return [f for f in self._buf if event_ts <= f.timestamp <= cutoff]

    def get_snapshot_frame(self, event_ts: float) -> Optional[BufferedFrame]:
        """Frame closest to the event timestamp."""
        if not self._buf:
            return None
        return min(self._buf, key=lambda f: abs(f.timestamp - event_ts))


# ---------------------------------------------------------------------------
# Evidence Builder
# ---------------------------------------------------------------------------


class EvidenceBuilder:
    """
    Constructs evidence packages from ring buffer frames.

    Each clip is:
      1. Written as a raw MP4 to a temp path.
      2. Encrypted with AES-256-GCM and saved under evidence/{event_id}/.
      3. SHA-256 hash recorded in the append-only ledger.
    """

    def __init__(self) -> None:
        self._evidence_dir = settings.EVIDENCE_DIR
        self._evidence_dir.mkdir(parents=True, exist_ok=True)

    async def create_package(
        self,
        event_id: str,
        camera_id: str,
        event_timestamp: float,
        ring_buffer: EvidenceRingBuffer,
        model_versions: Dict[str, str],
        rule_version: str = "v1.0",
        calibration_version: str = "v1.0",
    ) -> EvidencePackage:
        """
        Build a complete EvidencePackage for the given event.
        """
        pkg = EvidencePackage(
            event_id=event_id,
            camera_id=camera_id,
            model_versions=model_versions,
            rule_version=rule_version,
            calibration_version=calibration_version,
        )

        event_dir = self._evidence_dir / event_id
        event_dir.mkdir(parents=True, exist_ok=True)

        ledger = get_ledger()

        # Snapshot
        snap_frame = ring_buffer.get_snapshot_frame(event_timestamp)
        if snap_frame is not None:
            snap_path = event_dir / "snapshot.jpg"
            cv2.imwrite(str(snap_path), snap_frame.frame)
            snap_hash = compute_sha256(snap_path)
            enc_snap = event_dir / "snapshot.jpg.enc"
            encrypt_file(snap_path, enc_snap)
            snap_path.unlink(missing_ok=True)  # remove plaintext
            entry_id = await ledger.append(
                LedgerEntry(
                    evidence_type="snapshot",
                    reference_id=event_id,
                    file_hash=snap_hash,
                )
            )
            pkg.snapshot_path = enc_snap
            pkg.snapshot_hash = snap_hash
            pkg.ledger_entry_ids.append(entry_id)

        # Pre-event clip
        pre_frames = ring_buffer.get_pre_event(event_timestamp)
        if pre_frames:
            pre_path = self._write_clip(pre_frames, event_dir / "pre_event.mp4", ring_buffer.fps)
            if pre_path:
                pre_hash = compute_sha256(pre_path)
                enc_pre = event_dir / "pre_event.mp4.enc"
                encrypt_file(pre_path, enc_pre)
                pre_path.unlink(missing_ok=True)
                entry_id = await ledger.append(
                    LedgerEntry(
                        evidence_type="pre_event_clip",
                        reference_id=event_id,
                        file_hash=pre_hash,
                    )
                )
                pkg.pre_clip_path = enc_pre
                pkg.pre_clip_hash = pre_hash
                pkg.ledger_entry_ids.append(entry_id)

        # Post-event clip (may not be available yet for real-time events)
        post_frames = ring_buffer.get_post_event(event_timestamp)
        if post_frames:
            post_path = self._write_clip(post_frames, event_dir / "post_event.mp4", ring_buffer.fps)
            if post_path:
                post_hash = compute_sha256(post_path)
                enc_post = event_dir / "post_event.mp4.enc"
                encrypt_file(post_path, enc_post)
                post_path.unlink(missing_ok=True)
                entry_id = await ledger.append(
                    LedgerEntry(
                        evidence_type="post_event_clip",
                        reference_id=event_id,
                        file_hash=post_hash,
                    )
                )
                pkg.post_clip_path = enc_post
                pkg.post_clip_hash = post_hash
                pkg.ledger_entry_ids.append(entry_id)

        log.info(
            "evidence_package_created",
            event_id=event_id,
            camera_id=camera_id,
            files=len(pkg.ledger_entry_ids),
        )
        return pkg

    @staticmethod
    def _write_clip(frames: List[BufferedFrame], out_path: Path, fps: int) -> Optional[Path]:
        """Write a list of BufferedFrames to an MP4 file. Returns path or None."""
        if not frames:
            return None
        h, w = frames[0].frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))
        for bf in frames:
            writer.write(bf.frame)
        writer.release()
        return out_path if out_path.exists() else None

    async def verify_package(
        self,
        event_id: str,
    ) -> Dict[str, Any]:
        """
        Re-compute SHA-256 for all evidence files and check against ledger.
        Returns a verification report dict.
        """
        from backend.security.hash_ledger import get_ledger

        ledger = get_ledger()
        event_dir = self._evidence_dir / event_id
        if not event_dir.exists():
            return {"verified": False, "reason": "Evidence directory not found"}

        report: Dict[str, Any] = {"event_id": event_id, "files": {}, "chain_valid": False}

        for enc_file in event_dir.glob("*.enc"):
            ledger_entry = await ledger.get_entry(event_id)
            if ledger_entry is None:
                report["files"][enc_file.name] = "no_ledger_entry"
                continue
            # We can only verify the hash of the encrypted file matches what was stored
            current_hash = compute_sha256(enc_file)
            report["files"][enc_file.name] = "match" if current_hash == ledger_entry.file_hash else "MISMATCH"

        report["chain_valid"] = await ledger.verify_chain()
        report["verified"] = all(v == "match" for v in report["files"].values()) and report["chain_valid"]
        return report
