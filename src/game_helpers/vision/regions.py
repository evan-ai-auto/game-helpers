"""Configurable regions of interest for vision pipelines.

ROI coordinates are configuration, not game logic. A region may declare a
reference resolution so the same semantic region can be scaled when the
runtime capture resolution differs.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from game_helpers.core.models import Rect


@dataclass(frozen=True)
class VisionRegion:
    """Named ROI in a reference coordinate space."""

    name: str
    box: tuple[int, int, int, int]
    reference_width: int | None = None
    reference_height: int | None = None
    enabled: bool = True
    layer: str = "roi"

    def resolve(self, width: int, height: int) -> Rect:
        """Scale the configured ROI to the current frame when needed."""
        left, top, right, bottom = self.box
        if self.reference_width and self.reference_height:
            sx = width / self.reference_width
            sy = height / self.reference_height
            left, right = round(left * sx), round(right * sx)
            top, bottom = round(top * sy), round(bottom * sy)
        return Rect(max(0, left), max(0, top), min(width, right), min(height, bottom))


class VisionRegionRegistry:
    """Lookup and resolve semantic ROIs without hard-coding coordinates."""

    def __init__(self, regions: tuple[VisionRegion, ...] = ()) -> None:
        self._regions = {region.name: region for region in regions}

    @classmethod
    def from_json(cls, path: str | Path) -> "VisionRegionRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        regions = []
        for item in payload.get("regions", []):
            regions.append(
                VisionRegion(
                    name=item["name"],
                    box=tuple(item["box"]),
                    reference_width=item.get("reference_resolution", [None, None])[0],
                    reference_height=item.get("reference_resolution", [None, None])[1],
                    enabled=item.get("enabled", True),
                    layer=item.get("layer", "roi"),
                )
            )
        return cls(tuple(regions))

    def get(self, name: str) -> VisionRegion | None:
        region = self._regions.get(name)
        return region if region and region.enabled else None

    def resolve(self, name: str, width: int, height: int) -> Rect | None:
        region = self.get(name)
        return region.resolve(width, height) if region else None

    def names(self) -> tuple[str, ...]:
        return tuple(self._regions)
