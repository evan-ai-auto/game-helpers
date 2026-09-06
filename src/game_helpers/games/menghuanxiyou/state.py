"""梦幻西游 semantic state and game adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from game_helpers.core.agent_protocol import Observation
from game_helpers.core.models import GameState, Point, Rect


@dataclass
class DreamGameState(GameState):
    """Actionable semantic state projected from visual evidence and game knowledge."""

    game: str = "梦幻西游"
    resolution: str = ""
    item_panel_open: bool = False
    soul_task_claimed: bool = False
    scene_id: str | None = None
    scene_name: str | None = None
    scene_confidence: float = 0.0
    player_position: Point | None = None
    player_position_confidence: float = 0.0
    cash: int | None = None
    cash_confidence: float = 0.0
    transport_points: dict[str, Rect] = field(default_factory=dict)
    nearby_targets: dict[str, Rect] = field(default_factory=dict)
    interaction_target: str | None = None
    navigation_goal: str | None = None


class DreamGameAdapter:
    """Map observations into state while keeping map knowledge separate from vision."""

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
        objects = dict(observation.objects)
        scene_hint = observation.metadata.get("scene_id")
        scene = self.scenes.get("scene", {})
        scene_id = scene_hint if scene_hint == scene.get("id") else None
        scene_name = scene.get("name") if scene_id else observation.metadata.get("scene_name")
        confidence = float(observation.metadata.get("scene_confidence", 0.0))

        location = observation.metadata.get("player_location", {})
        position = None
        position_confidence = 0.0
        if isinstance(location, dict) and location.get("x") is not None and location.get("y") is not None:
            position = Point(int(location["x"]), int(location["y"]))
            position_confidence = float(location.get("confidence", 0.0))
            scene_name = scene_name or location.get("scene_name")

        cash_info = observation.metadata.get("cash", {})
        cash = None
        cash_confidence = 0.0
        if isinstance(cash_info, dict) and cash_info.get("value") is not None:
            cash = int(cash_info["value"])
            cash_confidence = float(cash_info.get("confidence", 0.0))

        transport_points: dict[str, Rect] = {}
        for item in self.scenes.get("transport_points", []):
            key = f"transport:{item['id']}"
            if key in objects:
                transport_points[item["id"]] = objects[key]

        target = observation.metadata.get("interaction_target")
        return DreamGameState(
            window=observation.frame.window,
            screenshot_available=True,
            inventory_visible="item_panel_open" in objects,
            item_panel_open="item_panel_open" in objects,
            soul_task_claimed="soul_task_claimed" in objects,
            task_completed="soul_task_claimed" in objects,
            detected_text=list(observation.text),
            targets=objects,
            game=observation.metadata.get("game", "梦幻西游"),
            resolution=observation.metadata.get("resolution", ""),
            scene_id=scene_id,
            scene_name=scene_name,
            scene_confidence=confidence,
            player_position=position,
            player_position_confidence=position_confidence,
            cash=cash,
            cash_confidence=cash_confidence,
            transport_points=transport_points,
            nearby_targets={k: v for k, v in objects.items() if k.startswith("npc:") or k.startswith("transport:")},
            interaction_target=target,
            navigation_goal=observation.metadata.get("navigation_goal"),
            metadata=dict(observation.metadata),
        )
