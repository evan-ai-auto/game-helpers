"""梦幻西游 semantic state and game adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from game_helpers.core.agent_protocol import Observation
from game_helpers.core.models import GameState, Rect


@dataclass
class DreamGameState(GameState):
    """Game-specific state projected from the generic Observation contract."""

    game: str = "梦幻西游"
    resolution: str = ""
    item_panel_open: bool = False
    soul_task_claimed: bool = False
    scene_id: str | None = None
    scene_name: str | None = None
    transport_points: dict[str, Rect] = field(default_factory=dict)


class DreamGameAdapter:
    """Map visual observations into actionable 梦幻西游 state."""

    def __init__(self, asset_root: str | Path | None = None) -> None:
        root = Path(asset_root) if asset_root else Path(__file__).resolve().parents[4] / "data" / "assets"
        self.asset_root = root
        self.scenes = self._load_scene(root / "scenes" / "changan.json")

    @staticmethod
    def _load_scene(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def to_state(self, observation: Observation) -> DreamGameState:
        objects = observation.objects
        scene = self.scenes.get("scene", {})
        return DreamGameState(
            window=observation.frame.window,
            screenshot_available=True,
            inventory_visible="item_panel_open" in objects,
            item_panel_open="item_panel_open" in objects,
            soul_task_claimed="soul_task_claimed" in objects,
            detected_text=list(observation.text),
            targets=dict(objects),
            game=observation.metadata.get("game", "梦幻西游"),
            resolution=observation.metadata.get("resolution", ""),
            scene_id=scene.get("id"),
            scene_name=scene.get("name"),
            metadata=dict(observation.metadata),
        )
