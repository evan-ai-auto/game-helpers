"""Visual perception pipeline for the supported 梦幻西游 800x600 baseline."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from game_helpers.capture.models import Frame
from game_helpers.core.agent_protocol import Observation
from game_helpers.vision.template_matching import load_template_asset, match_template

from .scene import DreamSceneRecognizer


class DreamObservationBuilder:
    """Build a semantic observation from pixels plus optional OCR/scene hints."""

    def __init__(self, asset_root: str | Path | None = None) -> None:
        root = Path(asset_root) if asset_root else Path(__file__).resolve().parents[4] / "data" / "assets"
        self.asset_root = root
        self.item_bar = load_template_asset(root / "ui" / "resolutions" / "800x600" / "item_bar_icon.blob")
        self.item_panel = load_template_asset(root / "ui" / "resolutions" / "800x600" / "item_panel_open.png")
        self.soul_icon = load_template_asset(root / "ui" / "resolutions" / "800x600" / "soul_task_claimed_icon.json")
        self.scenes = self._load_scenes(root / "scenes")
        self.scene_recognizer = DreamSceneRecognizer(self.scenes)

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

    def build(self, frame: Frame) -> Observation:
        image = Image.frombytes("RGBA", (frame.width, frame.height), frame.data, "raw", "BGRA")
        item_bar = match_template(image, self.item_bar, threshold=0.75)
        item_panel = match_template(image, self.item_panel, threshold=0.88)
        soul_icon = match_template(image, self.soul_icon, threshold=0.88)

        # OCR can be supplied by a future platform/Vision adapter through the
        # frame metadata without coupling this builder to an OCR engine.
        text = tuple(frame.metadata.get("ocr_text", ())) if hasattr(frame, "metadata") else ()
        scene = self.scene_recognizer.recognize(text, getattr(frame, "metadata", {}))
        objects = {}
        if item_bar:
            objects["item_bar_toggle"] = item_bar.bounds
        if item_panel:
            objects["item_panel_open"] = item_panel.bounds
        if soul_icon:
            objects["soul_task_claimed"] = soul_icon.bounds

        metadata = {
            "game": "梦幻西游",
            "resolution": f"{frame.width}x{frame.height}",
            "item_bar_score": item_bar.score if item_bar else 0.0,
            "item_panel_score": item_panel.score if item_panel else 0.0,
            "soul_task_score": soul_icon.score if soul_icon else 0.0,
        }
        if scene:
            metadata.update({"scene_id": scene.scene_id, "scene_name": scene.scene_name, "scene_confidence": scene.confidence, "scene_source": scene.source})
        return Observation(
            frame=frame,
            observation_id=f"dream-{frame.captured_at:.6f}",
            timestamp=frame.captured_at,
            objects=objects,
            text=text,
            metadata=metadata,
        )
