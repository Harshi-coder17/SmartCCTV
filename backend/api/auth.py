"""
SmartCCTV SIH26187 - Authentication API Routes.

Implements JWT RS256 login/refresh/logout with httpOnly cookie delivery,
rate-limiting on login, and RBAC-gated password change.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.user import User
from backend.security.auth import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    revoke_access_token,
    revoke_all_user_tokens,
    verify_access_token,
    verify_password,
    verify_refresh_token,
)
from backend.security.rbac import get_current_user
from backend.utils.logger import audit_log

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Simple in-memory rate limiter: {ip: [timestamp, ...]}
_login_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_WINDOW_SECS = 300   # 5 minutes
_MAX_ATTEMPTS = 10


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    window_start = now - _RATE_WINDOW_SECS
    attempts = [t for t in _login_attempts[ip] if t > window_start]
    _login_attempts[ip] = attempts
    if len(attempts) >= _MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )
    _login_attempts[ip].append(now)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserResponse(BaseModel):
    user_id: str
    username: str
    role: str
    last_login: Optional[datetime]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/login")
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Authenticate user and issue JWT access + refresh tokens via httpOnly cookies."""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(req.password, user.hashed_password):
        await audit_log(
            "user.login_failed",
            "user",
            req.username,
            actor_id=None,
            ip_address=client_ip,
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    access_token = create_access_token({"sub": user.user_id, "role": user.role})
    refresh_token = await create_refresh_token(user.user_id, db)

    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()

    await audit_log(
        "user.login_success",
        "user",
        user.user_id,
        actor_id=user.user_id,
        actor_role=user.role,
        ip_address=client_ip,
        db=db,
    )

    # Deliver tokens as httpOnly cookies (XSS-resistant)
    response.set_cookie(
        "access_token", access_token,
        httponly=True, secure=False, samesite="lax", max_age=3600,
    )
    response.set_cookie(
        "refresh_token", refresh_token,
        httponly=True, secure=False, samesite="lax", max_age=604800,
        path="/auth/refresh",
    )

    return {
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role,
        "message": "Login successful",
    }


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Issue a new access token using the refresh token cookie."""
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    user = await verify_refresh_token(token, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    new_access = create_access_token({"sub": user.user_id, "role": user.role})
    response.set_cookie(
        "access_token", new_access,
        httponly=True, secure=False, samesite="lax", max_age=3600,
    )
    return {"message": "Token refreshed"}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revoke both tokens and clear cookies."""
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            payload = verify_access_token(access_token)
            jti = payload.get("jti")
            if jti:
                revoke_access_token(jti)
        except Exception:
            pass

    refresh_token_val = request.cookies.get("refresh_token")
    if refresh_token_val:
        await revoke_all_user_tokens(current_user.user_id, db)

    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")

    await audit_log("user.logout", "user", current_user.user_id, actor_id=current_user.user_id, db=db)
    return {"message": "Logged out"}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return current user information."""
    return UserResponse(
        user_id=current_user.user_id,
        username=current_user.username,
        role=current_user.role,
        last_login=current_user.last_login,
    )


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Change password and revoke all existing tokens."""
    if not verify_password(req.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password incorrect")

    current_user.hashed_password = get_password_hash(req.new_password)
    await revoke_all_user_tokens(current_user.user_id, db)
    await db.commit()

    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")

    await audit_log(
        "user.password_changed", "user", current_user.user_id,
        actor_id=current_user.user_id, ip_address=request.client.host if request.client else None, db=db,
    )
    return {"message": "Password changed. Please log in again."}
