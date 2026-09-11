"""
SmartCCTV SIH26187 — ORM Models Package.

Importing this package registers all models with SQLAlchemy's declarative
Base so that `Base.metadata.create_all()` sees every table.
"""

from backend.models.camera import Camera, CameraHealth, Tripwire, Zone  # noqa: F401
from backend.models.event import Alert, Event  # noqa: F401
from backend.models.track import GlobalIdentity, Observation, Track  # noqa: F401
from backend.models.audit import (  # noqa: F401
    AuditAction,
    HashLedgerEntry,
    RefreshToken,
)
from backend.models.user import Personnel, User, Watchlist  # noqa: F401
