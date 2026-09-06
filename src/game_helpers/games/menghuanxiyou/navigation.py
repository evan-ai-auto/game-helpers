"""Navigation graph and semantic targets for 梦幻西游."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from game_helpers.core.models import Point


@dataclass(frozen=True)
class NavigationTarget:
    id: str
    name: str
    point: Point
    kind: str
    destination: dict[str, Any]


class DreamNavigationGraph:
    """Build a lightweight route graph from the game's scene knowledge."""

    def __init__(self, scene: dict[str, Any]) -> None:
        self.scene = scene
        self.scene_id = scene.get("scene", {}).get("id")
        self.scene_name = scene.get("scene", {}).get("name")
        self.targets = tuple(
            NavigationTarget(
                id=item["id"],
                name=item["name"],
                point=Point(int(item["position"]["x"]), int(item["position"]["y"])),
                kind=item.get("type", "unknown"),
                destination=dict(item.get("destination", {})),
            )
            for item in scene.get("transport_points", [])
        )

    def find(self, target_id: str) -> NavigationTarget | None:
        return next((target for target in self.targets if target.id == target_id), None)

    def route(self, target_id: str) -> tuple[NavigationTarget, ...]:
        target = self.find(target_id)
        return (target,) if target else ()

    def as_metadata(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "scene_name": self.scene_name,
            "targets": tuple(target.id for target in self.targets),
        }
