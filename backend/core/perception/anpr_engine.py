"""
SmartCCTV SIH26187 — ANPR (Automatic Number Plate Recognition) Engine.

Uses YOLOv8 fine-tuned for plates (falls back to lower-half crop heuristic)
for localisation and EasyOCR for text extraction.  Quality gating prevents
low-confidence reads from being surfaced as facts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from backend.config import settings

logger = logging.getLogger(__name__)

_PLATE_MODEL_PATH = "models/plate_detector.pt"


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class ANPRResult:
    """Result of ANPR processing on a vehicle crop."""

    raw_text: str
    confidence: float
    plate_bbox: Optional[Tuple[int, int, int, int]]   # x, y, w, h within vehicle crop
    quality_score: float
    image_quality_metrics: Dict[str, float] = field(default_factory=dict)
    is_reliable: bool = True   # False when quality insufficient
    reason: str = ""           # Set when is_reliable=False


# ---------------------------------------------------------------------------
# Plate Localiser
# ---------------------------------------------------------------------------


class PlateLocalizer:
    """Detect the license plate region within a vehicle bounding box.

    Tries a YOLOv8 plate detector first; falls back to a lower-half crop
    heuristic if the weights file is absent.
    """

    def __init__(self) -> None:
        """Load plate detection model if available."""
        self._model = None
        self._using_fallback = False
        self._load()

    def _load(self) -> None:
        """Attempt to load YOLOv8 plate detector."""
        model_path = Path(_PLATE_MODEL_PATH)
        if not model_path.exists():
            logger.info(
                "Plate detector weights not found at %s; using lower-half heuristic.",
                model_path,
            )
            self._using_fallback = True
            return

        try:
            from ultralytics import YOLO

            self._model = YOLO(str(model_path))
            logger.info("Plate detector loaded from %s.", model_path)
        except Exception as exc:
            logger.warning("Plate detector load failed (%s); using fallback.", exc)
            self._using_fallback = True

    def localise(
        self, vehicle_crop: np.ndarray
    ) -> Optional[Tuple[int, int, int, int]]:
        """Detect plate region within a vehicle crop.

        Args:
            vehicle_crop: BGR crop of the full vehicle.

        Returns:
            (x, y, w, h) of the plate region within the crop, or None.
        """
        if not self._using_fallback and self._model is not None:
            return self._model_localise(vehicle_crop)
        return self._heuristic_localise(vehicle_crop)

    def _model_localise(
        self, crop: np.ndarray
    ) -> Optional[Tuple[int, int, int, int]]:
        """Run YOLO plate detection on the crop."""
        try:
            results = self._model(crop, verbose=False)  # type: ignore[operator]
            if not results or results[0].boxes is None:
                return None
            best = None
            best_conf = 0.0
            for box in results[0].boxes:
                conf = float(box.conf.item())
                if conf > best_conf:
                    x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
                    best = (x1, y1, x2 - x1, y2 - y1)
                    best_conf = conf
            return best
        except Exception as exc:
            logger.warning("Plate model inference failed: %s", exc)
            return self._heuristic_localise(crop)

    @staticmethod
    def _heuristic_localise(
        crop: np.ndarray,
    ) -> Tuple[int, int, int, int]:
        """Return the lower 25% strip of the crop as the plate region."""
        h, w = crop.shape[:2]
        y_start = int(h * 0.65)
        return (0, y_start, w, h - y_start)


# ---------------------------------------------------------------------------
# OCR Engine
# ---------------------------------------------------------------------------


class ANPROCREngine:
    """EasyOCR-based text extraction with confidence filtering."""

    def __init__(self) -> None:
        """Initialise EasyOCR reader."""
        self._reader = None
        self._load()

    def _load(self) -> None:
        """Load EasyOCR with English and Hindi support."""
        try:
            import easyocr

            self._reader = easyocr.Reader(
                ["en", "hi"],
                gpu=settings.USE_GPU,
                verbose=False,
            )
            logger.info("EasyOCR initialised with [en, hi].")
        except Exception as exc:
            logger.warning("EasyOCR unavailable: %s", exc)

    def read(
        self, plate_crop: np.ndarray
    ) -> Tuple[str, float]:
        """Extract text from a plate crop.

        Args:
            plate_crop: BGR image of the plate region.

        Returns:
            Tuple of (raw_text, mean_confidence).
        """
        if self._reader is None:
            return "ANPR_UNAVAILABLE", 0.0

        try:
            # Pre-process: upscale small plates, convert to greyscale+threshold
            h, w = plate_crop.shape[:2]
            if w < 100:
                scale = 100 / w
                plate_crop = cv2.resize(
                    plate_crop,
                    (int(w * scale), int(h * scale)),
                    interpolation=cv2.INTER_CUBIC,
                )

            gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            results = self._reader.readtext(thresh, detail=1)
            if not results:
                return "", 0.0

            texts = []
            confidences = []
            for _, text, conf in results:
                if conf >= settings.ANPR_CONFIDENCE_THRESHOLD:
                    texts.append(text.strip().upper())
                    confidences.append(conf)

            if not texts:
                return "", 0.0

            raw = " ".join(texts)
            mean_conf = float(sum(confidences) / len(confidences))
            return raw, mean_conf
        except Exception as exc:
            logger.warning("OCR read failed: %s", exc)
            return "ANPR_ERROR", 0.0


# ---------------------------------------------------------------------------
# ANPR Engine
# ---------------------------------------------------------------------------


class ANPREngine:
    """End-to-end ANPR processing pipeline.

    Localises the plate region within a vehicle bbox, runs OCR, applies
    quality gating, and returns a structured ANPRResult.
    """

    def __init__(self) -> None:
        """Initialise localiser and OCR components."""
        self._localiser = PlateLocalizer()
        self._ocr = ANPROCREngine()

    def process_vehicle(
        self,
        frame: np.ndarray,
        vehicle_bbox: Tuple[int, int, int, int],
    ) -> Optional[ANPRResult]:
        """Run ANPR on one vehicle detection.

        Args:
            frame:        Full BGR frame.
            vehicle_bbox: (x1, y1, x2, y2) vehicle bounding box.

        Returns:
            ANPRResult or None if the vehicle crop is invalid.
        """
        x1, y1, x2, y2 = vehicle_bbox
        if x2 <= x1 or y2 <= y1:
            return None

        vehicle_crop = frame[y1:y2, x1:x2]
        if vehicle_crop.size == 0:
            return None

        plate_bbox = self._localiser.localise(vehicle_crop)
        if plate_bbox is None:
            return ANPRResult(
                raw_text="ANPR_UNAVAILABLE",
                confidence=0.0,
                plate_bbox=None,
                quality_score=0.0,
                is_reliable=False,
                reason="Plate region not detected",
            )

        px, py, pw, ph = plate_bbox
        plate_crop = vehicle_crop[py: py + ph, px: px + pw]
        if plate_crop.size == 0:
            return ANPRResult(
                raw_text="ANPR_UNAVAILABLE",
                confidence=0.0,
                plate_bbox=plate_bbox,
                quality_score=0.0,
                is_reliable=False,
                reason="Empty plate crop",
            )

        quality_score, metrics = self.quality_check(plate_crop)

        if quality_score < 0.3:
            return ANPRResult(
                raw_text="ANPR_UNAVAILABLE",
                confidence=0.0,
                plate_bbox=plate_bbox,
                quality_score=quality_score,
                image_quality_metrics=metrics,
                is_reliable=False,
                reason=f"Insufficient plate quality (score={quality_score:.2f})",
            )

        raw_text, confidence = self._ocr.read(plate_crop)

        if not raw_text or confidence < settings.ANPR_CONFIDENCE_THRESHOLD:
            return ANPRResult(
                raw_text=raw_text or "",
                confidence=confidence,
                plate_bbox=plate_bbox,
                quality_score=quality_score,
                image_quality_metrics=metrics,
                is_reliable=False,
                reason=f"Low OCR confidence ({confidence:.2f} < {settings.ANPR_CONFIDENCE_THRESHOLD})",
            )

        return ANPRResult(
            raw_text=raw_text,
            confidence=confidence,
            plate_bbox=plate_bbox,
            quality_score=quality_score,
            image_quality_metrics=metrics,
            is_reliable=True,
        )

    @staticmethod
    def quality_check(
        plate_crop: np.ndarray,
    ) -> Tuple[float, Dict[str, float]]:
        """Assess whether a plate crop has sufficient quality for reliable OCR.

        Checks: area, sharpness (Laplacian), and brightness.

        Args:
            plate_crop: BGR plate region.

        Returns:
            Tuple of (quality_score [0,1], metrics_dict).
        """
        h, w = plate_crop.shape[:2]
        area = h * w

        metrics: Dict[str, float] = {"area_px": float(area)}

        # Area check
        area_score = min(1.0, area / max(settings.ANPR_MIN_PLATE_AREA_PX, 1))
        metrics["area_score"] = area_score

        # Sharpness (Laplacian variance)
        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        sharpness_score = min(1.0, sharpness / 500.0)
        metrics["sharpness"] = sharpness
        metrics["sharpness_score"] = sharpness_score

        # Brightness (avoid over/underexposed)
        mean_brightness = float(gray.mean())
        if mean_brightness < 30 or mean_brightness > 220:
            brightness_score = 0.3
        else:
            brightness_score = 1.0
        metrics["mean_brightness"] = mean_brightness
        metrics["brightness_score"] = brightness_score

        quality_score = (area_score + sharpness_score + brightness_score) / 3.0
        metrics["overall_quality"] = quality_score
        return quality_score, metrics


# Singleton
anpr_engine = ANPREngine()
