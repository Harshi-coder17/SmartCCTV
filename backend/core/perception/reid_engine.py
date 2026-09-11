"""
SmartCCTV SIH26187 — OSNet ReID Engine with FAISS Cross-Camera Matching.

Extracts 512-d appearance embeddings from person crops using torchreid's
OSNet and performs approximate nearest-neighbour search via FAISS.
Implements geography gating and ambiguous-match detection.
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from backend.config import settings

logger = logging.getLogger(__name__)

_EMBEDDING_DIM = 512


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class ReIDResult:
    """Result of a FAISS ReID query."""

    match_type: str          # 'clear_match' | 'ambiguous' | 'no_match'
    global_identity_id: Optional[str]
    confidence: float
    candidates: List[Dict]   # list of {identity_id, distance, camera_id}


@dataclass
class IndexEntry:
    """Metadata stored alongside each FAISS vector."""

    global_identity_id: str
    camera_id: str
    track_id: int
    timestamp: datetime


# ---------------------------------------------------------------------------
# ReID Engine
# ---------------------------------------------------------------------------


class ReIDEngine:
    """OSNet-based appearance ReID engine with FAISS search.

    Maintains one FAISS flat-L2 index across all cameras.
    Each vector is tagged with a GlobalIdentity ID so that cross-camera
    hits can be resolved to a single persistent identity.
    """

    def __init__(
        self,
        model_name: str = settings.REID_MODEL,
        device: Optional[str] = None,
        similarity_threshold: float = settings.REID_SIMILARITY_THRESHOLD,
        margin_threshold: float = settings.REID_MARGIN_THRESHOLD,
    ) -> None:
        """Initialise the engine.

        Args:
            model_name:           torchreid model name (e.g. 'osnet_x0_25').
            device:               'cuda' | 'cpu'; auto-detected if None.
            similarity_threshold: Distance threshold for a positive match.
            margin_threshold:     Top-1 vs top-2 margin below which result is ambiguous.
        """
        self.model_name = model_name
        self.similarity_threshold = similarity_threshold
        self.margin_threshold = margin_threshold
        self._model = None
        self._index = None          # faiss.IndexFlatL2
        self._entries: List[IndexEntry] = []
        self._device = device or self._auto_device()

        self._load_model()
        self._init_index()

    @staticmethod
    def _auto_device() -> str:
        try:
            import torch
            return "cuda" if settings.USE_GPU and torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def _load_model(self) -> None:
        """Load OSNet model via torchreid with graceful fallback."""
        try:
            import torchreid

            self._model = torchreid.models.build_model(
                name=self.model_name,
                num_classes=1000,
                pretrained=True,
            )
            self._model.eval()
            if self._device == "cuda":
                import torch
                self._model = self._model.cuda()
            logger.info("ReID model loaded: %s on %s", self.model_name, self._device)
        except Exception as exc:
            logger.warning("ReID model load failed (%s); embeddings disabled.", exc)
            self._model = None

    def _init_index(self) -> None:
        """Initialise or load the FAISS flat L2 index."""
        try:
            import faiss

            self._index = faiss.IndexFlatL2(_EMBEDDING_DIM)
            logger.info("FAISS ReID index initialised (dim=%d).", _EMBEDDING_DIM)
        except Exception as exc:
            logger.warning("FAISS not available: %s", exc)
            self._index = None

    def extract_embedding(self, crop_frame: np.ndarray) -> Optional[np.ndarray]:
        """Extract a 512-d appearance embedding from a person crop.

        Args:
            crop_frame: BGR NumPy array of the person crop.

        Returns:
            Unit-normalised 512-d float32 embedding, or None on failure.
        """
        if self._model is None or crop_frame is None or crop_frame.size == 0:
            return None

        try:
            import torch
            import torchvision.transforms as T

            transform = T.Compose([
                T.ToPILImage(),
                T.Resize((256, 128)),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])

            tensor = transform(crop_frame).unsqueeze(0)
            if self._device == "cuda":
                tensor = tensor.cuda()

            with torch.no_grad():
                feat = self._model(tensor)

            emb = feat.cpu().numpy().flatten().astype(np.float32)
            norm = np.linalg.norm(emb)
            if norm > 0:
                emb = emb / norm
            return emb
        except Exception as exc:
            logger.warning("Embedding extraction failed: %s", exc)
            return None

    def add_to_index(
        self,
        camera_id: str,
        track_id: int,
        global_identity_id: str,
        embedding: np.ndarray,
        timestamp: datetime,
    ) -> None:
        """Add an embedding vector to the FAISS index.

        Args:
            camera_id:           Source camera.
            track_id:            Local track ID.
            global_identity_id:  Associated global identity.
            embedding:           512-d float32 embedding.
            timestamp:           When this embedding was extracted.
        """
        if self._index is None:
            return

        vec = embedding.reshape(1, -1).astype(np.float32)
        self._index.add(vec)  # type: ignore[union-attr]
        self._entries.append(
            IndexEntry(
                global_identity_id=global_identity_id,
                camera_id=camera_id,
                track_id=track_id,
                timestamp=timestamp,
            )
        )

    def query(
        self,
        embedding: np.ndarray,
        candidate_camera_ids: Optional[List[str]] = None,
    ) -> ReIDResult:
        """Query the FAISS index for the closest matching identity.

        Implements geography gating: if candidate_camera_ids is provided,
        only entries from those cameras are considered.

        Args:
            embedding:             512-d query embedding.
            candidate_camera_ids:  Camera IDs to restrict search to.

        Returns:
            ReIDResult with match_type, identity, and confidence.
        """
        if self._index is None or self._index.ntotal == 0:  # type: ignore[union-attr]
            return ReIDResult(
                match_type="no_match",
                global_identity_id=None,
                confidence=0.0,
                candidates=[],
            )

        try:
            import faiss

            k = min(5, self._index.ntotal)  # type: ignore[union-attr]
            vec = embedding.reshape(1, -1).astype(np.float32)
            distances, indices = self._index.search(vec, k)  # type: ignore[union-attr]

            candidates = []
            for dist, idx in zip(distances[0], indices[0]):
                if idx < 0 or idx >= len(self._entries):
                    continue
                entry = self._entries[idx]
                if candidate_camera_ids and entry.camera_id not in candidate_camera_ids:
                    continue
                candidates.append(
                    {
                        "identity_id": entry.global_identity_id,
                        "distance": float(dist),
                        "camera_id": entry.camera_id,
                        "track_id": entry.track_id,
                    }
                )

            if not candidates:
                return ReIDResult(
                    match_type="no_match",
                    global_identity_id=None,
                    confidence=0.0,
                    candidates=[],
                )

            candidates.sort(key=lambda x: x["distance"])
            top = candidates[0]

            # Convert L2 distance to a confidence-like score [0,1].
            confidence = max(0.0, 1.0 - top["distance"] / 2.0)

            if confidence < self.similarity_threshold:
                return ReIDResult(
                    match_type="no_match",
                    global_identity_id=None,
                    confidence=confidence,
                    candidates=candidates,
                )

            if len(candidates) > 1:
                margin = candidates[1]["distance"] - top["distance"]
                if margin < self.margin_threshold:
                    return ReIDResult(
                        match_type="ambiguous",
                        global_identity_id=top["identity_id"],
                        confidence=confidence,
                        candidates=candidates,
                    )

            return ReIDResult(
                match_type="clear_match",
                global_identity_id=top["identity_id"],
                confidence=confidence,
                candidates=candidates,
            )
        except Exception as exc:
            logger.error("FAISS query failed: %s", exc)
            return ReIDResult(
                match_type="no_match",
                global_identity_id=None,
                confidence=0.0,
                candidates=[],
            )

    async def update_global_identity(
        self,
        local_track_id: int,
        camera_id: str,
        reid_result: ReIDResult,
        embedding: np.ndarray,
        db: "AsyncSession",  # type: ignore[name-defined]
    ) -> str:
        """Reconcile a ReID result with the GlobalIdentity table.

        - clear_match: link track to existing identity.
        - ambiguous:   link with 'provisional' authorization_status.
        - no_match:    create a new GlobalIdentity.

        Args:
            local_track_id: Local ByteTrack track ID.
            camera_id:      Camera the track was seen on.
            reid_result:    Result from query().
            embedding:      Current embedding for storage.
            db:             Async DB session.

        Returns:
            The global_identity_id (existing or newly created).
        """
        from sqlalchemy import select
        from backend.models.track import GlobalIdentity

        if reid_result.match_type == "clear_match" and reid_result.global_identity_id:
            gid = reid_result.global_identity_id
            result = await db.execute(
                select(GlobalIdentity).where(GlobalIdentity.identity_id == gid)
            )
            identity = result.scalar_one_or_none()
            if identity:
                identity.movement_log = (identity.movement_log or []) + [
                    {
                        "camera_id": camera_id,
                        "timestamp": datetime.utcnow().isoformat(),
                        "confidence": reid_result.confidence,
                    }
                ]
                identity.reid_embedding = embedding.tobytes()
                await db.flush()
                return gid

        if reid_result.match_type == "ambiguous" and reid_result.global_identity_id:
            auth_status = "provisional"
        else:
            auth_status = "unauthorized"

        new_identity = GlobalIdentity(
            authorization_status=auth_status,
            reid_embedding=embedding.tobytes(),
            movement_log=[
                {
                    "camera_id": camera_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "confidence": reid_result.confidence,
                }
            ],
        )
        db.add(new_identity)
        await db.flush()
        return new_identity.identity_id

    def save_index(self, path: Optional[Path] = None) -> None:
        """Persist the FAISS index and entry metadata to disk.

        Args:
            path: Directory to save to; defaults to settings.REID_INDEX_PATH parent.
        """
        if self._index is None:
            return
        try:
            import faiss

            save_path = path or settings.REID_INDEX_PATH
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self._index, str(save_path))  # type: ignore[attr-defined]
            meta_path = save_path.with_suffix(".pkl")
            with open(meta_path, "wb") as f:
                pickle.dump(self._entries, f)
            logger.info("ReID FAISS index saved to %s", save_path)
        except Exception as exc:
            logger.error("Failed to save ReID index: %s", exc)

    def load_index(self, path: Optional[Path] = None) -> None:
        """Load a previously saved FAISS index from disk.

        Args:
            path: Path to the .faiss file; defaults to settings.REID_INDEX_PATH.
        """
        try:
            import faiss

            load_path = path or settings.REID_INDEX_PATH
            load_path = Path(load_path)
            if not load_path.exists():
                logger.info("No saved ReID index found at %s.", load_path)
                return
            self._index = faiss.read_index(str(load_path))  # type: ignore[attr-defined]
            meta_path = load_path.with_suffix(".pkl")
            if meta_path.exists():
                with open(meta_path, "rb") as f:
                    self._entries = pickle.load(f)
            logger.info(
                "ReID FAISS index loaded from %s (%d vectors).",
                load_path,
                self._index.ntotal,  # type: ignore[union-attr]
            )
        except Exception as exc:
            logger.error("Failed to load ReID index: %s", exc)


# Singleton
reid_engine = ReIDEngine()
