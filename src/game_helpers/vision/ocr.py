"""OCR contracts and deterministic parsers used by semantic vision."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol

from PIL import Image

from game_helpers.core.models import Rect


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float = 0.0


class OCRBackend(Protocol):
    """Pluggable OCR implementation; the vision layer does not own an engine."""

    def read(self, image: Image.Image, *, region: Rect) -> tuple[OCRResult, ...]:
        ...


_COORDINATE_RE = re.compile(
    r"(?P<map>.+?)\s*[\[(](?P<x>\d+)\s*[,，]\s*(?P<y>\d+)[\])]"
)
_HUD_XY_RE = re.compile(
    r"X\s*[.:：]*\s*(?P<x>(?:\d\s*)+)\s*(?:Y\s*)?[:：.]*\s*(?P<y>(?:\d\s*)+)",
    re.IGNORECASE,
)
_HUD_XY_LABELED_RE = re.compile(
    r"X\s*[.:：]*\s*(?P<x>(?:\d\s*)+)\s*Y\s*[:：.]*\s*(?P<y>(?:\d\s*)+)",
    re.IGNORECASE,
)
_SCENE_NAME_RE = re.compile(r"[\u4e00-\u9fff]{2,}")


def parse_scene_coordinate(text: str) -> tuple[str, int, int] | None:
    """Parse an assembled ``地图名[x,y]`` result string."""
    match = _COORDINATE_RE.search(text)
    if not match:
        return None
    return match.group("map").strip(), int(match.group("x")), int(match.group("y"))


def parse_scene_name(text: str) -> str | None:
    """Pick the scene-name line from one OCR reading."""
    match = _SCENE_NAME_RE.search(text.replace(" ", ""))
    return match.group(0) if match else None


def parse_hud_xy(text: str) -> tuple[int, int] | None:
    """Parse ``X:71 Y:34`` and the spaced form ``X ： 5 4 ： 7 2``.

    A Y label keeps every digit before it on X. ``X ： 80 Y ： 四`` stays unread
    instead of becoming ``(8, 0)``.
    """
    match = _HUD_XY_LABELED_RE.search(text)
    if match is None and re.search(r"Y", text, re.IGNORECASE) is None:
        match = _HUD_XY_RE.search(text)
    if not match:
        return None
    x_digits = re.sub(r"\s+", "", match.group("x"))
    y_digits = re.sub(r"\s+", "", match.group("y"))
    if not x_digits or not y_digits:
        return None
    return int(x_digits), int(y_digits)


def format_scene_coordinate(map_name: str, x: int, y: int) -> str:
    """Format a recognized location as ``地图名[x,y]``."""
    return f"{map_name}[{x},{y}]"


def assemble_scene_coordinate(scene_text: str, coordinate_text: str) -> tuple[str, int, int] | None:
    """Combine a scene-name reading and an ``X:n Y:n`` reading into one location."""
    name = parse_scene_name(scene_text)
    xy = parse_hud_xy(coordinate_text)
    if name is None or xy is None:
        return None
    return name, xy[0], xy[1]


def parse_integer(text: str) -> int | None:
    """Parse a currency/count value while tolerating OCR separators."""
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else None
