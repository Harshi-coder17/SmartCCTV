"""
SmartCCTV SIH26187 — Audit, HashLedgerEntry, RefreshToken ORM Models.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from backend.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# RefreshToken
# ---------------------------------------------------------------------------


class RefreshToken(Base):
    """Persisted refresh token record (stores SHA-256 hash of the raw token)."""

    __tablename__ = "refresh_tokens"

    token_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    # Relationships
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", back_populates="refresh_tokens"
    )


# ---------------------------------------------------------------------------
# HashLedgerEntry
# ---------------------------------------------------------------------------


class HashLedgerEntry(Base):
    """Append-only SHA-256 hash chain entry for evidence integrity.

    chain_hash = SHA-256(file_hash || prev_chain_hash).
    Verification replays this computation over all entries.
    """

    __tablename__ = "hash_ledger"

    entry_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entry_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 hex
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # previous chain_hash
    chain_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256(file+prev)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


# ---------------------------------------------------------------------------
# AuditAction
# ---------------------------------------------------------------------------


class AuditAction(Base):
    """Immutable audit trail entry recording every sensitive system action."""

    __tablename__ = "audit_actions"

    action_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.user_id"), nullable=True, index=True
    )
    actor_role: Mapped[str] = mapped_column(String(16), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    before_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    after_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Relationships
    actor: Mapped[Optional["User"]] = relationship(  # type: ignore[name-defined]
        "User", back_populates="audit_actions", foreign_keys=[actor_id]
    )
