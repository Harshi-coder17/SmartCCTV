"""
SmartCCTV SIH26187 - FastAPI Application Entry Point.

Wires together all layers:
  - Database initialisation
  - Structured logging
  - Stream manager (multi-camera perception pipeline)
  - All REST routers
  - WebSocket alert feed
  - Health and metrics endpoints
  - Security middleware
"""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from backend.database import init_db
from backend.utils.logger import setup_logging, AuditMiddleware

log = structlog.get_logger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Application lifespan (startup + shutdown)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    # ── Startup ──────────────────────────────────────────────────────────────
    setup_logging()
    log.info("smartcctv_starting", version="1.0.0")

    # Ensure required directories exist
    settings.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    settings.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    settings.HASH_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    Path("./logs").mkdir(exist_ok=True)
    Path("./keys").mkdir(exist_ok=True)

    # Generate RSA keys if not present
    settings.generate_rsa_keys()

    # Initialise database (create all tables)
    await init_db()
    log.info("database_ready")

    # Initialise SHA-256 hash ledger
    from backend.security.hash_ledger import init_ledger
    await init_ledger(str(settings.HASH_LEDGER_PATH))
    log.info("hash_ledger_ready")

    # Initialise model registry
    from backend.utils.model_registry import init_registry
    registry = init_registry(Path("./logs/model_registry.json"))
    # Register YOLO model if weights file present
    yolo_path = settings.MODELS_DIR / settings.YOLO_MODEL
    if not yolo_path.exists():
        # Try project root
        yolo_path = Path(settings.YOLO_MODEL)
    if yolo_path.exists():
        if not registry.get_current_version("detector"):
            registry.register_model("detector", "v1.0-yolov8n", str(yolo_path), "yolo")
    log.info("model_registry_ready")

    # Initialise topology graph
    from backend.core.correlation.graph import init_topology
    cameras_json = Path("./data/cameras.json")
    if cameras_json.exists():
        init_topology(cameras_json)
        log.info("topology_graph_ready")

    # Start face engine (loads FAISS indices from disk if present)
    from backend.core.perception.face_engine import get_face_engine
    face_engine = get_face_engine()
    log.info("face_engine_ready", backend=settings.FACE_BACKEND)

    # Start stream manager (launches one asyncio worker per active camera)
    from backend.core.stream_manager import get_stream_manager
    manager = get_stream_manager()
    await manager.start()
    log.info("stream_manager_started")

    log.info("smartcctv_ready", api_port=settings.API_PORT)

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    log.info("smartcctv_shutting_down")
    await manager.stop()
    log.info("stream_manager_stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


app = FastAPI(
    title="SmartCCTV - Border Intelligence Platform",
    description=(
        "SIH26187: Software-Defined Border Video Intelligence Platform. "
        "AI-Based Intelligent Video Analytics for Border Surveillance."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Audit middleware ───────────────────────────────────────────────────────────
app.add_middleware(AuditMiddleware)


# ── Routers ───────────────────────────────────────────────────────────────────
from backend.api.auth import router as auth_router
from backend.api.cameras import router as cameras_router
from backend.api.events import router as events_router
from backend.api.alerts import router as alerts_router
from backend.api.evidence import router as evidence_router
from backend.api.admin import router as admin_router

app.include_router(auth_router)
app.include_router(cameras_router)
app.include_router(events_router)
app.include_router(alerts_router)
app.include_router(evidence_router)
app.include_router(admin_router)


# ── Static file serving (evidence snapshots - auth-gated via API) ─────────────
# Raw evidence files are served only through the /evidence/ API (decrypted on demand)


# ---------------------------------------------------------------------------
# Health and Metrics endpoints
# ---------------------------------------------------------------------------


@app.get("/health", tags=["System"])
async def health_check() -> Dict[str, Any]:
    """System health check - returns component statuses."""
    from backend.core.stream_manager import get_stream_manager
    from backend.database import get_engine

    manager = get_stream_manager()
    camera_statuses = manager.get_camera_statuses()

    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "components": {
            "database": "ok",
            "stream_manager": "ok" if manager.is_running else "stopped",
            "cameras_active": sum(1 for s in camera_statuses.values() if s == "running"),
            "cameras_total": len(camera_statuses),
            "face_backend": settings.FACE_BACKEND,
            "gpu_enabled": settings.USE_GPU,
        },
    }


@app.get("/metrics", tags=["System"])
async def metrics(
    request: Request,
) -> Dict[str, Any]:
    """Basic operational metrics."""
    from backend.database import AsyncSessionLocal
    from backend.models.event import Event, Alert
    from sqlalchemy import select, func
    from datetime import timedelta

    async with AsyncSessionLocal() as db:
        # Events in last 24h
        since = datetime.utcnow() - timedelta(hours=24)
        event_count = await db.scalar(
            select(func.count(Event.event_id)).where(Event.timestamp >= since)
        )
        # False positive rate
        total_disposed = await db.scalar(
            select(func.count(Alert.alert_id)).where(
                Alert.disposition != "pending"
            )
        )
        false_positives = await db.scalar(
            select(func.count(Alert.alert_id)).where(
                Alert.disposition == "false_positive"
            )
        )
        fp_rate = round(false_positives / max(total_disposed, 1) * 100, 1)

        # Active open alerts
        open_alerts = await db.scalar(
            select(func.count(Alert.alert_id)).where(Alert.disposition == "pending")
        )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "events_last_24h": event_count or 0,
        "open_alerts": open_alerts or 0,
        "false_positive_rate_pct": fp_rate,
        "total_disposed": total_disposed or 0,
    }


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return structured validation errors without leaking stack traces."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "body": str(exc.body)[:200]},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log the error, return generic response (no stack trace to client)."""
    log.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal error occurred. The incident has been logged."},
    )
