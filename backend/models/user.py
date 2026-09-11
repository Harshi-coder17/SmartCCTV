"""
SmartCCTV SIH26187 — User, Personnel, Watchlist ORM Models.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class User(Base):
    """System operator / supervisor / admin / auditor account."""

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="operator")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(  # type: ignore[name-defined]
        "RefreshToken", back_populates="user"
    )
    enrolled_personnel: Mapped[list["Personnel"]] = relationship(
        "Personnel", back_populates="enrolled_by_user", foreign_keys="Personnel.enrolled_by"
    )
    audit_actions: Mapped[list["AuditAction"]] = relationship(  # type: ignore[name-defined]
        "AuditAction", back_populates="actor", foreign_keys="AuditAction.actor_id"
    )
    alerts_handled: Mapped[list["Alert"]] = relationship(  # type: ignore[name-defined]
        "Alert", back_populates="operator", foreign_keys="Alert.operator_id"
    )


# ---------------------------------------------------------------------------
# Personnel
# ---------------------------------------------------------------------------


class Personnel(Base):
    """Authorised personnel whose face embeddings are enrolled in the system."""

    __tablename__ = "personnel"

    person_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    designation: Mapped[str] = mapped_column(String(128), nullable=True)
    authorization_level: Mapped[int] = mapped_column(Integer, default=1)  # 1–5
    face_embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    embedding_version: Mapped[str] = mapped_column(String(64), default="v1.0")
    enrolled_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    enrolled_by: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.user_id"), nullable=True
    )

    # Relationships
    enrolled_by_user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="enrolled_personnel", foreign_keys=[enrolled_by]
    )
    global_identities: Mapped[list["GlobalIdentity"]] = relationship(  # type: ignore[name-defined]
        "GlobalIdentity",
        back_populates="authorized_person",
        foreign_keys="GlobalIdentity.authorized_person_id",
    )


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------


class Watchlist(Base):
    """Threat watchlist entry with face embedding for matching."""

    __tablename__ = "watchlist"

    watchlist_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    face_embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    embedding_version: Mapped[str] = mapped_column(String(64), default="v1.0")
    added_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    added_by: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.user_id"), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
