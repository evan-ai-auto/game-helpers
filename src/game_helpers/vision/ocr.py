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


def parse_scene_coordinate(text: str) -> tuple[str, int, int] | None:
    """Parse map name and dynamic player coordinates from OCR text."""
    match = _COORDINATE_RE.search(text)
    if not match:
        return None
    return match.group("map").strip(), int(match.group("x")), int(match.group("y"))


def parse_integer(text: str) -> int | None:
    """Parse a currency/count value while tolerating OCR separators."""
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else None
