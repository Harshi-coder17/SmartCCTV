"""
SmartCCTV SIH26187 — JWT RS256 Authentication.

Complete implementation of RS256 JWT access/refresh token lifecycle with
bcrypt password hashing, in-memory JTI revocation set, and persistent
refresh token storage.
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional, Set

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password Hashing
# ---------------------------------------------------------------------------


def get_password_hash(password: str) -> str:
    """Hash a plain-text password with bcrypt."""
    pw_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a stored bcrypt hash."""
    try:
        pw_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pw_bytes, hash_bytes)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# RSA Key Loading / Generation
# ---------------------------------------------------------------------------

_private_key_pem: Optional[bytes] = None
_public_key_pem: Optional[bytes] = None


def load_or_generate_rsa_keypair() -> tuple[bytes, bytes]:
    """Load the RS256 key pair from disk, generating them if absent.

    Returns:
        Tuple of (private_key_pem_bytes, public_key_pem_bytes).
    """
    global _private_key_pem, _public_key_pem

    priv_path = Path(settings.SECRET_KEY)
    pub_path = Path(settings.PUBLIC_KEY_PATH)

    if not priv_path.exists() or not pub_path.exists():
        logger.info("RSA key pair not found — generating 2048-bit keys at %s", priv_path)
        priv_path.parent.mkdir(parents=True, exist_ok=True)
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )
        priv_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pub_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        priv_path.write_bytes(priv_pem)
        pub_path.write_bytes(pub_pem)
        logger.info("RSA key pair written successfully.")
    else:
        priv_pem = priv_path.read_bytes()
        pub_pem = pub_path.read_bytes()

    _private_key_pem = priv_pem
    _public_key_pem = pub_pem
    return priv_pem, pub_pem


def _get_private_key() -> bytes:
    """Return the private key PEM bytes, loading from disk if needed."""
    if _private_key_pem is None:
        load_or_generate_rsa_keypair()
    assert _private_key_pem is not None
    return _private_key_pem


def _get_public_key() -> bytes:
    """Return the public key PEM bytes, loading from disk if needed."""
    if _public_key_pem is None:
        load_or_generate_rsa_keypair()
    assert _public_key_pem is not None
    return _public_key_pem


# ---------------------------------------------------------------------------
# In-Memory JTI Revocation Set (access tokens)
# ---------------------------------------------------------------------------

_revoked_jtis: Set[str] = set()


def revoke_access_token(jti: str) -> None:
    """Add a JTI to the in-memory revocation set.

    Note: This set is ephemeral — on restart, already-expired tokens will
    not be re-added.  For long-lived tokens or multi-instance deployments,
    move to a Redis set.
    """
    _revoked_jtis.add(jti)
    logger.info("Access token JTI revoked: %s", jti)


def is_access_token_revoked(jti: str) -> bool:
    """Return True if the given JTI has been revoked."""
    return jti in _revoked_jtis


# ---------------------------------------------------------------------------
# Access Token
# ---------------------------------------------------------------------------


def create_access_token(
    data: Dict[str, object],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed RS256 JWT access token.

    Args:
        data:          Payload claims to embed (e.g. sub, role).
        expires_delta: Override default expiry.

    Returns:
        Signed JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    jti = str(uuid.uuid4())
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "jti": jti})
    return jwt.encode(to_encode, _get_private_key(), algorithm=settings.JWT_ALGORITHM)


def verify_access_token(token: str) -> Dict[str, object]:
    """Decode and validate an RS256 JWT access token.

    Args:
        token: Raw JWT string.

    Returns:
        Decoded payload dict.

    Raises:
        JWTError: On invalid signature, expiry, or revocation.
    """
    try:
        payload: Dict[str, object] = jwt.decode(
            token, _get_public_key(), algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError as exc:
        raise JWTError(f"Token validation failed: {exc}") from exc

    jti = str(payload.get("jti", ""))
    if is_access_token_revoked(jti):
        raise JWTError("Token has been revoked.")

    return payload


# ---------------------------------------------------------------------------
# Refresh Token
# ---------------------------------------------------------------------------


def _hash_token(raw_token: str) -> str:
    """SHA-256 hash of a raw refresh token string."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


async def create_refresh_token(user_id: str, db: AsyncSession) -> str:
    """Generate a secure refresh token and persist its hash.

    Args:
        user_id: The user this token belongs to.
        db:      Async DB session.

    Returns:
        The raw (unhashed) refresh token string — send to client once.
    """
    from backend.models.audit import RefreshToken  # avoid circular import

    raw_token = os.urandom(64).hex()
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )

    db_token = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(db_token)
    await db.flush()
    return raw_token


async def verify_refresh_token(raw_token: str, db: AsyncSession) -> "User":  # type: ignore[name-defined]
    """Verify a raw refresh token, returning the owning User.

    Args:
        raw_token: The token string received from the client.
        db:        Async DB session.

    Returns:
        The User associated with this token.

    Raises:
        ValueError: If token not found, revoked, or expired.
    """
    from backend.models.audit import RefreshToken
    from backend.models.user import User

    token_hash = _hash_token(raw_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    db_token = result.scalar_one_or_none()

    if db_token is None:
        raise ValueError("Refresh token not found.")
    if db_token.revoked_at is not None:
        raise ValueError("Refresh token has been revoked.")
    if db_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise ValueError("Refresh token has expired.")

    user_result = await db.execute(
        select(User).where(User.user_id == db_token.user_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise ValueError("Associated user not found or inactive.")

    return user


async def revoke_refresh_token(token_hash: str, db: AsyncSession) -> None:
    """Mark a single refresh token as revoked.

    Args:
        token_hash: SHA-256 hex hash of the raw token.
        db:         Async DB session.
    """
    from backend.models.audit import RefreshToken

    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await db.flush()


async def revoke_all_user_tokens(user_id: str, db: AsyncSession) -> None:
    """Revoke every active refresh token for a user (password change / compromise).

    Args:
        user_id: The user whose tokens should all be revoked.
        db:      Async DB session.
    """
    from backend.models.audit import RefreshToken

    await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await db.flush()
    logger.info("All refresh tokens revoked for user %s", user_id)
