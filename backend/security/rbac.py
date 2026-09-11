"""
SmartCCTV SIH26187 — Role-Based Access Control (RBAC).

Defines roles, permissions, and FastAPI dependencies for enforcing
least-privilege access across all API endpoints.  Every access check
is logged to the audit trail.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional, Set

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.security.auth import verify_access_token

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Role Enum
# ---------------------------------------------------------------------------


class Role(str, Enum):
    """Hierarchy of user roles from least to most privileged."""

    OPERATOR = "operator"
    SUPERVISOR = "supervisor"
    ADMIN = "admin"
    AUDITOR = "auditor"


# ---------------------------------------------------------------------------
# Permission Enum
# ---------------------------------------------------------------------------


class Permission(str, Enum):
    """Fine-grained permissions checked at the API layer."""

    # Camera management
    CAMERA_VIEW = "camera:view"
    CAMERA_CREATE = "camera:create"
    CAMERA_EDIT = "camera:edit"
    CAMERA_DELETE = "camera:delete"
    CAMERA_STREAM = "camera:stream"
    CAMERA_CALIBRATE = "camera:calibrate"

    # Event access
    EVENT_VIEW = "event:view"
    EVENT_TIMELINE = "event:timeline"

    # Alert management
    ALERT_VIEW = "alert:view"
    ALERT_DISPOSE = "alert:dispose"

    # Evidence
    EVIDENCE_VIEW = "evidence:view"
    EVIDENCE_VERIFY = "evidence:verify"

    # Zone / Tripwire administration
    ZONE_MANAGE = "zone:manage"
    TRIPWIRE_MANAGE = "tripwire:manage"

    # Personnel / Watchlist
    PERSONNEL_VIEW = "personnel:view"
    PERSONNEL_MANAGE = "personnel:manage"
    WATCHLIST_MANAGE = "watchlist:manage"

    # Audit and model registry
    AUDIT_VIEW = "audit:view"
    MODEL_REGISTRY_VIEW = "model_registry:view"
    MODEL_REGISTRY_MANAGE = "model_registry:manage"

    # Topology
    TOPOLOGY_VIEW = "topology:view"
    TOPOLOGY_MANAGE = "topology:manage"

    # User management
    USER_MANAGE = "user:manage"


# ---------------------------------------------------------------------------
# Role → Permission Mapping
# ---------------------------------------------------------------------------

ROLE_PERMISSIONS: dict[Role, Set[Permission]] = {
    Role.OPERATOR: {
        Permission.CAMERA_VIEW,
        Permission.CAMERA_STREAM,
        Permission.EVENT_VIEW,
        Permission.EVENT_TIMELINE,
        Permission.ALERT_VIEW,
        Permission.ALERT_DISPOSE,
        Permission.EVIDENCE_VIEW,
        Permission.PERSONNEL_VIEW,
        Permission.TOPOLOGY_VIEW,
    },
    Role.SUPERVISOR: {
        Permission.CAMERA_VIEW,
        Permission.CAMERA_STREAM,
        Permission.CAMERA_CALIBRATE,
        Permission.EVENT_VIEW,
        Permission.EVENT_TIMELINE,
        Permission.ALERT_VIEW,
        Permission.ALERT_DISPOSE,
        Permission.EVIDENCE_VIEW,
        Permission.EVIDENCE_VERIFY,
        Permission.PERSONNEL_VIEW,
        Permission.TOPOLOGY_VIEW,
        Permission.MODEL_REGISTRY_VIEW,
    },
    Role.ADMIN: {p for p in Permission},  # All permissions
    Role.AUDITOR: {
        Permission.CAMERA_VIEW,
        Permission.EVENT_VIEW,
        Permission.EVENT_TIMELINE,
        Permission.ALERT_VIEW,
        Permission.EVIDENCE_VIEW,
        Permission.EVIDENCE_VERIFY,
        Permission.AUDIT_VIEW,
        Permission.MODEL_REGISTRY_VIEW,
        Permission.PERSONNEL_VIEW,
        Permission.TOPOLOGY_VIEW,
    },
}


def has_permission(role: str, permission: Permission) -> bool:
    """Check if a role includes the requested permission.

    Args:
        role:       Role string from JWT payload.
        permission: Permission to check.

    Returns:
        True if the role grants the permission.
    """
    try:
        role_enum = Role(role)
    except ValueError:
        return False
    return permission in ROLE_PERMISSIONS.get(role_enum, set())


# ---------------------------------------------------------------------------
# Token Extraction Helper
# ---------------------------------------------------------------------------


def _extract_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> Optional[str]:
    """Extract a bearer token from Authorization header or cookie.

    Args:
        request:     The incoming FastAPI request.
        credentials: HTTP Bearer credentials parsed by HTTPBearer.

    Returns:
        Raw token string or None.
    """
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials

    # Fallback: check httpOnly cookie set by /auth/login
    cookie_token = request.cookies.get("access_token")
    return cookie_token


# ---------------------------------------------------------------------------
# get_current_user Dependency
# ---------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> "User":  # type: ignore[name-defined]
    """FastAPI dependency that validates the JWT and returns the User object.

    Args:
        request:     The current HTTP request.
        credentials: Parsed Bearer credentials.
        db:          Async DB session.

    Returns:
        Authenticated User ORM instance.

    Raises:
        HTTPException 401: If token is absent, invalid, or user is inactive.
    """
    from backend.models.user import User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = _extract_token(request, credentials)
    if not token:
        raise credentials_exception

    try:
        payload = verify_access_token(token)
    except JWTError as exc:
        logger.warning("JWT validation failed: %s", exc)
        raise credentials_exception from exc

    user_id: Optional[str] = payload.get("sub")  # type: ignore[assignment]
    if user_id is None:
        raise credentials_exception

    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise credentials_exception

    return user


# ---------------------------------------------------------------------------
# Permission / Role Dependency Factories
# ---------------------------------------------------------------------------


def require_permission(permission: Permission):
    """Return a FastAPI dependency that enforces a specific permission.

    Args:
        permission: The Permission enum value required.

    Returns:
        A FastAPI Depends-compatible coroutine.
    """

    async def _check(
        request: Request,
        current_user: "User" = Depends(get_current_user),  # type: ignore[name-defined]
    ) -> "User":  # type: ignore[name-defined]
        if not has_permission(current_user.role, permission):
            logger.warning(
                "Permission denied: user=%s role=%s required=%s path=%s",
                current_user.user_id,
                current_user.role,
                permission,
                request.url.path,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {permission.value}",
            )
        return current_user

    return _check


def require_role(*roles: "Role | str"):
    """Return a FastAPI dependency that enforces membership in any of the given roles.

    Accepts both Role enum values and plain strings (e.g. 'admin', 'operator').

    Args:
        roles: One or more Role enum values or role name strings.

    Returns:
        A FastAPI Depends-compatible coroutine.
    """
    role_values: set[str] = set()
    for r in roles:
        if isinstance(r, str):
            role_values.add(r)
        else:
            role_values.add(r.value)

    async def _check(
        request: Request,
        current_user: "User" = Depends(get_current_user),  # type: ignore[name-defined]
    ) -> "User":  # type: ignore[name-defined]
        if current_user.role not in role_values:
            logger.warning(
                "Role denied: user=%s role=%s required_one_of=%s",
                current_user.user_id,
                current_user.role,
                role_values,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role(s): {', '.join(role_values)}",
            )
        return current_user

    return _check
