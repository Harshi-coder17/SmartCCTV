"""
SmartCCTV SIH26187 - Structured Audit Logging.

Every operator action, API call, and system event is persisted to:
  1. An append-only JSON-lines file (AUDIT_LOG_PATH).
  2. The AuditAction database table.

structlog is used for all logging: JSON renderer in production,
pretty-printed in development.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog
from structlog.types import FilteringBoundLogger

from backend.config import get_settings

settings = get_settings()


# ---------------------------------------------------------------------------
# structlog setup
# ---------------------------------------------------------------------------


def setup_logging() -> None:
    """Configure structlog for the process. Call once at application startup."""
    is_dev = os.getenv("ENV", "development") == "development"

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if is_dev:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            structlog.stdlib.NAME_TO_LEVEL.get("INFO", 20)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "smartcctv") -> FilteringBoundLogger:
    """Return a bound structlog logger for the given module name."""
    return structlog.get_logger(name)


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


def _append_audit_line(record: dict) -> None:
    """Append a JSON record to the append-only audit log file."""
    log_path = settings.AUDIT_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


async def audit_log(
    action_type: str,
    target_type: str,
    target_id: str,
    *,
    actor_id: Optional[str] = None,
    actor_role: Optional[str] = None,
    before_state: Optional[Any] = None,
    after_state: Optional[Any] = None,
    ip_address: Optional[str] = None,
    session_id: Optional[str] = None,
    db=None,
    extra: Optional[dict] = None,
) -> None:
    """
    Record an audit action to both the log file and the database.

    Parameters
    ----------
    action_type : str
        Human-readable action, e.g. 'alert.disposition', 'zone.create', 'user.login'.
    target_type : str
        Entity type, e.g. 'alert', 'zone', 'camera', 'user'.
    target_id : str
        Primary key of the affected entity.
    actor_id : str, optional
        User ID of the actor (None for system actions).
    actor_role : str, optional
        Role of the actor at the time of the action.
    before_state : Any, optional
        Snapshot of entity state before the change.
    after_state : Any, optional
        Snapshot of entity state after the change.
    ip_address : str, optional
        Remote IP address of the requesting client.
    session_id : str, optional
        Session or JWT JTI for correlation.
    db : AsyncSession, optional
        If provided, also persists the record to the AuditAction table.
    extra : dict, optional
        Additional arbitrary key-value context.
    """
    import uuid

    record = {
        "action_id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "action_type": action_type,
        "target_type": target_type,
        "target_id": target_id,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "ip_address": ip_address,
        "session_id": session_id,
        "before_state": before_state,
        "after_state": after_state,
        **(extra or {}),
    }

    # Always write to file (synchronous, cheap)
    _append_audit_line(record)

    # Persist to DB when a session is provided
    if db is not None:
        from backend.models.audit import AuditAction

        entry = AuditAction(
            action_id=record["action_id"],
            actor_id=actor_id,
            actor_role=actor_role or "",
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address or "",
            session_id=session_id or "",
        )
        db.add(entry)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            structlog.get_logger().warning(
                "audit_db_write_failed",
                action_type=action_type,
                target_id=target_id,
            )


class AuditMiddleware:
    """
    FastAPI middleware that automatically logs every HTTP request
    to the structured audit trail.

    Attaches actor identity (from JWT) and remote IP to the log record.
    Does NOT log request/response bodies to avoid data leakage.
    """

    def __init__(self, app) -> None:
        self._app = app
        self._log = structlog.get_logger("audit.middleware")

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        from starlette.requests import Request
        from starlette.responses import Response

        request = Request(scope, receive)
        method = request.method
        path = request.url.path

        # Skip noisy health/metrics/static endpoints
        if path in ("/health", "/metrics", "/docs", "/openapi.json", "/redoc"):
            await self._app(scope, receive, send)
            return

        status_code = 500
        actor_id: Optional[str] = None

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self._app(scope, receive, send_wrapper)
        finally:
            # Best-effort: extract actor from request state if auth middleware set it
            actor_id = getattr(request.state, "user_id", None)
            actor_role = getattr(request.state, "user_role", None)

            self._log.info(
                "http_request",
                method=method,
                path=path,
                status=status_code,
                actor_id=actor_id,
                actor_role=actor_role,
                ip=request.client.host if request.client else None,
            )
