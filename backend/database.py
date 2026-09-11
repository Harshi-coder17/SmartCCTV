"""
SmartCCTV SIH26187 — Async Database Engine.

SQLAlchemy 2.x async engine that supports both SQLite (WAL mode) and
PostgreSQL via the same interface. PostgreSQL is preferred when
POSTGRES_URL is configured; SQLite is the default demo backend.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Declarative Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ---------------------------------------------------------------------------
# Engine Factory
# ---------------------------------------------------------------------------


def _build_engine() -> AsyncEngine:
    """Create and configure the async engine.

    SQLite gets WAL mode + busy-timeout for concurrent reads.
    PostgreSQL gets a conservative pool configuration.
    """
    url = settings.effective_database_url()
    is_sqlite = url.startswith("sqlite")

    if is_sqlite:
        engine = create_async_engine(
            url,
            echo=settings.DEBUG,
            connect_args={"check_same_thread": False, "timeout": 30},
            pool_pre_ping=True,
        )

        # Enable WAL mode and set busy_timeout for SQLite concurrency.
        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[union-attr]
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout=5000;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.close()

    else:
        engine = create_async_engine(
            url,
            echo=settings.DEBUG,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
        )

    logger.info("Database engine created", extra={"url": url.split("@")[-1]})
    return engine


engine: AsyncEngine = _build_engine()

# ---------------------------------------------------------------------------
# Session Factory
# ---------------------------------------------------------------------------

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# ---------------------------------------------------------------------------
# FastAPI Dependency
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession; commits on success, rolls back on exception."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Table Initialisation
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create all ORM-mapped tables if they do not already exist.

    Safe to call on every startup (uses CREATE TABLE IF NOT EXISTS).
    """
    # Import models so SQLAlchemy registers them against Base.
    import backend.models  # noqa: F401  — side-effect import

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables initialised successfully.")


async def check_db_connection() -> bool:
    """Probe the database connection. Returns True if reachable."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("Database connectivity check failed: %s", exc)
        return False


def get_engine() -> AsyncEngine:
    """Return the module-level async engine instance."""
    return engine
