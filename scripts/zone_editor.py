"""
Zone and Tripwire Editor Tool - SmartCCTV SIH26187
Interactive OpenCV-based editor for defining:
  - Zone polygons (restricted areas, monitored areas)
  - Tripwire lines (virtual crossing detection lines)
  - Permitted direction arrows

Usage:
    python scripts/zone_editor.py --camera CAM-01 [--video video.mp4]
    
Controls:
    Left click  - Add point to active zone/tripwire
    Right click - Finish current polygon
    'z'         - New zone polygon mode
    't'         - New tripwire mode
    'd'         - Delete last point
    'r'         - Reset current shape
    's'         - Save to data/zones.json and data/tripwires.json
    'n'         - Set name for current shape
    '1'-'5'     - Set sensitivity level (zones only)
    ESC         - Exit without saving
    'h'         - Help overlay
"""

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Color palette matching the platform's design system (BGR for OpenCV)
COLORS = {
    "accent": (170, 212, 0),        # #00D4AA in BGR
    "critical": (68, 68, 239),      # #EF4444
    "high": (22, 115, 249),         # #F97316
    "medium": (8, 179, 234),        # #EAB308
    "low": (94, 197, 34),           # #22C55E
    "tripwire": (0, 0, 220),        # Red for tripwires
    "zone_1": (200, 200, 20),       # Sensitivity 1-2: yellow-ish
    "zone_3": (20, 120, 220),       # Sensitivity 3: orange
    "zone_5": (20, 20, 220),        # Sensitivity 4-5: red
    "text": (241, 245, 249),        # Light text
    "overlay": (10, 14, 26),        # Dark overlay
    "point": (0, 212, 170),         # Accent for points
    "help_bg": (17, 24, 39),        # Surface color
}

SENSITIVITY_COLORS = {
    1: COLORS["low"],
    2: COLORS["low"],
    3: COLORS["medium"],
    4: COLORS["high"],
    5: COLORS["critical"],
}


