"""
SmartCCTV SIH26187 — Pluggable Face Engine.

Provides a FaceBackend abstraction with two implementations:
  - HaarFaceBackend: OpenCV Haar cascade (always available, no embedding)
  - InsightFaceBackend: RetinaFace detection + ArcFace embedding with
    MediaPipe liveness check (requires insightface package)

The FaceEngine wrapper class manages separate FAISS indices for
watchlist and personnel matching.
"""

from __future__ import annotations

import logging
import pickle
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from backend.config import settings

logger = logging.getLogger(__name__)

_EMBEDDING_DIM = 512
_HAAR_XML = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class FaceDetection:
    """A single detected face region."""

    bbox: Tuple[int, int, int, int]   # x, y, w, h
    confidence: float
    is_live: bool = True              # liveness result (Haar always True)

    @property
    def x1(self) -> int:
        return int(self.bbox[0])

    @property
    def y1(self) -> int:
        return int(self.bbox[1])

    @property
    def x2(self) -> int:
        return int(self.bbox[0] + self.bbox[2])

    @property
    def y2(self) -> int:
        return int(self.bbox[1] + self.bbox[3])


@dataclass
class WatchlistMatch:
    """Result of a watchlist FAISS match."""

    watchlist_id: str
    label: str
    distance: float
    confidence: float


@dataclass
class PersonnelMatch:
    """Result of a personnel FAISS match."""

    person_id: str
    name: str
    authorization_level: int
    distance: float
    confidence: float


# ---------------------------------------------------------------------------
# Abstract Backend
# ---------------------------------------------------------------------------


class FaceBackend(ABC):
    """Abstract interface for face detection and embedding backends."""

    @abstractmethod
    def detect(self, frame: np.ndarray) -> List[FaceDetection]:
        """Detect faces in a frame.

        Args:
            frame: BGR image array.

        Returns:
            List of FaceDetection objects.
        """
        ...

    @abstractmethod
    def embed(self, face_crop: np.ndarray) -> Optional[np.ndarray]:
        """Extract a face embedding from a cropped face image.

        Args:
            face_crop: BGR crop of a face.

        Returns:
            512-d float32 embedding or None if not supported / failed.
        """
        ...


# ---------------------------------------------------------------------------
# Haar Cascade Backend (always available)
# ---------------------------------------------------------------------------


