"""Scene recognition and visual target resolution for 梦幻西游."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SceneMatch:
    scene_id: str
    scene_name: str
    confidence: float
    source: str


class DreamSceneRecognizer:
    """Recognize scenes from explicit visual/OCR evidence, never map guesses."""

    def __init__(self, scenes: Iterable[dict]) -> None:
        self.scenes = tuple(scenes)

    def recognize(self, text: Iterable[str], metadata: dict) -> SceneMatch | None:
        hint = metadata.get("scene_id")
        if hint:
            for scene in self.scenes:
                if scene.get("id") == hint:
                    return SceneMatch(scene["id"], scene["name"], 1.0, "metadata")

        haystack = " ".join(text)
        for scene in self.scenes:
            aliases = [scene.get("name", ""), *scene.get("aliases", [])]
            if any(alias and alias in haystack for alias in aliases):
                return SceneMatch(scene["id"], scene["name"], 0.92, "text")
        return None
