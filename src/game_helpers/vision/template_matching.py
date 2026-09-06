"""Small dependency-free template matcher for GUI asset detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import base64
import json
import os

import numpy as np
from PIL import Image

from game_helpers.core.models import Point, Rect


@dataclass(frozen=True)
class TemplateMatch:
    score: float
    bounds: Rect

    @property
    def center(self) -> Point:
        return self.bounds.center


def _gray(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("L"), dtype=np.float32)


def _decode_image(path: Path) -> Image.Image:
    if path.suffix == ".blob":
        return Image.open(path)
    return Image.open(path)


def load_template_asset(asset_path: str | os.PathLike[str]) -> Image.Image:
    """Load a PNG asset or a base64 JSON template asset."""
    path = Path(asset_path)
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw = payload.get("template_base64")
        if not raw:
            image_name = payload.get("image")
            if not image_name:
                raise ValueError(f"No template image in {path}")
            return _decode_image(path.parent / image_name)
        return Image.open(__import__("io").BytesIO(base64.b64decode(raw)))
    if path.suffix == ".blob":
        raw = base64.b64decode(path.read_text(encoding="utf-8").strip())
        return Image.open(__import__("io").BytesIO(raw))
    return Image.open(path)


def match_template(frame: Image.Image, template: Image.Image, *, threshold: float = 0.8) -> TemplateMatch | None:
    """Find the best normalized cross-correlation match.

    The implementation uses FFT convolution plus integral images, avoiding a
    dependency on OpenCV while remaining practical for 800x600 GUI frames.
    """
    image = _gray(frame)
    needle = _gray(template)
    th, tw = needle.shape
    ih, iw = image.shape
    if th > ih or tw > iw:
        return None

    needle = needle - needle.mean()
    needle_norm = float(np.sqrt(np.sum(needle * needle)))
    if needle_norm < 1e-6:
        return None

    shape = (ih + th - 1, iw + tw - 1)
    corr = np.fft.irfft2(
        np.fft.rfft2(image, shape) * np.conj(np.fft.rfft2(needle, shape)),
        shape,
    )
    corr = corr[th - 1 : ih, tw - 1 : iw]

    integral = np.pad(np.cumsum(np.cumsum(image, axis=0), axis=1), ((1, 0), (1, 0)))
    integral_sq = np.pad(np.cumsum(np.cumsum(image * image, axis=0), axis=1), ((1, 0), (1, 0)))
    sums = integral[th:, tw:] - integral[:-th, tw:] - integral[th:, :-tw] + integral[:-th, :-tw]
    sums_sq = integral_sq[th:, tw:] - integral_sq[:-th, tw:] - integral_sq[th:, :-tw] + integral_sq[:-th, :-tw]
    count = float(th * tw)
    variance = np.maximum(sums_sq - (sums * sums) / count, 1e-6)
    scores = corr / (np.sqrt(variance) * needle_norm)
    y, x = np.unravel_index(np.argmax(scores), scores.shape)
    score = float(scores[y, x])
    if score < threshold:
        return None
    return TemplateMatch(score=score, bounds=Rect(x, y, x + tw, y + th))
