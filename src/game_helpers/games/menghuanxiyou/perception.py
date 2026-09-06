"""Three-layer perception adapter for 梦幻西游.

The design deliberately avoids making template matching the primary source of
truth. Global understanding and configurable ROI OCR feed one semantic
Observation; small templates remain an optional compatibility/fallback path
for legacy UI assets.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

from game_helpers.capture.models import Frame
from game_helpers.core.agent_protocol import Observation
from game_helpers.vision.ocr import OCRBackend, OCRResult, parse_integer, parse_scene_coordinate
from game_helpers.vision.regions import VisionRegionRegistry
from game_helpers.vision.template_matching import load_template_asset, match_template

from .scene import DreamSceneRecognizer


class DreamObservationBuilder:
    """Build semantic observations from global vision plus configurable ROIs."""

    def __init__(
        self,
        asset_root: str | Path | None = None,
        *,
        ocr_backend: OCRBackend | None = None,
        enable_template_fallback: bool = True,
    ) -> None:
        root = Path(asset_root) if asset_root else Path(__file__).resolve().parents[4] / "data" / "assets"
        self.asset_root = root
        self.ocr_backend = ocr_backend
        self.regions = VisionRegionRegistry.from_json(root / "ui" / "vision_regions.json")
        self.enable_template_fallback = enable_template_fallback
        self.item_bar = self._load_template(root / "ui" / "resolutions" / "800x600" / "item_bar_icon.blob")
        self.item_panel = self._load_template(root / "ui" / "resolutions" / "800x600" / "item_panel_open.png")
        self.soul_icon = self._load_template(root / "ui" / "resolutions" / "800x600" / "soul_task_claimed_icon.json")
        self.scenes = self._load_scenes(root / "scenes")
        self.scene_recognizer = DreamSceneRecognizer(self.scenes)

    @staticmethod
    def _load_template(path: Path):
        try:
            return load_template_asset(path)
        except (OSError, ValueError):
            return None

    @staticmethod
    def _load_scenes(path: Path) -> tuple[dict, ...]:
        scenes = []
        for file in sorted(path.glob("*.json")):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                if data.get("scene"):
                    scenes.append(data["scene"])
            except (OSError, ValueError):
                continue
        return tuple(scenes)

    @staticmethod
    def _ocr_text(results: tuple[OCRResult, ...]) -> tuple[str, ...]:
        return tuple(result.text.strip() for result in results if result.text.strip())

    def _read_roi(self, image: Image.Image, frame: Frame, name: str) -> tuple[OCRResult, ...]:
        if not self.ocr_backend:
            return ()
        region = self.regions.resolve(name, frame.width, frame.height)
        if not region:
            return ()
        return self.ocr_backend.read(image, region=region)

    def build(self, frame: Frame) -> Observation:
        image = Image.frombytes("RGBA", (frame.width, frame.height), frame.data, "raw", "BGRA")
        frame_hints: dict[str, Any] = dict(getattr(frame, "metadata", {}) or {})

        # Layer 1: global visual understanding. A future global vision adapter
        # may populate these hints; the game adapter only consumes semantics.
        global_state = {
            "in_game": frame.window.visible and bool(frame.window.title),
            "scene": frame_hints.get("scene_id") or frame_hints.get("scene_name"),
            "combat": frame_hints.get("combat", False),
            "dialogue": frame_hints.get("dialogue", False),
            "map_or_dungeon": frame_hints.get("map_or_dungeon"),
            "teleport_detected": frame_hints.get("teleport_detected", False),
            "ui_state": frame_hints.get("ui_state", {}),
        }

        # Layer 2: high-value configurable ROIs. OCR is pluggable and can be
        # swapped without changing the Agent, GameState, or runtime.
        roi_text: list[str] = []
        roi_metadata: dict[str, Any] = {}
        location_results = self._read_roi(image, frame, "player_location")
        location_text = self._ocr_text(location_results)
        roi_text.extend(location_text)
        location = parse_scene_coordinate(" ".join(location_text))
        if location:
            map_name, x, y = location
            roi_metadata["player_location"] = {
                "scene_name": map_name,
                "x": x,
                "y": y,
                "confidence": min((r.confidence for r in location_results if r.text.strip()), default=0.0),
                "source": "ocr",
            }

        cash_results = self._read_roi(image, frame, "economy")
        cash_text = self._ocr_text(cash_results)
        roi_text.extend(cash_text)
        if cash_text:
            cash = parse_integer("".join(cash_text))
            if cash is not None:
                roi_metadata["cash"] = {
                    "value": cash,
                    "confidence": min((r.confidence for r in cash_results if r.text.strip()), default=0.0),
                    "source": "ocr",
                }

        # Preserve externally supplied OCR text for compatibility with the
        # existing scene recognizer and offline tests.
        text = tuple(frame_hints.get("ocr_text", ())) + tuple(roi_text)
        scene = self.scene_recognizer.recognize(text, frame_hints)

        # Layer 3: semantic observation. Template matching is deliberately a
        # fallback for legacy assets, never required for location/economy data.
        objects: dict[str, Any] = {}
        template_scores: dict[str, float] = {}
        if self.enable_template_fallback:
            detectors = (
                ("item_bar_toggle", self.item_bar, 0.75),
                ("item_panel_open", self.item_panel, 0.88),
                ("soul_task_claimed", self.soul_icon, 0.88),
            )
            for name, asset, threshold in detectors:
                if asset is None:
                    continue
                match = match_template(image, asset, threshold=threshold)
                template_scores[name] = match.score if match else 0.0
                if match:
                    objects[name] = match.bounds

        metadata: dict[str, Any] = {
            "game": "梦幻西游",
            "resolution": f"{frame.width}x{frame.height}",
            "vision_layers": {"global": global_state, "roi": roi_metadata},
            "roi_regions": self.regions.names(),
            "template_fallback": self.enable_template_fallback,
            "template_scores": template_scores,
        }
        if scene:
            metadata.update(
                {
                    "scene_id": scene.scene_id,
                    "scene_name": scene.scene_name,
                    "scene_confidence": scene.confidence,
                    "scene_source": scene.source,
                }
            )
        if "player_location" in roi_metadata:
            metadata["player_location"] = roi_metadata["player_location"]
            metadata.setdefault("scene_name", roi_metadata["player_location"]["scene_name"])
        if "cash" in roi_metadata:
            metadata["cash"] = roi_metadata["cash"]
        return Observation(
            frame=frame,
            observation_id=f"dream-{frame.captured_at:.6f}",
            timestamp=frame.captured_at,
            objects=objects,
            text=text,
            metadata=metadata,
        )