class HaarFaceBackend(FaceBackend):
    """OpenCV Haar cascade face detector.

    Detection only — no embedding capability.  Used as the default
    fallback when insightface is not installed or FACE_BACKEND='haar'.
    """

    def __init__(self) -> None:
        """Load the Haar cascade classifier."""
        self._cascade = cv2.CascadeClassifier(_HAAR_XML)
        if self._cascade.empty():
            raise RuntimeError(
                f"Failed to load Haar cascade from {_HAAR_XML}. "
                "Ensure opencv-python is installed correctly."
            )
        logger.info("HaarFaceBackend initialised.")

    def detect(self, frame: np.ndarray) -> List[FaceDetection]:
        """Detect faces using Haar cascade.

        Args:
            frame: BGR image array.

        Returns:
            List of FaceDetection; confidence is heuristic (always 0.5).
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30),
        )
        result = []
        if len(faces) > 0:
            for x, y, w, h in faces:
                result.append(
                    FaceDetection(bbox=(int(x), int(y), int(w), int(h)), confidence=0.5, is_live=True)
                )
        return result

    def embed(self, face_crop: np.ndarray) -> Optional[np.ndarray]:
        """Haar backend does not support embedding extraction.

        Returns:
            Always None — upgrade to InsightFace for embeddings.
        """
        return None


# ---------------------------------------------------------------------------
# InsightFace Backend (ArcFace + RetinaFace)
# ---------------------------------------------------------------------------


class InsightFaceBackend(FaceBackend):
    """InsightFace ArcFace + RetinaFace backend.

    Provides robust multi-angle face detection and 512-d ArcFace embeddings.
    Includes MediaPipe-based liveness check (blink / EAR detection).
    Falls back to HaarFaceBackend if insightface is not importable.
    """

    def __init__(self) -> None:
        """Initialise InsightFace and MediaPipe."""
        self._app = None
        self._mp_face_mesh = None
        self._fallback: Optional[HaarFaceBackend] = None
        self._load()

    def _load(self) -> None:
        """Load InsightFace app and MediaPipe face mesh."""
        try:
            import insightface
            from insightface.app import FaceAnalysis

            self._app = FaceAnalysis(
                name="buffalo_l",
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
                if (settings.USE_GPU)
                else ["CPUExecutionProvider"],
            )
            self._app.prepare(ctx_id=0 if settings.USE_GPU else -1, det_size=(640, 640))
            logger.info("InsightFaceBackend: FaceAnalysis loaded (buffalo_l).")
        except Exception as exc:
            logger.warning(
                "InsightFace unavailable (%s); falling back to HaarFaceBackend.", exc
            )
            self._fallback = HaarFaceBackend()

        try:
            import mediapipe as mp

            self._mp_face_mesh = mp.solutions.face_mesh.FaceMesh(  # type: ignore[attr-defined]
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
            )
            logger.info("MediaPipe FaceMesh loaded for liveness detection.")
        except Exception as exc:
            logger.warning("MediaPipe unavailable (%s); liveness checks disabled.", exc)

    def detect(self, frame: np.ndarray) -> List[FaceDetection]:
        """Detect faces using RetinaFace.

        Falls back to Haar if InsightFace is unavailable.

        Args:
            frame: BGR image array.

        Returns:
            List of FaceDetection with confidence from RetinaFace.
        """
        if self._fallback:
            return self._fallback.detect(frame)

        if self._app is None:
            return []

        try:
            faces = self._app.get(frame)
            result = []
            for face in faces:
                bbox = face.bbox.astype(int)
                x1, y1, x2, y2 = bbox
                w, h = x2 - x1, y2 - y1
                det_score = float(face.det_score) if hasattr(face, "det_score") else 0.9
                live = self.liveness_check(frame[y1:y2, x1:x2])
                result.append(
                    FaceDetection(bbox=(x1, y1, w, h), confidence=det_score, is_live=live)
                )
            return result
        except Exception as exc:
            logger.warning("InsightFace detection failed: %s", exc)
            return []

    def embed(self, face_crop: np.ndarray) -> Optional[np.ndarray]:
        """Extract 512-d ArcFace embedding.

        Args:
            face_crop: BGR face crop.

        Returns:
            Unit-normalised 512-d float32 numpy array or None.
        """
        if self._fallback:
            return None

        if self._app is None or face_crop is None or face_crop.size == 0:
            return None

        try:
            faces = self._app.get(face_crop)
            if not faces:
                return None
            emb = faces[0].normed_embedding.astype(np.float32)
            norm = np.linalg.norm(emb)
            return emb / norm if norm > 0 else emb
        except Exception as exc:
            logger.warning("ArcFace embedding failed: %s", exc)
            return None

    def liveness_check(self, face_crop: np.ndarray) -> bool:
        """Estimate liveness using MediaPipe Eye Aspect Ratio (blink heuristic).

        For single-frame liveness, checks that eyes are open (EAR > 0.2).
        Multi-frame blink sequence detection requires a temporal buffer
        in the calling context.

        Args:
            face_crop: BGR crop of the face.

        Returns:
            True if likely live (eyes open or MediaPipe unavailable).
            False if eyes appear closed (possible photo attack).
        """
        if self._mp_face_mesh is None or face_crop is None or face_crop.size == 0:
            return True  # Cannot determine — assume live

        try:
            import mediapipe as mp

            rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
            results = self._mp_face_mesh.process(rgb)
            if not results.multi_face_landmarks:
                return True

            lm = results.multi_face_landmarks[0].landmark
            h, w = face_crop.shape[:2]

            # Left eye EAR landmarks (MediaPipe indices)
            def _dist(a: int, b: int) -> float:
                dx = (lm[a].x - lm[b].x) * w
                dy = (lm[a].y - lm[b].y) * h
                return float((dx ** 2 + dy ** 2) ** 0.5)

            # Approximate EAR: vertical / horizontal distances
            left_ear = (_dist(159, 145) + _dist(158, 153)) / (2.0 * _dist(33, 133) + 1e-6)
            right_ear = (_dist(386, 374) + _dist(385, 380)) / (2.0 * _dist(362, 263) + 1e-6)
            ear = (left_ear + right_ear) / 2.0
            return ear > 0.15  # Below 0.15 suggests eyes closed

        except Exception as exc:
            logger.debug("Liveness check exception: %s", exc)
            return True


# ---------------------------------------------------------------------------
# Face Engine Wrapper
# ---------------------------------------------------------------------------


class FaceEngine:
    """Unified face engine wrapping a backend with FAISS index management.

    Maintains separate FAISS indices for watchlist and personnel.
    Index entries store entity IDs alongside each vector.
    """

    def __init__(self) -> None:
        """Select backend from config and initialise FAISS indices."""
        self.backend: FaceBackend = self._build_backend()

        # FAISS indices
        self._watchlist_index = None
        self._watchlist_ids: List[str] = []
        self._watchlist_labels: Dict[str, str] = {}

        self._personnel_index = None
        self._personnel_ids: List[str] = []
        self._personnel_meta: Dict[str, Dict] = {}

        self._init_indices()

    def _build_backend(self) -> FaceBackend:
        """Build the appropriate backend from settings."""
        if settings.FACE_BACKEND == "insightface":
            try:
                return InsightFaceBackend()
            except Exception as exc:
                logger.warning("InsightFace init failed (%s); using Haar.", exc)
        return HaarFaceBackend()

    def _init_indices(self) -> None:
        """Initialise FAISS flat L2 indices for watchlist and personnel."""
        try:
            import faiss

            self._watchlist_index = faiss.IndexFlatL2(_EMBEDDING_DIM)
            self._personnel_index = faiss.IndexFlatL2(_EMBEDDING_DIM)
        except Exception as exc:
            logger.warning("FAISS unavailable for face matching: %s", exc)

    # ------------------------------------------------------------------
    # Detection & Embedding
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray) -> List[FaceDetection]:
        """Detect faces in a frame using the configured backend."""
        return self.backend.detect(frame)

    def embed(self, face_crop: np.ndarray) -> Optional[np.ndarray]:
        """Extract a face embedding using the configured backend."""
        return self.backend.embed(face_crop)

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def match_watchlist(
        self,
        embedding: np.ndarray,
        threshold: float = 0.6,
    ) -> Optional[WatchlistMatch]:
        """Search the watchlist FAISS index for a match.

        Args:
            embedding:  512-d query embedding.
            threshold:  L2 distance threshold for a positive match.

        Returns:
            WatchlistMatch if found within threshold, else None.
        """
        if self._watchlist_index is None or self._watchlist_index.ntotal == 0:
            return None

        try:
            vec = embedding.reshape(1, -1).astype(np.float32)
            distances, indices = self._watchlist_index.search(vec, 1)
            dist = float(distances[0][0])
            idx = int(indices[0][0])
            if idx < 0 or idx >= len(self._watchlist_ids):
                return None
            if dist > threshold * 2:  # L2 ~ 2*(1-cosine) for unit vectors
                return None
            wid = self._watchlist_ids[idx]
            return WatchlistMatch(
                watchlist_id=wid,
                label=self._watchlist_labels.get(wid, "Unknown"),
                distance=dist,
                confidence=max(0.0, 1.0 - dist / 2.0),
            )
        except Exception as exc:
            logger.warning("Watchlist match failed: %s", exc)
            return None

    def match_personnel(
        self,
        embedding: np.ndarray,
        threshold: float = 0.6,
    ) -> Optional[PersonnelMatch]:
        """Search the personnel FAISS index for a match.

        Args:
            embedding:  512-d query embedding.
            threshold:  L2 distance threshold for a positive match.

        Returns:
            PersonnelMatch if found within threshold, else None.
        """
        if self._personnel_index is None or self._personnel_index.ntotal == 0:
            return None

        try:
            vec = embedding.reshape(1, -1).astype(np.float32)
            distances, indices = self._personnel_index.search(vec, 1)
            dist = float(distances[0][0])
            idx = int(indices[0][0])
            if idx < 0 or idx >= len(self._personnel_ids):
                return None
            if dist > threshold * 2:
                return None
            pid = self._personnel_ids[idx]
            meta = self._personnel_meta.get(pid, {})
            return PersonnelMatch(
                person_id=pid,
                name=meta.get("name", "Unknown"),
                authorization_level=meta.get("authorization_level", 1),
                distance=dist,
                confidence=max(0.0, 1.0 - dist / 2.0),
            )
        except Exception as exc:
            logger.warning("Personnel match failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Enrollment
    # ------------------------------------------------------------------

    async def enroll_person(
        self,
        person_id: str,
        face_crop: np.ndarray,
        db: "AsyncSession",  # type: ignore[name-defined]
    ) -> bool:
        """Extract and store a face embedding for an authorised person.

        Args:
            person_id:  Personnel table primary key.
            face_crop:  Cropped face image (BGR).
            db:         Async DB session.

        Returns:
            True on success; False if embedding extraction failed.
        """
        from sqlalchemy import select, update
        from backend.models.user import Personnel

        embedding = self.embed(face_crop)
        if embedding is None:
            logger.warning("enroll_person: embedding failed for %s (Haar mode?).", person_id)
            return False

        if self._personnel_index is not None:
            vec = embedding.reshape(1, -1).astype(np.float32)
            self._personnel_index.add(vec)
            self._personnel_ids.append(person_id)

        result = await db.execute(select(Personnel).where(Personnel.person_id == person_id))
        person = result.scalar_one_or_none()
        if person:
            person.face_embedding = embedding.tobytes()
            self._personnel_meta[person_id] = {
                "name": person.name,
                "authorization_level": person.authorization_level,
            }
            await db.flush()

        return True

    async def enroll_watchlist(
        self,
        watchlist_id: str,
        face_crop: np.ndarray,
        db: "AsyncSession",  # type: ignore[name-defined]
    ) -> bool:
        """Extract and store a face embedding for a watchlist entry.

        Args:
            watchlist_id: Watchlist table primary key.
            face_crop:    Cropped face image (BGR).
            db:           Async DB session.

        Returns:
            True on success; False if embedding extraction failed.
        """
        from sqlalchemy import select
        from backend.models.user import Watchlist

        embedding = self.embed(face_crop)
        if embedding is None:
            logger.warning("enroll_watchlist: embedding failed for %s.", watchlist_id)
            return False

        if self._watchlist_index is not None:
            vec = embedding.reshape(1, -1).astype(np.float32)
            self._watchlist_index.add(vec)
            self._watchlist_ids.append(watchlist_id)

        result = await db.execute(
            select(Watchlist).where(Watchlist.watchlist_id == watchlist_id)
        )
        entry = result.scalar_one_or_none()
        if entry:
            entry.face_embedding = embedding.tobytes()
            self._watchlist_labels[watchlist_id] = entry.label
            await db.flush()

        return True

    # ------------------------------------------------------------------
    # Index Persistence
    # ------------------------------------------------------------------

    def save_indices(self) -> None:
        """Persist both FAISS indices and metadata to disk."""
        try:
            import faiss

            for index, path, ids, meta in [
                (
                    self._watchlist_index,
                    settings.WATCHLIST_INDEX_PATH,
                    self._watchlist_ids,
                    self._watchlist_labels,
                ),
                (
                    self._personnel_index,
                    settings.PERSONNEL_INDEX_PATH,
                    self._personnel_ids,
                    self._personnel_meta,
                ),
            ]:
                if index is None:
                    continue
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                faiss.write_index(index, str(path))
                with open(Path(path).with_suffix(".pkl"), "wb") as f:
                    pickle.dump({"ids": ids, "meta": meta}, f)
            logger.info("Face FAISS indices saved.")
        except Exception as exc:
            logger.error("Failed to save face indices: %s", exc)

    def load_indices(self) -> None:
        """Load previously saved FAISS indices and metadata from disk."""
        try:
            import faiss

            for attr_idx, attr_ids, attr_meta, path in [
                ("_watchlist_index", "_watchlist_ids", "_watchlist_labels", settings.WATCHLIST_INDEX_PATH),
                ("_personnel_index", "_personnel_ids", "_personnel_meta", settings.PERSONNEL_INDEX_PATH),
            ]:
                p = Path(path)
                if not p.exists():
                    continue
                setattr(self, attr_idx, faiss.read_index(str(p)))
                pkl = p.with_suffix(".pkl")
                if pkl.exists():
                    with open(pkl, "rb") as f:
                        data = pickle.load(f)
                    setattr(self, attr_ids, data.get("ids", []))
                    setattr(self, attr_meta, data.get("meta", {}))
                logger.info("Face index loaded: %s", p)
        except Exception as exc:
            logger.error("Failed to load face indices: %s", exc)


# Singleton
face_engine = FaceEngine()


def get_face_engine() -> FaceEngine:
    """Return the singleton FaceEngine instance."""
    global face_engine
    if face_engine is None:
        face_engine = FaceEngine()
    return face_engine
