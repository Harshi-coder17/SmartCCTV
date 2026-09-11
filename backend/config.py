"""
SmartCCTV SIH26187 — Configuration Module.

Centralises every runtime parameter in a Pydantic-Settings class.
Never hard-code constants elsewhere — import from here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# RSA Key Generation Helper
# ---------------------------------------------------------------------------

def generate_rsa_keys(
    private_key_path: Path,
    public_key_path: Path,
) -> None:
    """Generate a 2048-bit RSA key pair and persist them to disk.

    Args:
        private_key_path: Destination for the PEM-encoded private key.
        public_key_path:  Destination for the PEM-encoded public key.
    """
    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    public_key_path.parent.mkdir(parents=True, exist_ok=True)

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

    private_key_path.write_bytes(priv_pem)
    public_key_path.write_bytes(pub_pem)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    """Application-wide settings loaded from environment / .env file.

    All constants in the system must be sourced from this class.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    DATABASE_URL: str = "sqlite+aiosqlite:///./smartcctv.db"
    POSTGRES_URL: Optional[str] = None

    # ------------------------------------------------------------------
    # JWT / Auth
    # ------------------------------------------------------------------
    SECRET_KEY: str = "keys/private_key.pem"        # path to RS256 private key
    PUBLIC_KEY_PATH: str = "keys/public_key.pem"    # path to RS256 public key
    JWT_ALGORITHM: str = "RS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ------------------------------------------------------------------
    # File System Paths
    # ------------------------------------------------------------------
    EVIDENCE_DIR: Path = Path("./evidence")
    MODELS_DIR: Path = Path("./models")
    HASH_LEDGER_PATH: Path = Path("./logs/hash_ledger.db")
    AUDIT_LOG_PATH: Path = Path("./logs/audit.log")

    # ------------------------------------------------------------------
    # Model Configuration
    # ------------------------------------------------------------------
    YOLO_MODEL: str = "yolov8n.pt"
    REID_MODEL: str = "osnet_x0_25"
    FACE_BACKEND: str = "haar"          # 'haar' | 'insightface'

    # ------------------------------------------------------------------
    # Hardware
    # ------------------------------------------------------------------
    USE_GPU: bool = True

    # ------------------------------------------------------------------
    # Analytics Pipeline
    # ------------------------------------------------------------------
    ANALYTICS_FPS: int = 5              # process every Nth frame for AI
    EVIDENCE_PRE_EVENT_SECS: int = 10
    EVIDENCE_POST_EVENT_SECS: int = 20

    # ------------------------------------------------------------------
    # Camera Health
    # ------------------------------------------------------------------
    CAMERA_HEALTH_INTERVAL_SECS: int = 5
    BLANK_FRAME_VARIANCE_THRESHOLD: float = 100.0    # below = covered
    SHARPNESS_LAPLACIAN_THRESHOLD: float = 50.0      # below = blurry
    FPS_DEGRADED_RATIO: float = 0.5                  # actual/expected < 0.5 = degraded

    # ------------------------------------------------------------------
    # ReID
    # ------------------------------------------------------------------
    REID_SIMILARITY_THRESHOLD: float = 0.75
    REID_MARGIN_THRESHOLD: float = 0.10

    # ------------------------------------------------------------------
    # Behavioural Thresholds
    # ------------------------------------------------------------------
    LOITERING_THRESHOLD_SECS: int = 30
    ABANDONED_OBJECT_THRESHOLD_SECS: int = 60
    CROWD_DENSITY_THRESHOLD: float = 0.05    # persons per pixel²
    CROWD_COUNT_THRESHOLD: int = 10

    # ------------------------------------------------------------------
    # Risk Score Bands
    # ------------------------------------------------------------------
    RISK_LOW_MAX: int = 20
    RISK_MEDIUM_MAX: int = 40
    RISK_HIGH_MAX: int = 60

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ------------------------------------------------------------------
    # Paths for FAISS indices
    # ------------------------------------------------------------------
    WATCHLIST_INDEX_PATH: Path = Path("./models/watchlist.faiss")
    PERSONNEL_INDEX_PATH: Path = Path("./models/personnel.faiss")
    REID_INDEX_PATH: Path = Path("./models/reid.faiss")

    # ------------------------------------------------------------------
    # Topology
    # ------------------------------------------------------------------
    TOPOLOGY_CONFIG_PATH: Path = Path("./data/topology.json")
    CAMERAS_JSON_PATH: Path = Path("./data/cameras.json")
    ZONES_JSON_PATH: Path = Path("./data/zones.json")
    RISK_WEIGHTS_JSON_PATH: Path = Path("./data/risk_weights.json")

    # ------------------------------------------------------------------
    # ANPR
    # ------------------------------------------------------------------
    ANPR_CONFIDENCE_THRESHOLD: float = 0.4
    ANPR_MIN_PLATE_AREA_PX: int = 1000

    # ------------------------------------------------------------------
    # Pose Engine
    # ------------------------------------------------------------------
    POSE_PERSISTENCE_FRAMES: int = 10  # signal must hold for N frames

    # ------------------------------------------------------------------
    # Server
    # ------------------------------------------------------------------
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    API_PORT: int = 8000
    DEBUG: bool = False

    @field_validator("EVIDENCE_DIR", "MODELS_DIR", mode="before")
    @classmethod
    def _coerce_path(cls, v: object) -> Path:
        return Path(str(v))

    def effective_database_url(self) -> str:
        """Return POSTGRES_URL if provided, else SQLite DATABASE_URL."""
        return self.POSTGRES_URL if self.POSTGRES_URL else self.DATABASE_URL

    def ensure_dirs(self) -> None:
        """Create all required directories on startup."""
        for directory in (
            self.EVIDENCE_DIR,
            self.MODELS_DIR,
            self.HASH_LEDGER_PATH.parent,
            self.AUDIT_LOG_PATH.parent,
            self.WATCHLIST_INDEX_PATH.parent,
            Path(self.SECRET_KEY).parent,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def ensure_rsa_keys(self) -> None:
        """Generate RSA key pair on first boot if absent."""
        priv = Path(self.SECRET_KEY)
        pub = Path(self.PUBLIC_KEY_PATH)
        if not priv.exists() or not pub.exists():
            generate_rsa_keys(priv, pub)


    def generate_rsa_keys(self) -> None:
        """Alias for ensure_rsa_keys - generate RSA keypair if absent."""
        self.ensure_rsa_keys()


# Singleton instance - import `settings` everywhere, or call get_settings()
settings = Settings()


def get_settings() -> Settings:
    """Return the singleton Settings instance.

    This function exists so modules can call get_settings() consistently,
    and it can be overridden in tests with dependency injection.
    """
    return settings
