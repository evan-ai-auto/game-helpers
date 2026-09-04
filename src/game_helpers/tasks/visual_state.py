"""Generic visual state detection from user-provided feature assets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from ..capture.models import Frame


class VisualStateStatus(str):
    DETECTED = "detected"
    NOT_DETECTED = "not_detected"
    INVALID = "invalid"


@dataclass(frozen=True)
class VisualAnchor:
    name: str
    image_path: Path
    offset_x: int
    offset_y: int
    threshold: float = 0.92
    search_step: int = 1


@dataclass(frozen=True)
class VisualStateProfile:
    name: str
    anchors: tuple[VisualAnchor, ...]
    consecutive_frames: int = 2


@dataclass(frozen=True)
class VisualStateObservation:
    state: str
    status: str
    confidence: float
    origin: tuple[int, int] | None = None
    anchor_scores: tuple[tuple[str, float], ...] = ()
    evidence: tuple[str, ...] = ()

    @property
    def detected(self) -> bool:
        return self.status == VisualStateStatus.DETECTED


def _frame_gray(frame: Frame) -> np.ndarray:
    expected = frame.width * frame.height * 4
    if frame.width <= 0 or frame.height <= 0 or len(frame.data) != expected:
        raise ValueError("invalid Frame")
    bgra = np.frombuffer(frame.data, dtype=np.uint8).reshape(frame.height, frame.width, 4)
    b, g, r = bgra[..., 0].astype(np.float32), bgra[..., 1].astype(np.float32), bgra[..., 2].astype(np.float32)
    return (0.114 * b + 0.587 * g + 0.299 * r).astype(np.float32)


def _template_gray(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (0.299 * r + 0.587 * g + 0.114 * b).astype(np.float32)


def _integral(array: np.ndarray) -> np.ndarray:
    return np.pad(array.cumsum(0).cumsum(1), ((1, 0), (1, 0)))


def _window_sum(integral: np.ndarray, height: int, width: int) -> np.ndarray:
    return integral[height:, width:] - integral[:-height, width:] - integral[height:, :-width] + integral[:-height, :-width]


def _ncc_map(image: np.ndarray, template: np.ndarray, step: int = 1) -> np.ndarray:
    h, w = template.shape
    H, W = image.shape
    if h > H or w > W:
        return np.empty((0, 0), dtype=np.float32)
    shape = (H + h - 1, W + w - 1)
    corr = np.fft.irfftn(np.fft.rfftn(image, shape) * np.conj(np.fft.rfftn(template, shape)), shape).real[: H - h + 1, : W - w + 1]
    n = float(h * w)
    t_mean = float(template.mean())
    t_energy = float(np.sum((template - t_mean) ** 2))
    if t_energy <= 1e-8:
        raise ValueError("template has no variance")
    ii = _integral(image)
    ii2 = _integral(image * image)
    sums = _window_sum(ii, h, w)
    sums2 = _window_sum(ii2, h, w)
    numerator = corr - sums * t_mean
    denominator = np.sqrt(np.maximum((sums2 - (sums * sums) / n) * t_energy, 1e-8))
    result = numerator / denominator
    return result[::step, ::step].astype(np.float32) if step > 1 else result.astype(np.float32)


def _load_profile(path: str | Path) -> VisualStateProfile:
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    anchors = tuple(
        VisualAnchor(
            name=item["name"],
            image_path=(base / item["image"]).resolve(),
            offset_x=int(item["offset_x"]),
            offset_y=int(item["offset_y"]),
            threshold=float(item.get("threshold", 0.92)),
            search_step=max(1, int(item.get("search_step", 1))),
        )
        for item in payload["anchors"]
    )
    if not anchors:
        raise ValueError("visual state profile has no anchors")
    return VisualStateProfile(str(payload["name"]), anchors, max(1, int(payload.get("consecutive_frames", 2))))


def detect_visual_state(frame: Frame, profile: VisualStateProfile) -> VisualStateObservation:
    """Search the complete frame for a composite visual-state asset."""
    try:
        image = _frame_gray(frame)
        matches = [(anchor, _ncc_map(image, _template_gray(anchor.image_path), anchor.search_step)) for anchor in profile.anchors]
        base = profile.anchors[0]
        base_scores = matches[0][1]
        ys, xs = np.where(base_scores >= base.threshold)
        if len(xs) == 0:
            return VisualStateObservation(profile.name, VisualStateStatus.NOT_DETECTED, float(base_scores.max()) if base_scores.size else 0.0, evidence=(f"anchor {base.name} not found",))
        candidates = np.argsort(base_scores[ys, xs])[::-1]
        for idx in candidates[:64]:
            bx, by = int(xs[idx] * base.search_step), int(ys[idx] * base.search_step)
            scores_for_origin = [(base.name, float(base_scores[ys[idx], xs[idx]]))]
            valid = True
            for anchor, scores in matches[1:]:
                ax = bx + anchor.offset_x - base.offset_x
                ay = by + anchor.offset_y - base.offset_y
                sx, sy = ax // anchor.search_step, ay // anchor.search_step
                if sx < 0 or sy < 0 or sy >= scores.shape[0] or sx >= scores.shape[1]:
                    valid = False
                    break
                score = float(scores[sy, sx])
                scores_for_origin.append((anchor.name, score))
                if score < anchor.threshold:
                    valid = False
                    break
            if valid:
                return VisualStateObservation(profile.name, VisualStateStatus.DETECTED, min(s for _, s in scores_for_origin), (bx - base.offset_x, by - base.offset_y), tuple(scores_for_origin), ("all required anchors matched",))
        return VisualStateObservation(profile.name, VisualStateStatus.NOT_DETECTED, float(base_scores.max()), evidence=("base anchor found but composite anchors did not align",))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return VisualStateObservation(profile.name, VisualStateStatus.INVALID, 0.0, evidence=(str(exc),))


def load_visual_state(path: str | Path) -> VisualStateProfile:
    return _load_profile(path)


def make_visual_state_verifier(capture: Callable[[], Frame], profile: VisualStateProfile) -> Callable[[], VisualStateObservation | None]:
    """Return a stateful verifier requiring consecutive positive frames."""
    consecutive = 0

    def verify() -> VisualStateObservation | None:
        nonlocal consecutive
        observation = detect_visual_state(capture(), profile)
        if observation.detected:
            consecutive += 1
            if consecutive >= profile.consecutive_frames:
                return observation
        else:
            consecutive = 0
        return None

    return verify
