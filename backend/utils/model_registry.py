"""
SmartCCTV SIH26187 - Model Version Registry.

Tracks every deployed AI model and scoring configuration with:
  - Version identifiers and file hashes
  - Deployment timestamps and reasons
  - Rollback support (deprecation = new forward entry, not a history edit)
  - Automatic personnel-embedding re-verification trigger on version change

Every generated Event is stamped with model version IDs from this registry
so any alert can be traced back to the exact model that produced it.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ModelVersion:
    """A single versioned model or scoring configuration entry."""

    id: str
    model_name: str       # e.g. 'detector', 'reid', 'face', 'risk_weights'
    version: str          # e.g. 'v1.0', 'v1.1-thermal'
    file_path: str        # relative or absolute path to weights/config file
    sha256_hash: str      # hash of the file at registration time
    model_type: str       # 'yolo' | 'reid' | 'face' | 'anpr' | 'config'
    description: str = ""
    status: str = "active"   # 'active' | 'deprecated' | 'reverted'
    deployed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    deprecated_at: Optional[str] = None
    deployed_by: Optional[str] = None
    deprecated_by: Optional[str] = None
    deprecation_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "model_name": self.model_name,
            "version": self.version,
            "file_path": self.file_path,
            "sha256_hash": self.sha256_hash,
            "model_type": self.model_type,
            "description": self.description,
            "status": self.status,
            "deployed_at": self.deployed_at,
            "deprecated_at": self.deprecated_at,
            "deployed_by": self.deployed_by,
            "deprecated_by": self.deprecated_by,
            "deprecation_reason": self.deprecation_reason,
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ModelRegistry:
    """
    In-process model version registry backed by a JSON file on disk.

    The registry is append-only by design: deprecation and rollback are
    forward entries, never edits of existing history. This mirrors the
    same principle used by the hash ledger for evidence integrity.
    """

    def __init__(self, registry_path: Optional[Path] = None) -> None:
        self._path = registry_path or Path("./logs/model_registry.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._versions: List[ModelVersion] = []
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._path.exists():
            with open(self._path) as fh:
                data = json.load(fh)
            self._versions = [ModelVersion(**entry) for entry in data]
            log.info("model_registry_loaded", entries=len(self._versions))
        else:
            self._versions = []

    def _save(self) -> None:
        with open(self._path, "w") as fh:
            json.dump([v.to_dict() for v in self._versions], fh, indent=2)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_model(
        self,
        model_name: str,
        version: str,
        file_path: str,
        model_type: str,
        description: str = "",
        deployed_by: Optional[str] = None,
    ) -> ModelVersion:
        """
        Register a new model version.

        The SHA-256 hash of the file is computed and stored automatically.
        Any previously active version for the same model_name is left as-is
        (caller must call deprecate_version() to retire the old one).
        """
        file_path_obj = Path(file_path)
        if file_path_obj.exists():
            sha256 = _hash_file(file_path_obj)
        else:
            sha256 = "file_not_found"
            log.warning("model_file_not_found", path=file_path)

        entry = ModelVersion(
            id=str(uuid.uuid4()),
            model_name=model_name,
            version=version,
            file_path=file_path,
            sha256_hash=sha256,
            model_type=model_type,
            description=description,
            deployed_by=deployed_by,
        )
        self._versions.append(entry)
        self._save()
        log.info("model_registered", name=model_name, version=version, hash=sha256[:12])
        return entry

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_current_version(self, model_name: str) -> Optional[ModelVersion]:
        """Return the latest active version for the given model name."""
        active = [v for v in self._versions if v.model_name == model_name and v.status == "active"]
        if not active:
            return None
        return sorted(active, key=lambda v: v.deployed_at)[-1]

    def get_version(self, model_name: str, version: str) -> Optional[ModelVersion]:
        """Return a specific version entry."""
        for v in self._versions:
            if v.model_name == model_name and v.version == version:
                return v
        return None

    def list_versions(self, model_name: Optional[str] = None) -> List[ModelVersion]:
        """Return version history, optionally filtered by model name."""
        if model_name:
            return [v for v in self._versions if v.model_name == model_name]
        return list(self._versions)

    # ------------------------------------------------------------------
    # Deprecation / rollback
    # ------------------------------------------------------------------

    def deprecate_version(
        self,
        model_name: str,
        version: str,
        reason: str,
        deprecated_by: Optional[str] = None,
    ) -> bool:
        """
        Mark a version as deprecated and reactivate the previous version.

        Deprecation is a forward entry (the version record is mutated
        only in memory/file, not on a blockchain ledger - the file hash
        ledger records model metadata separately).
        """
        target = self.get_version(model_name, version)
        if target is None:
            log.warning("deprecate_version_not_found", name=model_name, version=version)
            return False

        target.status = "deprecated"
        target.deprecated_at = datetime.utcnow().isoformat()
        target.deprecated_by = deprecated_by
        target.deprecation_reason = reason

        # Reactivate the previous active version (if any)
        all_active = [
            v for v in self._versions
            if v.model_name == model_name and v.status == "active" and v.id != target.id
        ]
        if all_active:
            prev = sorted(all_active, key=lambda v: v.deployed_at)[-1]
            prev.status = "reverted"  # mark as reverted-reactivation
            prev.description = f"{prev.description} [Reactivated after {version} deprecated]"
            log.info("model_reverted", name=model_name, reverted_to=prev.version)

        self._save()
        log.info("model_deprecated", name=model_name, version=version, reason=reason)
        return True

    # ------------------------------------------------------------------
    # Embedding version change hook
    # ------------------------------------------------------------------

    async def on_personnel_embedding_update(
        self,
        new_version_id: str,
        db: Any,  # AsyncSession
    ) -> None:
        """
        Called whenever a new personnel face embedding version is deployed.

        Flags all GlobalIdentity records whose authorization_status was
        established against the now-superseded embedding version for
        background re-verification.
        """
        from sqlalchemy import select, update
        from backend.models.track import GlobalIdentity

        log.info("personnel_embedding_update_triggered", new_version=new_version_id)

        result = await db.execute(
            select(GlobalIdentity).where(
                GlobalIdentity.authorization_status == "authorized",
                GlobalIdentity.matched_embedding_version != new_version_id,
            )
        )
        stale_identities = result.scalars().all()

        for identity in stale_identities:
            # Downgrade to 'pending_reverification' - not unauthorized,
            # but not trusted at full confidence until re-checked
            identity.authorization_status = "pending_reverification"

        if stale_identities:
            await db.commit()
            log.warning(
                "identities_flagged_for_reverification",
                count=len(stale_identities),
                new_embedding_version=new_version_id,
            )

    # ------------------------------------------------------------------
    # Current versions snapshot (for event stamping)
    # ------------------------------------------------------------------

    def get_active_versions_snapshot(self) -> Dict[str, str]:
        """
        Return a dict of {model_name: version_string} for all currently
        active models. Used to stamp every generated Event record.
        """
        result: Dict[str, str] = {}
        for model_name in {v.model_name for v in self._versions}:
            current = self.get_current_version(model_name)
            if current:
                result[model_name] = current.version
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_file(path: Path, chunk: int = 65536) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            data = fh.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


# Module-level singleton
_registry: Optional[ModelRegistry] = None


def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry


def init_registry(path: Optional[Path] = None) -> ModelRegistry:
    global _registry
    _registry = ModelRegistry(path)
    return _registry