class ZoneEditor:
    """Interactive zone/tripwire editor for SmartCCTV configuration."""

    def __init__(self, camera_id: str, video_source: str):
        self.camera_id = camera_id
        self.video_source = video_source
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame: Optional[np.ndarray] = None
        self.reference_frame: Optional[np.ndarray] = None

        self.mode = "zone"  # 'zone' or 'tripwire'
        self.current_points: list[list[int]] = []
        self.current_name: str = "Zone 1"
        self.current_sensitivity: int = 3
        self.current_direction: str = "any"  # for tripwires: 'any', 'inbound', 'outbound'

        self.zones: list[dict] = []
        self.tripwires: list[dict] = []

        self.show_help = False
        self.status_message = "Press 'h' for help"
        self.mouse_pos: tuple[int, int] = (0, 0)

        # Load existing data if available
        self._load_existing()

    def _load_existing(self):
        """Load existing zone and tripwire configurations."""
        zones_path = DATA_DIR / "zones.json"
        tripwires_path = DATA_DIR / "tripwires.json"

        if zones_path.exists():
            with open(zones_path) as f:
                all_zones = json.load(f)
                self.zones = [z for z in all_zones if z.get("camera_id") == self.camera_id]
            print(f"Loaded {len(self.zones)} existing zones for {self.camera_id}")

        if tripwires_path.exists():
            with open(tripwires_path) as f:
                all_tripwires = json.load(f)
                self.tripwires = [t for t in all_tripwires if t.get("camera_id") == self.camera_id]
            print(f"Loaded {len(self.tripwires)} existing tripwires for {self.camera_id}")

    def _load_frame(self) -> bool:
        """Load a reference frame from the video source."""
        source = 0 if self.video_source == "0" else self.video_source
        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            print(f"ERROR: Cannot open video source: {self.video_source}")
            return False

        ok, frame = self.cap.read()
        if not ok:
            print("ERROR: Cannot read frame from source")
            return False

        self.reference_frame = frame.copy()
        self.frame = frame.copy()
        self.cap.release()
        return True

    def _mouse_callback(self, event: int, x: int, y: int, flags: int, param) -> None:
        """Handle mouse events for point placement."""
        self.mouse_pos = (x, y)

        if event == cv2.EVENT_LBUTTONDOWN:
            self.current_points.append([x, y])
            if self.mode == "zone":
                self.status_message = f"Zone point added ({len(self.current_points)} points). Right-click to close polygon."
            else:
                if len(self.current_points) == 1:
                    self.status_message = "Tripwire: Click second point to complete line"
                elif len(self.current_points) >= 2:
                    self._finish_tripwire()

        elif event == cv2.EVENT_RBUTTONDOWN:
            if self.mode == "zone" and len(self.current_points) >= 3:
                self._finish_zone()
            elif self.mode == "zone" and len(self.current_points) < 3:
                self.status_message = "Need at least 3 points to close a zone polygon"

    def _finish_zone(self) -> None:
        """Save the current polygon as a zone."""
        zone = {
            "zone_id": f"ZONE-{str(uuid.uuid4())[:8].upper()}",
            "camera_id": self.camera_id,
            "name": self.current_name,
            "sensitivity_level": self.current_sensitivity,
            "polygon_points": self.current_points.copy(),
            "camera_ids": [self.camera_id],
            "allowed_time_start": "00:00",
            "allowed_time_end": "23:59",
            "min_authorization_level": self.current_sensitivity,
            "is_active": True,
            "created_at": datetime.now().isoformat(),
            "calibration_version": "v1.0",
        }
        self.zones.append(zone)
        self.status_message = f"Zone '{self.current_name}' saved. Total: {len(self.zones)} zones"
        self.current_points = []
        self.current_name = f"Zone {len(self.zones) + 1}"

    def _finish_tripwire(self) -> None:
        """Save the current two points as a tripwire line."""
        if len(self.current_points) < 2:
            return
        tripwire = {
            "tripwire_id": f"TW-{str(uuid.uuid4())[:8].upper()}",
            "camera_id": self.camera_id,
            "name": self.current_name,
            "point_a": self.current_points[0],
            "point_b": self.current_points[1],
            "permitted_direction": self.current_direction,
            "is_active": True,
            "created_at": datetime.now().isoformat(),
            "calibration_version": "v1.0",
        }
        self.tripwires.append(tripwire)
        self.status_message = f"Tripwire '{self.current_name}' saved. Total: {len(self.tripwires)} tripwires"
        self.current_points = []
        self.current_name = f"Tripwire {len(self.tripwires) + 1}"

    def _draw_frame(self) -> np.ndarray:
        """Render the current editor state onto the frame."""
        if self.reference_frame is None:
            return np.zeros((480, 640, 3), dtype=np.uint8)

        canvas = self.reference_frame.copy()

        # Draw existing zones
        for zone in self.zones:
            pts = np.array(zone["polygon_points"], dtype=np.int32)
            color = SENSITIVITY_COLORS.get(zone.get("sensitivity_level", 3), COLORS["medium"])
            overlay = canvas.copy()
            cv2.fillPoly(overlay, [pts], color)
            cv2.addWeighted(overlay, 0.25, canvas, 0.75, 0, canvas)
            cv2.polylines(canvas, [pts], True, color, 2)
            centroid = pts.mean(axis=0).astype(int)
            label = f"{zone['name']} (L{zone['sensitivity_level']})"
            cv2.putText(canvas, label, (centroid[0] - 40, centroid[1]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

        # Draw existing tripwires
        for tw in self.tripwires:
            pa = tuple(tw["point_a"])
            pb = tuple(tw["point_b"])
            cv2.line(canvas, pa, pb, COLORS["tripwire"], 2)
            mid = ((pa[0] + pb[0]) // 2, (pa[1] + pb[1]) // 2)
            cv2.putText(canvas, f"{tw['name']} [{tw['permitted_direction']}]", mid,
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLORS["tripwire"], 1, cv2.LINE_AA)

        # Draw current in-progress shape
        for i, pt in enumerate(self.current_points):
            cv2.circle(canvas, tuple(pt), 5, COLORS["point"], -1)
            if i > 0:
                prev_pt = tuple(self.current_points[i - 1])
                line_color = COLORS["accent"] if self.mode == "zone" else COLORS["tripwire"]
                cv2.line(canvas, prev_pt, tuple(pt), line_color, 2)

        # Draw line from last point to mouse (preview)
        if self.current_points:
            last_pt = tuple(self.current_points[-1])
            preview_color = COLORS["accent"] if self.mode == "zone" else COLORS["tripwire"]
            cv2.line(canvas, last_pt, self.mouse_pos, preview_color, 1)

        # Status bar at bottom
        h, w = canvas.shape[:2]
        cv2.rectangle(canvas, (0, h - 50), (w, h), COLORS["overlay"], -1)
        mode_text = f"MODE: {self.mode.upper()} | Name: {self.current_name}"
        if self.mode == "zone":
            mode_text += f" | Sensitivity: {self.current_sensitivity}"
        else:
            mode_text += f" | Direction: {self.current_direction}"
        mode_text += f" | Points: {len(self.current_points)}"
        cv2.putText(canvas, mode_text, (10, h - 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLORS["accent"], 1, cv2.LINE_AA)
        cv2.putText(canvas, self.status_message, (10, h - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, COLORS["text"], 1, cv2.LINE_AA)

        # Mouse coordinates
        coord_text = f"X:{self.mouse_pos[0]} Y:{self.mouse_pos[1]}"
        cv2.putText(canvas, coord_text, (w - 150, h - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, COLORS["text"], 1, cv2.LINE_AA)

        # Help overlay
        if self.show_help:
            self._draw_help(canvas)

        return canvas

    def _draw_help(self, canvas: np.ndarray) -> None:
        """Draw help overlay."""
        h, w = canvas.shape[:2]
        help_lines = [
            "SMARTCCTV ZONE EDITOR - CONTROLS",
            "",
            "LEFT CLICK  - Add point to current shape",
            "RIGHT CLICK - Close zone polygon (needs 3+ points)",
            "Z           - Switch to Zone polygon mode",
            "T           - Switch to Tripwire mode",
            "D           - Delete last added point",
            "R           - Reset current shape (discard)",
            "N           - Set name (type in terminal)",
            "1-5         - Set zone sensitivity level",
            "I           - Set tripwire direction: inbound",
            "O           - Set tripwire direction: outbound",
            "A           - Set tripwire direction: any",
            "S           - Save all zones and tripwires",
            "H           - Toggle this help",
            "ESC         - Exit without saving",
        ]
        box_w, box_h = 450, len(help_lines) * 22 + 20
        bx, by = (w - box_w) // 2, (h - box_h) // 2
        cv2.rectangle(canvas, (bx, by), (bx + box_w, by + box_h), COLORS["help_bg"], -1)
        cv2.rectangle(canvas, (bx, by), (bx + box_w, by + box_h), COLORS["accent"], 1)
        for i, line in enumerate(help_lines):
            color = COLORS["accent"] if i == 0 else COLORS["text"]
            thickness = 1
            cv2.putText(canvas, line, (bx + 15, by + 20 + i * 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, thickness, cv2.LINE_AA)

    def _save(self) -> None:
        """Save zones and tripwires to JSON files (merging with other cameras' data)."""
        # Zones: merge this camera's zones with others
        zones_path = DATA_DIR / "zones.json"
        if zones_path.exists():
            with open(zones_path) as f:
                all_zones = json.load(f)
            # Remove old entries for this camera
            all_zones = [z for z in all_zones if z.get("camera_id") != self.camera_id]
        else:
            all_zones = []
        all_zones.extend(self.zones)
        with open(zones_path, "w") as f:
            json.dump(all_zones, f, indent=2)

        # Tripwires: same pattern
        tripwires_path = DATA_DIR / "tripwires.json"
        if tripwires_path.exists():
            with open(tripwires_path) as f:
                all_tripwires = json.load(f)
            all_tripwires = [t for t in all_tripwires if t.get("camera_id") != self.camera_id]
        else:
            all_tripwires = []
        all_tripwires.extend(self.tripwires)
        with open(tripwires_path, "w") as f:
            json.dump(all_tripwires, f, indent=2)

        self.status_message = f"Saved {len(self.zones)} zones + {len(self.tripwires)} tripwires to data/"
        print(f"\nSaved {len(self.zones)} zones to {zones_path}")
        print(f"Saved {len(self.tripwires)} tripwires to {tripwires_path}")

    def run(self) -> int:
        """Main editor loop. Returns 0 on success."""
        if not self._load_frame():
            return 1

        window_name = f"SmartCCTV Zone Editor - {self.camera_id}"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 1280, 720)
        cv2.setMouseCallback(window_name, self._mouse_callback)

        print(f"\nSmartCCTV Zone Editor started for camera: {self.camera_id}")
        print("Press 'h' for keyboard controls")

        while True:
            canvas = self._draw_frame()
            cv2.imshow(window_name, canvas)
            key = cv2.waitKey(30) & 0xFF

            if key == 27:  # ESC
                print("Exiting without saving.")
                break
            elif key == ord("h"):
                self.show_help = not self.show_help
            elif key == ord("z"):
                self.mode = "zone"
                self.current_points = []
                self.status_message = "Zone mode. Left-click to add points, right-click to close"
            elif key == ord("t"):
                self.mode = "tripwire"
                self.current_points = []
                self.status_message = "Tripwire mode. Click two points to define the crossing line"
            elif key == ord("d"):
                if self.current_points:
                    self.current_points.pop()
                    self.status_message = f"Last point removed ({len(self.current_points)} remaining)"
            elif key == ord("r"):
                self.current_points = []
                self.status_message = "Current shape reset"
            elif key == ord("n"):
                name = input(f"\nEnter name for current shape (current: '{self.current_name}'): ").strip()
                if name:
                    self.current_name = name
                    self.status_message = f"Name set to: {self.current_name}"
            elif key in [ord("1"), ord("2"), ord("3"), ord("4"), ord("5")]:
                self.current_sensitivity = int(chr(key))
                self.status_message = f"Sensitivity set to: {self.current_sensitivity}"
            elif key == ord("i"):
                self.current_direction = "inbound"
                self.status_message = "Tripwire direction: inbound only"
            elif key == ord("o"):
                self.current_direction = "outbound"
                self.status_message = "Tripwire direction: outbound only"
            elif key == ord("a"):
                self.current_direction = "any"
                self.status_message = "Tripwire direction: any"
            elif key == ord("s"):
                self._save()

        cv2.destroyAllWindows()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SmartCCTV Zone and Tripwire Editor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--camera",
        required=True,
        help="Camera ID to configure (e.g. CAM-01)",
    )
    parser.add_argument(
        "--video",
        default="video.mp4",
        help="Video file or RTSP URL to use as background reference (default: video.mp4)",
    )
    args = parser.parse_args()

    editor = ZoneEditor(camera_id=args.camera, video_source=args.video)
    return editor.run()


if __name__ == "__main__":
    sys.exit(main())
