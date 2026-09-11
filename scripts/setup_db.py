"""
SmartCCTV SIH26187 - Database Initialisation and Demo Seed Script.

Run once before starting the backend:
    python scripts/setup_db.py

Creates all tables, seeds demo cameras, zones, tripwires,
and creates a default admin user with a randomly generated secure password.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import string
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from backend.config import get_settings
from backend.database import Base
from backend.security.auth import get_password_hash

settings = get_settings()


def generate_secure_password(length: int = 24) -> str:
    """Generate a cryptographically secure random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def main() -> None:
    print("\nSmartCCTV - Database Initialisation")
    print("=" * 50)

    # Ensure keys exist before models import
    settings.generate_rsa_keys()

    # Import all models to register them with Base.metadata
    from backend.models.camera import Camera, Zone, Tripwire, CameraHealth  # noqa
    from backend.models.event import Event, Alert  # noqa
    from backend.models.track import Track, GlobalIdentity, Observation  # noqa
    from backend.models.user import User, Personnel, Watchlist  # noqa
    from backend.models.audit import AuditAction, HashLedgerEntry, RefreshToken  # noqa

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    )

    # Enable WAL mode for SQLite (concurrent readers)
    if "sqlite" in settings.DATABASE_URL:
        from sqlalchemy import event as sa_event, text

        @sa_event.listens_for(engine.sync_engine, "connect")
        def set_wal(dbapi_conn, connection_record):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    print("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("  Tables created.")

    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as db:
        # ── Admin user ──────────────────────────────────────────────────────
        from sqlalchemy import select
        existing_admin = await db.scalar(select(User).where(User.username == "admin"))
        if existing_admin:
            print("  Admin user already exists - skipping.")
        else:
            admin_password = generate_secure_password()
            admin = User(
                user_id=str(uuid.uuid4()),
                username="admin",
                hashed_password=get_password_hash(admin_password),
                role="admin",
                is_active=True,
            )
            db.add(admin)

            # Create demo operator
            op_password = generate_secure_password()
            operator = User(
                user_id=str(uuid.uuid4()),
                username="operator1",
                hashed_password=get_password_hash(op_password),
                role="operator",
                is_active=True,
            )
            db.add(operator)

            await db.flush()
            print(f"\n  {'='*48}")
            print(f"  ADMIN CREDENTIALS - SAVE THESE NOW")
            print(f"  {'='*48}")
            print(f"  Username : admin")
            print(f"  Password : {admin_password}")
            print(f"  {'='*48}")
            print(f"  OPERATOR CREDENTIALS")
            print(f"  Username : operator1")
            print(f"  Password : {op_password}")
            print(f"  {'='*48}\n")

        # ── Demo cameras ────────────────────────────────────────────────────
        cameras_json = Path("./data/cameras.json")
        if cameras_json.exists():
            with open(cameras_json) as fh:
                cameras_data = json.load(fh)

            for cam_data in cameras_data:
                existing = await db.scalar(
                    select(Camera).where(Camera.camera_id == cam_data["camera_id"])
                )
                if existing:
                    continue
                camera = Camera(
                    camera_id=cam_data["camera_id"],
                    name=cam_data["name"],
                    location_name=cam_data["location_name"],
                    gps_lat=cam_data.get("gps_lat", 0.0),
                    gps_lon=cam_data.get("gps_lon", 0.0),
                    rtsp_url=cam_data["rtsp_url"],
                    camera_type=cam_data.get("camera_type", "visible"),
                    expected_fps=cam_data.get("expected_fps", 30),
                    orientation_degrees=cam_data.get("orientation_degrees", 0.0),
                    zone_ids=cam_data.get("zone_ids", []),
                    capability_profile=cam_data.get("capability_profile", {}),
                    health_state="healthy",
                    is_active=True,
                )
                db.add(camera)
            print(f"  Seeded {len(cameras_data)} demo cameras.")

        # ── Demo zones ──────────────────────────────────────────────────────
        zones_json = Path("./data/zones.json")
        if zones_json.exists():
            with open(zones_json) as fh:
                zones_data = json.load(fh)

            for zone_data in zones_data:
                existing = await db.scalar(
                    select(Zone).where(Zone.zone_id == zone_data["zone_id"])
                )
                if existing:
                    continue
                zone = Zone(
                    zone_id=zone_data["zone_id"],
                    name=zone_data["name"],
                    sensitivity_level=zone_data.get("sensitivity_level", 3),
                    polygon_points=zone_data.get("polygon_points", []),
                    camera_ids=zone_data.get("camera_ids", []),
                    allowed_time_start=zone_data.get("allowed_time_start", "00:00"),
                    allowed_time_end=zone_data.get("allowed_time_end", "23:59"),
                    min_authorization_level=zone_data.get("min_authorization_level", 1),
                    loitering_threshold_secs=zone_data.get("loitering_threshold_secs", 30),
                    is_active=True,
                )
                db.add(zone)
            print(f"  Seeded {len(zones_data)} demo zones.")

        # ── Default tripwires ────────────────────────────────────────────────
        existing_tw = await db.scalar(select(Tripwire))
        if not existing_tw:
            # Fence from original config.json
            tw1 = Tripwire(
                tripwire_id=str(uuid.uuid4()),
                camera_id="CAM-01",
                name="Gate Alpha Boundary",
                point_a=[915, 582],
                point_b=[960, 1149],
                permitted_direction="any",
                is_active=True,
            )
            db.add(tw1)
            tw2 = Tripwire(
                tripwire_id=str(uuid.uuid4()),
                camera_id="CAM-02",
                name="Perimeter East Line",
                point_a=[200, 300],
                point_b=[800, 300],
                permitted_direction="outbound",
                is_active=True,
            )
            db.add(tw2)
            print("  Seeded demo tripwires.")

        await db.commit()

    await engine.dispose()
    print("\nDatabase initialisation complete.")
    print("Start the backend with: uvicorn backend.main:app --reload")


if __name__ == "__main__":
    asyncio.run(main())
